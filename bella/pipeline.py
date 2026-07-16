"""The per-message pipeline: safety checks, Scope Gate, then a guarded reply.

This module owns the invariants that must hold from day one: never reply to
ourselves, never reply twice to the same delivery, always send the user a
reply, and never let a processing error escape after the webhook has already
been acknowledged.
"""

import asyncio
import logging
from collections import OrderedDict
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from bella.answer_guard import strip_foreign_urls
from bella.canned_replies import CannedReplies
from bella.conversation_store import (
    ConversationMessage,
    ConversationStore,
)
from bella.evolution import InboundMessage, WhatsAppSender
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


class Answerer(Protocol):
    async def answer(
        self,
        text: str,
        category: RouteCategory,
        history: Sequence[ConversationMessage],
    ) -> str: ...


class Pipeline:
    def __init__(
        self,
        sender: WhatsAppSender,
        scope_gate: ScopeGate,
        answerer: Answerer,
        canned_replies: CannedReplies,
        enrollment_url: str,
        conversation_store: ConversationStore,
    ) -> None:
        self._sender = sender
        self._scope_gate = scope_gate
        self._answerer = answerer
        self._canned_replies = canned_replies
        self._enrollment_url = enrollment_url
        self._conversation_store = conversation_store
        self._refusals = RefusalRotation(canned_replies.refusals)

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
        if message.text is None:
            logger.info(
                "non-text message ignored: %s (type=%s)",
                message.message_id,
                message.message_type,
            )
            return

        history = await self._conversation_store.recent_messages(message.number)
        await self._conversation_store.append_message(
            message.number,
            ConversationMessage("user", message.text, datetime.now(UTC)),
        )
        try:
            reply = await self._reply_for(message.text, message.number, history)
        except Exception:
            # Guards the whole reply-producing step, not just one stage of it:
            # every stage added here must degrade to a reply, never to silence.
            logger.exception("reply production failed for %s", message.message_id)
            reply = self._canned_replies.error_reply
        await self._sender.send_text(message.number, reply)
        await self._conversation_store.append_message(
            message.number,
            ConversationMessage("assistant", reply, datetime.now(UTC)),
        )
        logger.info("replied to %s (message %s)", message.number, message.message_id)

    async def _reply_for(
        self,
        text: str,
        number: str,
        history: Sequence[ConversationMessage],
    ) -> str:
        category = await self._scope_gate.classify(text)
        if category is RouteCategory.OUT_OF_SCOPE:
            return self._refusals.take(number)
        answer = await self._answerer.answer(text, category, history)
        return strip_foreign_urls(answer, self._enrollment_url)
