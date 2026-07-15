"""The per-message pipeline: safety checks, then a reply.

The brain is a placeholder for now — the Scope Gate arrives in ticket 04 and
real answering in ticket 05. This module owns the safety invariants that must
hold from day one: never reply to ourselves, never reply twice to the same
delivery, never let a processing error escape (the webhook was already acked).
"""

import logging
from collections import OrderedDict

from bella.evolution import InboundMessage, WhatsAppSender

logger = logging.getLogger("bella")

SKELETON_REPLY = (
    "Oi! 👋 Eu sou a Bella, assistente do curso de IA Generativa do SENAI. "
    "Ainda estou em construção, mas já recebi sua mensagem: “{text}”"
)


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


class Pipeline:
    def __init__(self, sender: WhatsAppSender) -> None:
        self._sender = sender
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

        reply = SKELETON_REPLY.format(text=message.text)
        await self._sender.send_text(message.number, reply)
        logger.info("replied to %s (message %s)", message.number, message.message_id)
