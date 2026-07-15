"""Integration tests for the storage contract against a disposable Postgres."""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from bella.conversation_store import ConversationMessage, PostgresConversationStore

DATABASE_URL = os.environ.get("BELLA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    DATABASE_URL is None,
    reason="BELLA_TEST_DATABASE_URL is not configured for a disposable Postgres",
)


def test_postgres_history_and_dedupe_survive_store_restart() -> None:
    async def exercise() -> None:
        assert DATABASE_URL is not None
        phone_number = f"test-{uuid4()}"
        message_id = f"delivery-{uuid4()}"
        started_at = datetime(2026, 1, 1, tzinfo=UTC)

        first_store = PostgresConversationStore(DATABASE_URL)
        await first_store.start()
        try:
            for index in range(55):
                await first_store.append_message(
                    phone_number,
                    ConversationMessage(
                        "user",
                        f"message {index}",
                        started_at + timedelta(minutes=index),
                    ),
                )
            assert await first_store.claim_delivery(message_id) is True
        finally:
            await first_store.close()

        restarted_store = PostgresConversationStore(DATABASE_URL)
        await restarted_store.start()
        try:
            history = await restarted_store.recent_messages(phone_number)
            assert [message.text for message in history] == [
                f"message {index}" for index in range(5, 55)
            ]
            assert await restarted_store.claim_delivery(message_id) is False
        finally:
            await restarted_store.close()

    asyncio.run(exercise())


def test_postgres_retention_deletes_only_idle_conversations() -> None:
    async def exercise() -> None:
        assert DATABASE_URL is not None
        store = PostgresConversationStore(DATABASE_URL)
        await store.start()
        try:
            await store.delete_conversations_idle_before(
                datetime(9999, 1, 1, tzinfo=UTC)
            )
            cutoff = datetime(2026, 3, 17, tzinfo=UTC)
            cases = [
                ("old", cutoff - timedelta(seconds=1)),
                ("boundary", cutoff),
                ("active", cutoff + timedelta(days=1)),
            ]
            phone_numbers: dict[str, str] = {}
            for label, timestamp in cases:
                phone_number = f"test-{label}-{uuid4()}"
                phone_numbers[label] = phone_number
                await store.append_message(
                    phone_number,
                    ConversationMessage("user", label, timestamp),
                )

            removed = await store.delete_conversations_idle_before(cutoff)

            assert removed == 1
            assert await store.recent_messages(phone_numbers["old"]) == []
            assert len(await store.recent_messages(phone_numbers["boundary"])) == 1
            assert len(await store.recent_messages(phone_numbers["active"])) == 1
        finally:
            await store.close()

    asyncio.run(exercise())
