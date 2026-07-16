import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from bella.conversation_store import (
    ConversationMessage,
    InMemoryConversationStore,
    PostgresConversationStore,
)


def test_recent_history_returns_the_last_50_messages_in_order() -> None:
    async def exercise() -> None:
        store = InMemoryConversationStore()
        started_at = datetime(2026, 1, 1, tzinfo=UTC)

        for index in range(55):
            await store.append_message(
                "5511999999999",
                ConversationMessage(
                    role="user",
                    text=f"message {index}",
                    timestamp=started_at + timedelta(minutes=index),
                ),
            )

        history = await store.recent_messages("5511999999999")

        assert [message.text for message in history] == [
            f"message {index}" for index in range(5, 55)
        ]

    asyncio.run(exercise())


def test_retention_deletes_only_conversations_idle_for_more_than_120_days() -> None:
    async def exercise() -> None:
        store = InMemoryConversationStore()
        cutoff = datetime(2026, 3, 17, tzinfo=UTC)
        cases = [
            ("old", cutoff - timedelta(seconds=1)),
            ("boundary", cutoff),
            ("active", cutoff + timedelta(days=30)),
        ]
        for phone_number, timestamp in cases:
            await store.append_message(
                phone_number,
                ConversationMessage("user", phone_number, timestamp),
            )

        removed = await store.delete_conversations_idle_before(cutoff)

        assert removed == 1
        assert await store.recent_messages("old") == []
        assert [
            message.text for message in await store.recent_messages("boundary")
        ] == ["boundary"]
        assert [message.text for message in await store.recent_messages("active")] == [
            "active"
        ]

    asyncio.run(exercise())


def test_production_store_refuses_to_connect_to_an_evolution_database() -> None:
    with pytest.raises(ValueError, match="must point to the 'bella' database"):
        PostgresConversationStore(
            "postgresql://postgres:secret@postgres:5432/evolution",
            required_database_name="bella",
        )


def test_pause_can_be_set_read_and_cleared() -> None:
    async def exercise() -> None:
        store = InMemoryConversationStore()
        assert await store.paused_until("5511999999999") is None

        until = datetime(2026, 7, 16, 13, 0, tzinfo=UTC)
        await store.set_pause("5511999999999", until)
        assert await store.paused_until("5511999999999") == until

        extended = until + timedelta(minutes=30)
        await store.set_pause("5511999999999", extended)
        assert await store.paused_until("5511999999999") == extended

        await store.clear_pause("5511999999999")
        assert await store.paused_until("5511999999999") is None

    asyncio.run(exercise())


def test_pause_can_be_set_for_a_conversation_with_no_prior_messages() -> None:
    async def exercise() -> None:
        store = InMemoryConversationStore()
        until = datetime(2026, 7, 16, 13, 0, tzinfo=UTC)

        await store.set_pause("5511999999999", until)

        assert await store.paused_until("5511999999999") == until
        assert await store.recent_messages("5511999999999") == []

    asyncio.run(exercise())
