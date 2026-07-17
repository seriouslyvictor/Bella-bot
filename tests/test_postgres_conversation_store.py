"""Integration tests for the storage contract against a disposable Postgres."""

import asyncio
import os
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import psycopg
import pytest

from bella.conversation_store import ConversationMessage, PostgresConversationStore

DATABASE_URL = os.environ.get("BELLA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    DATABASE_URL is None,
    reason="BELLA_TEST_DATABASE_URL is not configured for a disposable Postgres",
)


def run_async(coroutine: Coroutine[Any, Any, None]) -> None:
    """Use the event loop psycopg supports on Windows as well as Linux."""
    with asyncio.Runner(loop_factory=asyncio.SelectorEventLoop) as runner:
        runner.run(coroutine)


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

    run_async(exercise())


def test_postgres_pause_can_be_set_read_cleared_and_survives_restart() -> None:
    async def exercise() -> None:
        assert DATABASE_URL is not None
        phone_number = f"test-{uuid4()}"
        until = datetime(2026, 7, 16, 13, 0, tzinfo=UTC)

        first_store = PostgresConversationStore(DATABASE_URL)
        await first_store.start()
        try:
            assert await first_store.paused_until(phone_number) is None
            await first_store.set_pause(phone_number, until)
        finally:
            await first_store.close()

        restarted_store = PostgresConversationStore(DATABASE_URL)
        await restarted_store.start()
        try:
            assert await restarted_store.paused_until(phone_number) == until
            await restarted_store.clear_pause(phone_number)
            assert await restarted_store.paused_until(phone_number) is None
        finally:
            await restarted_store.close()

    run_async(exercise())


def test_postgres_pause_can_be_set_for_a_conversation_with_no_prior_messages() -> None:
    async def exercise() -> None:
        assert DATABASE_URL is not None
        phone_number = f"test-{uuid4()}"
        until = datetime(2026, 7, 16, 13, 0, tzinfo=UTC)

        store = PostgresConversationStore(DATABASE_URL)
        await store.start()
        try:
            await store.set_pause(phone_number, until)
            assert await store.paused_until(phone_number) == until
            assert await store.recent_messages(phone_number) == []
        finally:
            await store.close()

    run_async(exercise())


def test_postgres_delete_deliveries_before_prunes_only_older_claims() -> None:
    async def exercise() -> None:
        assert DATABASE_URL is not None
        store = PostgresConversationStore(DATABASE_URL)
        await store.start()
        try:
            # Clear any deliveries a previous run against this database left
            # behind, so this test only sees the two ids it claims below.
            await store.delete_deliveries_before(datetime(9999, 1, 1, tzinfo=UTC))
            old_id = f"delivery-old-{uuid4()}"
            recent_id = f"delivery-recent-{uuid4()}"
            assert await store.claim_delivery(old_id) is True
            assert await store.claim_delivery(recent_id) is True

            before_claims = datetime.now(UTC) - timedelta(days=1)
            assert await store.delete_deliveries_before(before_claims) == 0

            after_claims = datetime.now(UTC) + timedelta(days=1)
            removed = await store.delete_deliveries_before(after_claims)

            assert removed == 2
            assert await store.claim_delivery(old_id) is True
            assert await store.claim_delivery(recent_id) is True
        finally:
            await store.close()

    run_async(exercise())


def test_postgres_schema_migration_adds_paused_until_to_an_existing_table() -> None:
    """Simulates a database created by the previous schema version (before
    paused_until existed) — the current schema statements must still apply
    cleanly on top of it (ADR 0003)."""

    async def exercise() -> None:
        assert DATABASE_URL is not None
        # Get a table into the pre-migration shape without going through the
        # store, so this only pins the migration's behavior, not its SQL.
        async with await psycopg.AsyncConnection.connect(DATABASE_URL) as connection:
            await connection.execute(
                "CREATE TABLE IF NOT EXISTS conversations ("
                "  phone_number TEXT PRIMARY KEY,"
                "  last_message_at TIMESTAMPTZ NOT NULL"
                ")"
            )
            await connection.execute(
                "ALTER TABLE conversations DROP COLUMN IF EXISTS paused_until"
            )
            await connection.commit()

        migrated_store = PostgresConversationStore(DATABASE_URL)
        await migrated_store.start()  # must not raise applying the new column
        try:
            phone_number = f"test-{uuid4()}"
            until = datetime(2026, 7, 16, 13, 0, tzinfo=UTC)
            await migrated_store.set_pause(phone_number, until)
            assert await migrated_store.paused_until(phone_number) == until
        finally:
            await migrated_store.close()

    run_async(exercise())


def test_postgres_schema_migration_widens_role_check_to_accept_owner() -> None:
    """Simulates a database created by the previous schema version (role
    CHECK limited to user/assistant) — the current schema statements must
    widen the constraint in place, not just on a fresh CREATE TABLE
    (ticket 03)."""

    async def exercise() -> None:
        assert DATABASE_URL is not None
        async with await psycopg.AsyncConnection.connect(DATABASE_URL) as connection:
            await connection.execute(
                "CREATE TABLE IF NOT EXISTS conversations ("
                "  phone_number TEXT PRIMARY KEY,"
                "  last_message_at TIMESTAMPTZ NOT NULL,"
                "  paused_until TIMESTAMPTZ"
                ")"
            )
            await connection.execute(
                "CREATE TABLE IF NOT EXISTS conversation_messages ("
                "  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,"
                "  phone_number TEXT NOT NULL"
                "    REFERENCES conversations(phone_number) ON DELETE CASCADE,"
                "  role TEXT NOT NULL,"
                "  text TEXT NOT NULL,"
                "  created_at TIMESTAMPTZ NOT NULL"
                ")"
            )
            # Force the pre-ticket-03 constraint shape regardless of what an
            # earlier test run against this database left behind.
            await connection.execute(
                "ALTER TABLE conversation_messages "
                "DROP CONSTRAINT IF EXISTS conversation_messages_role_check"
            )
            await connection.execute(
                "ALTER TABLE conversation_messages "
                "ADD CONSTRAINT conversation_messages_role_check "
                "CHECK (role IN ('user', 'assistant'))"
            )
            await connection.commit()

        migrated_store = PostgresConversationStore(DATABASE_URL)
        await migrated_store.start()  # must not raise widening the constraint
        try:
            phone_number = f"test-{uuid4()}"
            await migrated_store.append_message(
                phone_number,
                ConversationMessage(
                    "owner", "eu assumo daqui", datetime(2026, 7, 16, tzinfo=UTC)
                ),
            )
            history = await migrated_store.recent_messages(phone_number)
            assert [m.role for m in history] == ["owner"]
        finally:
            await migrated_store.close()

    run_async(exercise())


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

    run_async(exercise())
