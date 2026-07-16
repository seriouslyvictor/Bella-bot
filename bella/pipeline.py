"""The per-message pipeline: safety checks, Scope Gate, then a guarded reply.

This module owns the invariants that must hold from day one: never reply to
ourselves, never reply twice to the same delivery, always send the user a
reply, and never let a processing error escape after the webhook has already
been acknowledged.
"""

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Protocol

from bella.answer_guard import strip_foreign_urls
from bella.canned_replies import CannedReplies
from bella.conversation_store import (
    ConversationMessage,
    ConversationStore,
)
from bella.evolution import InboundMessage, WhatsAppSender
from bella.rate_limit import (
    RateLimitDecision,
    RateLimitPolicy,
    SlidingWindowRateLimiter,
)
from bella.reply_language import ReplyLanguage, detect_reply_language
from bella.retention import run_retention_job
from bella.scope_gate import RouteCategory, ScopeGate

logger = logging.getLogger("bella")


class RefusalRotation:
    """Bounded per-recipient refusal rotation (Postgres in ticket 06).

    Out-of-scope traffic is the unbounded, adversarial surface — spam, wrong
    numbers, injection probes — so the recipient keys are attacker-chosen and
    must not accumulate forever. Evicting a cold recipient only costs them a
    restart of the rotation, which is invisible.
    """

    def __init__(self, refusals: Sequence[str], capacity: int = 2048) -> None:
        self._refusals = tuple(refusals)
        self._next: OrderedDict[str, int] = OrderedDict()
        self._capacity = capacity

    def take(self, recipient: str) -> str:
        index = self._next.get(recipient, 0)
        self._next[recipient] = index + 1
        self._next.move_to_end(recipient)
        if len(self._next) > self._capacity:
            self._next.popitem(last=False)
        return self._refusals[index % len(self._refusals)]


@dataclass(frozen=True)
class AnswerResult:
    text: str
    needs_handoff: bool = False


class Answerer(Protocol):
    async def answer(
        self,
        text: str,
        category: RouteCategory,
        history: Sequence[ConversationMessage],
    ) -> AnswerResult: ...


@dataclass(frozen=True)
class ReplyPlan:
    history_text: str
    outbound_text: str | None
    handoff_summary: str | None = None

    @classmethod
    def text(
        cls, text: str, *, handoff_summary: str | None = None
    ) -> "ReplyPlan":
        return cls(text, text, handoff_summary)

    @classmethod
    def document(cls, caption: str) -> "ReplyPlan":
        return cls(caption, None)


