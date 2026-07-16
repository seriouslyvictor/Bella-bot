"""The per-message pipeline: safety checks, Scope Gate, then a guarded reply.

This module owns the invariants that must hold from day one: never reply to
our own echoed messages (from-me messages are classified, not blanket-
dropped — see EchoLedger), never reply twice to the same delivery, always
send the user a reply, and never let a processing error escape after the
webhook has already been acknowledged.

The always-reply invariant has exactly one sanctioned exception: a
Takeover Pause (ADR 0003). While the course owner has typed into a
conversation, Bella stores the user's messages but sends nothing, because
the human owns the reply obligation. Do not "fix" that silence.
"""

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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


class EchoLedger:
    """Bounded in-process record of Bella's own outgoing sends.

    Distinguishes Bella's own from-me webhook echoes from a human typing
    into the same chat (ADR 0003, consequence 1). The expected outgoing
    (recipient, text) is registered *before* the send call, and the
    provider message ID is filled in once the call returns. The
    (recipient, text) registration stays live until an inbound echo
    actually consumes it — matching by id is just the fast path; an echo
    that beats the send response still matches by (recipient, text).

    Not persisted, and bounded like RefusalRotation above: a miss after
    eviction or a restart mis-reads one echo as human and pauses one
    conversation for one window — a bounded, invisible failure accepted
    by design.
    """

    def __init__(self, capacity: int = 2048) -> None:
        self._capacity = capacity
        self._pending: OrderedDict[tuple[str, str], int] = OrderedDict()
        self._ids: OrderedDict[str, tuple[str, str]] = OrderedDict()

    def register(self, recipient: str, text: str) -> tuple[str, str]:
        key = (recipient, text)
        self._pending[key] = self._pending.get(key, 0) + 1
        self._pending.move_to_end(key)
        while len(self._pending) > self._capacity:
            self._pending.popitem(last=False)
        return key

    def cancel(self, key: tuple[str, str]) -> None:
        """Release a registration whose send call failed before returning an id."""
        self._release_pending(key)

    def record_id(self, key: tuple[str, str], message_id: str) -> None:
        self._ids[message_id] = key
        self._ids.move_to_end(message_id)
        while len(self._ids) > self._capacity:
            self._ids.popitem(last=False)

    def is_own_echo(self, message_id: str, recipient: str, text: str | None) -> bool:
        key = self._ids.pop(message_id, None)
        if key is not None:
            self._release_pending(key)
            return True
        if text is None:
            return False
        return self._release_pending((recipient, text))

    def _release_pending(self, key: tuple[str, str]) -> bool:
        count = self._pending.get(key, 0)
        if count <= 0:
            return False
        if count == 1:
            del self._pending[key]
        else:
            self._pending[key] = count - 1
        return True


