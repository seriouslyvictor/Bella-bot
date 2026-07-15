import asyncio
import logging
from datetime import UTC, datetime, timedelta

import pytest

from bella.conversation_store import ConversationMessage, InMemoryConversationStore
from bella.retention import delete_expired_conversations


def test_retention_logs_the_number_of_idle_conversations_removed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def exercise() -> None:
        store = InMemoryConversationStore()
        now = datetime(2026, 7, 15, tzinfo=UTC)
        await store.append_message(
            "old",
            ConversationMessage("user", "olá", now - timedelta(days=121)),
        )

        with caplog.at_level(logging.INFO, logger="bella"):
            removed = await delete_expired_conversations(store, now=now)

        assert removed == 1
        assert (
            "retention removed 1 conversation(s) idle for more than 120 days"
            in caplog.text
        )

    asyncio.run(exercise())