class Pipeline:
    def __init__(
        self,
        sender: WhatsAppSender,
        scope_gate: ScopeGate,
        answerer: Answerer,
        canned_replies: CannedReplies,
        enrollment_url: str,
        conversation_store: ConversationStore,
        apostila_path: Path,
        human_contact_reply: str,
        admin_contact: str,
        rate_limit_policy: RateLimitPolicy,
        rate_limit_clock: Callable[[], float] = monotonic,
    ) -> None:
        self._sender = sender
        self._scope_gate = scope_gate
        self._answerer = answerer
        self._canned_replies = canned_replies
        self._enrollment_url = enrollment_url
        self._conversation_store = conversation_store
        self._apostila_path = apostila_path
        self._human_contact_reply = human_contact_reply
        self._admin_contact = "".join(
            character for character in admin_contact if character.isdigit()
        )
        self._refusals = RefusalRotation(canned_replies.refusals)
        self._rate_limiter = SlidingWindowRateLimiter(
            rate_limit_policy,
            rate_limit_clock,
        )

    async def start(self) -> None:
        await self._conversation_store.start()

    async def close(self) -> None:
        await self._conversation_store.close()

    async def check_readiness(self) -> None:
        # Both local dependencies are required to accept a webhook: Postgres
        # claims the delivery first, then Evolution sends the reply. Probe in
        # parallel and cap the whole check below Docker's five-second timeout.
        async with asyncio.timeout(4):
            await asyncio.gather(
                self._conversation_store.check_health(),
                self._sender.check_health(),
            )

    async def run_retention(self) -> None:
        await run_retention_job(self._conversation_store)

    async def handle(self, message: InboundMessage) -> None:
        """Process one inbound message. Never raises — the ack already went out."""
        try:
            await self._handle(message)
        except Exception:
            logger.exception("failed to process message %s", message.message_id)

    async def _handle(self, message: InboundMessage) -> None:
        if message.is_from_me:
            return
        if message.is_group:
            # Bella never speaks in groups (spec story 24). Full input policy
            # lands in ticket 09, but this guard must precede deployment.
            return
        if not await self._conversation_store.claim_delivery(message.message_id):
            logger.info("duplicate delivery ignored: %s", message.message_id)
            return
        language = detect_reply_language(message.text)
        rate_limit = self._rate_limiter.check(message.number)
        if rate_limit is RateLimitDecision.SILENCE:
            logger.info("rate-limited message silenced: %s", message.message_id)
            return
        if rate_limit is RateLimitDecision.NOTIFY:
            await self._sender.send_text(
                message.number,
                self._canned_replies.reply("rate_limit_reply", language),
            )
            logger.info("rate-limit notice sent: %s", message.message_id)
            return
        if message.text is None:
            logger.info(
                "non-text message receives canned reply: %s (type=%s)",
                message.message_id,
                message.message_type,
            )
            await self._sender.send_text(
                message.number,
                self._canned_replies.reply("media_reply", language),
            )
            return

        history = await self._conversation_store.recent_messages(message.number)
        await self._conversation_store.append_message(
            message.number,
            ConversationMessage("user", message.text, datetime.now(UTC)),
        )
        try:
            plan = await self._reply_for(
                message.text,
                message.number,
                history,
                language,
            )
        except Exception:
            # Guards the whole reply-producing step, not just one stage of it:
            # every stage added here must degrade to a reply, never to silence.
            logger.exception("reply production failed for %s", message.message_id)
            plan = ReplyPlan.text(
                self._canned_replies.reply("error_reply", language)
            )
        if plan.outbound_text is not None:
            await self._sender.send_text(message.number, plan.outbound_text)
        await self._conversation_store.append_message(
            message.number,
            ConversationMessage("assistant", plan.history_text, datetime.now(UTC)),
        )
        if plan.handoff_summary is not None:
            await self._notify_admin(message.number, plan.handoff_summary)
        logger.info("replied to %s (message %s)", message.number, message.message_id)

    async def _notify_admin(self, user_number: str, summary: str) -> None:
        if not self._admin_contact or user_number == self._admin_contact:
            return
        notification = (
            "Handoff Bella\n"
            f"Usuario: {user_number}\n"
            f"Pedido: {summary[:500]}"
        )
        try:
            await self._sender.send_text(self._admin_contact, notification)
        except Exception:
            logger.exception("failed to notify admin about %s", user_number)

    async def _reply_for(
        self,
        text: str,
        number: str,
        history: Sequence[ConversationMessage],
        language: ReplyLanguage,
    ) -> ReplyPlan:
        category = await self._scope_gate.classify(text)
        if category is RouteCategory.OUT_OF_SCOPE:
            return ReplyPlan.text(self._refusals.take(number))
        if category is RouteCategory.HUMAN_REQUESTED:
            contact = self._human_contact_reply
            if language is not ReplyLanguage.PORTUGUESE:
                intro = self._canned_replies.reply("human_contact_intro", language)
                contact = f"{intro}\n{contact}"
            return ReplyPlan.text(contact, handoff_summary=text)
        if category is RouteCategory.APOSTILA_REQUEST:
            if not self._apostila_path.is_file():
                return ReplyPlan.text(
                    self._canned_replies.reply("apostila_soon_reply", language)
                )
            caption = self._canned_replies.reply("apostila_caption", language)
            try:
                await self._sender.send_document(
                    number,
                    self._apostila_path,
                    caption,
                )
            except Exception:
                logger.exception("failed to send apostila to %s", number)
                return ReplyPlan.text(
                    self._canned_replies.reply("apostila_error_reply", language)
                )
            return ReplyPlan.document(caption)
        answer = await self._answerer.answer(text, category, history)
        reply_text = answer.text
        if answer.needs_handoff:
            heading = self._canned_replies.reply("human_contact_intro", language)
            reply_text = (
                f"{reply_text}\n\n{heading}\n{self._human_contact_reply}"
            )
        return ReplyPlan.text(
            strip_foreign_urls(reply_text, self._enrollment_url),
            handoff_summary=text if answer.needs_handoff else None,
        )