def _current_time() -> datetime:
    return datetime.now(UTC)


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
    text: str
    already_sent: bool = False  # the apostila path sends its own document
    needs_handoff: bool = False


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
        takeover_pause_seconds: int = 3600,
        takeover_clock: Callable[[], datetime] = _current_time,
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
        self._echo_ledger = EchoLedger()
        self._takeover_pause_window = timedelta(seconds=takeover_pause_seconds)
        self._clock = takeover_clock

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
        if message.is_group:
            # Bella never speaks in groups (spec story 24), from-me or not.
            # Full input policy lands in ticket 09, but this guard must
            # precede deployment.
            return
        if not await self._conversation_store.claim_delivery(message.message_id):
            logger.info("duplicate delivery ignored: %s", message.message_id)
            return
        if message.is_from_me:
            await self._handle_takeover_signal(message)
            return
        if await self._pause_active(message.number):
            # The human owns this conversation's reply obligation (ADR 0003):
            # store text for context, but no Scope Gate, no LLM, no canned
            # reply, no rate-limit notice. Checked before the rate limiter so
            # a pause-era message never feeds its accounting.
            if message.text is not None:
                await self._conversation_store.append_message(
                    message.number,
                    ConversationMessage("user", message.text, datetime.now(UTC)),
                )
            logger.info(
                "takeover pause active, no reply sent: %s", message.message_id
            )
            return
        rate_limit = self._rate_limiter.check(message.number)
        if rate_limit is RateLimitDecision.SILENCE:
            logger.info("rate-limited message silenced: %s", message.message_id)
            return
        language = detect_reply_language(message.text)
        if rate_limit is RateLimitDecision.NOTIFY:
            await self._send_text(
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
            await self._send_text(
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
            plan = ReplyPlan(self._canned_replies.reply("error_reply", language))
        if not plan.already_sent:
            await self._send_text(message.number, plan.text)
        await self._conversation_store.append_message(
            message.number,
            ConversationMessage("assistant", plan.text, datetime.now(UTC)),
        )
        if plan.needs_handoff:
            await self._notify_admin(message.number, message.text)
        logger.info("replied to %s (message %s)", message.number, message.message_id)

    async def _handle_takeover_signal(self, message: InboundMessage) -> None:
        """A from-me message is either Bella's own echo or a human typing in.

        The Owner role and its storage land in ticket 03; here a genuine
        Takeover message only sets/extends the pause.
        """
        if self._echo_ledger.is_own_echo(
            message.message_id, message.number, message.text
        ):
            return
        until = self._clock() + self._takeover_pause_window
        await self._conversation_store.set_pause(message.number, until)
        logger.info("takeover pause set for %s until %s", message.number, until)

    async def _pause_active(self, phone_number: str) -> bool:
        until = await self._conversation_store.paused_until(phone_number)
        return until is not None and until > self._clock()

    async def _send_text(self, number: str, text: str) -> None:
        """Every send to a user chat is registered before the call so a
        webhook echo that beats the send response still matches by
        (recipient, text) (ADR 0003, consequence 1)."""
        key = self._echo_ledger.register(number, text)
        try:
            message_id = await self._sender.send_text(number, text)
        except Exception:
            self._echo_ledger.cancel(key)
            raise
        self._echo_ledger.record_id(key, message_id)

    async def _send_document(self, number: str, path: Path, caption: str) -> None:
        key = self._echo_ledger.register(number, caption)
        try:
            message_id = await self._sender.send_document(number, path, caption)
        except Exception:
            self._echo_ledger.cancel(key)
            raise
        self._echo_ledger.record_id(key, message_id)

    async def _notify_admin(self, user_number: str, summary: str) -> None:
        if not self._admin_contact or user_number == self._admin_contact:
            return
        notification = (
            "Handoff Bella\n"
            f"Usuario: {user_number}\n"
            f"Pedido: {summary[:500]}"
        )
        try:
            await self._send_text(self._admin_contact, notification)
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
            return ReplyPlan(self._refusals.take(number))
        if category is RouteCategory.HUMAN_REQUESTED:
            contact = self._human_contact_reply
            if language is not ReplyLanguage.PORTUGUESE:
                intro = self._canned_replies.reply("human_contact_intro", language)
                contact = f"{intro}\n{contact}"
            return ReplyPlan(contact, needs_handoff=True)
        if category is RouteCategory.APOSTILA_REQUEST:
            if not self._apostila_path.is_file():
                return ReplyPlan(
                    self._canned_replies.reply("apostila_soon_reply", language)
                )
            caption = self._canned_replies.reply("apostila_caption", language)
            try:
                await self._send_document(
                    number,
                    self._apostila_path,
                    caption,
                )
            except Exception:
                logger.exception("failed to send apostila to %s", number)
                return ReplyPlan(
                    self._canned_replies.reply("apostila_error_reply", language)
                )
            return ReplyPlan(caption, already_sent=True)
        answer = await self._answerer.answer(text, category, history)
        reply_text = answer.text
        if answer.needs_handoff:
            heading = self._canned_replies.reply("human_contact_intro", language)
            reply_text = (
                f"{reply_text}\n\n{heading}\n{self._human_contact_reply}"
            )
        return ReplyPlan(
            strip_foreign_urls(reply_text, self._enrollment_url),
            needs_handoff=answer.needs_handoff,
        )
