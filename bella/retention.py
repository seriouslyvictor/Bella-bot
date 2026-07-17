"""Scheduled cleanup for idle Bella conversations."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from bella.conversation_store import ConversationStore

logger = logging.getLogger("bella")

RETENTION_DAYS = 120
RETENTION_INTERVAL_SECONDS = 24 * 60 * 60

# Webhook redelivery happens within minutes/hours, so deliveries only need a
# short horizon — far shorter than conversation retention.
DELIVERY_RETENTION = timedelta(days=7)


async def delete_expired_conversations(
    store: ConversationStore,
    *,
    now: datetime | None = None,
) -> int:
    reference_time = now or datetime.now(UTC)
    cutoff = reference_time - timedelta(days=RETENTION_DAYS)
    removed = await store.delete_conversations_idle_before(cutoff)
    logger.info(
        "retention removed %s conversation(s) idle for more than %s days",
        removed,
        RETENTION_DAYS,
    )
    return removed


async def delete_expired_deliveries(
    store: ConversationStore,
    *,
    now: datetime | None = None,
) -> int:
    reference_time = now or datetime.now(UTC)
    cutoff = reference_time - DELIVERY_RETENTION
    removed = await store.delete_deliveries_before(cutoff)
    logger.info(
        "retention removed %s webhook delivery id(s) older than %s days",
        removed,
        DELIVERY_RETENTION.days,
    )
    return removed


async def run_retention_job(store: ConversationStore) -> None:
    while True:
        try:
            await delete_expired_conversations(store)
            await delete_expired_deliveries(store)
        except Exception:
            logger.exception("conversation retention job failed")
        await asyncio.sleep(RETENTION_INTERVAL_SECONDS)
