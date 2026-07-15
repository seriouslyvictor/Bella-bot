"""The per-message pipeline: safety checks, Scope Gate, then a guarded reply.

This module owns the invariants that must hold from day one: never reply to
ourselves, never reply twice to the same delivery, and never let a processing
error escape after the webhook has already been acknowledged.
"""

import logging
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from bella.answer_guard import AllowedUrlGuard
from bella.canned_replies import CannedReplies
from bella.evolution import InboundMessage, WhatsAppSender
from bella.scope_gate import RouteCategory, ScopeGate

logger = logging.getLogger("bella")


class RecentMessageIds:
    """Bounded in-memory dedupe of webhook deliveries (Postgres in ticket 06)."""

    def __init__(self, capacity: int = 2048) -> None:
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._capacity = capacity

    def check_and_record(self, message_id: str) -> bool:
        """Return True if already seen; otherwise record it and return False."""
        if message_id in self._seen:
            self._seen.move_to_end(message_id)
            return True
        self._seen[message_id] = None
        if len(self._seen) > self._capacity:
            self._seen.popitem(last=False)
        return False


@dataclass(frozen=True)
class ConversationTurn:
    role: Literal["user", "assistant"]
    text: str


class Answerer(Protocol):
    async def answer(
        self,
        text: str,
        category: RouteCategory,
        history: Sequence[ConversationTurn] = (),
    ) -> str: ...


class Pipeline:
    def __init__(
        self,
        sender: WhatsAppSender,
        scope_gate: ScopeGate,
        answerer: Answerer,
        canned_replies: CannedReplies,
        answer_guard: AllowedUrlGuard,
    ) -> None:
        self._sender = sender
        self._scope_gate = scope_gate
        self._answerer = answerer
        self._canned_replies = canned_replies
        self._answer_guard = answer_guard
        self._recent = RecentMessageIds()

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
        if self._recent.check_and_record(message.message_id):
            logger.info("duplicate delivery ignored: %s", message.message_id)
            return
        if message.text is None:
            logger.info(
                "non-text message ignored: %s (type=%s)",
                message.message_id,
                message.message_type,
            )
            return

        try:
            category = await self._scope_gate.classify(message.text)
        except Exception:
            logger.exception("Scope Gate failed for message %s", message.message_id)
            await self._sender.send_text(message.number, self._canned_replies.error_reply)
            return

        if category is RouteCategory.OUT_OF_SCOPE:
            reply = self._canned_replies.take_refusal(message.number)
        else:
            reply = await self._answerer.answer(message.text, category)
            reply = self._answer_guard.apply(reply)
        await self._sender.send_text(message.number, reply)
        logger.info("replied to %s (message %s)", message.number, message.message_id)
