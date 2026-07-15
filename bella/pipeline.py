"""The per-message pipeline: safety checks, Scope Gate, then a guarded reply.

This module owns the invariants that must hold from day one: never reply to
ourselves, never reply twice to the same delivery, always send the user a
reply, and never let a processing error escape after the webhook has already
been acknowledged.
"""

import logging
from collections import OrderedDict
from collections.abc import Sequence
from typing import Protocol

from bella.answer_guard import strip_foreign_urls
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
    async def answer(self, text: str, category: RouteCategory) -> str: ...


class Pipeline:
    def __init__(
        self,
        sender: WhatsAppSender,
        scope_gate: ScopeGate,
        answerer: Answerer,
        canned_replies: CannedReplies,
        enrollment_url: str,
    ) -> None:
        self._sender = sender
        self._scope_gate = scope_gate
        self._answerer = answerer
        self._canned_replies = canned_replies
        self._enrollment_url = enrollment_url
        self._refusals = RefusalRotation(canned_replies.refusals)
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
            reply = await self._reply_for(message.text, message.number)
        except Exception:
            # Guards the whole reply-producing step, not just one stage of it:
            # every stage added here must degrade to a reply, never to silence.
            logger.exception("reply production failed for %s", message.message_id)
            reply = self._canned_replies.error_reply
        await self._sender.send_text(message.number, reply)
        logger.info("replied to %s (message %s)", message.number, message.message_id)

    async def _reply_for(self, text: str, number: str) -> str:
        category = await self._scope_gate.classify(text)
        if category is RouteCategory.OUT_OF_SCOPE:
            return self._refusals.take(number)
        answer = await self._answerer.answer(text, category)
        return strip_foreign_urls(answer, self._enrollment_url)
