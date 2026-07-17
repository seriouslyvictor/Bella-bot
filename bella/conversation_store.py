"""Conversation history and webhook delivery persistence contracts."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, cast

from psycopg_pool import AsyncConnectionPool

from bella.database import require_database_name

HISTORY_LIMIT = 50

MessageRole = Literal["user", "assistant", "owner"]


@dataclass(frozen=True)
class ConversationMessage:
    role: MessageRole
    text: str
    timestamp: datetime


class ConversationStore(Protocol):
    async def start(self) -> None: ...

    async def close(self) -> None: ...

    async def check_health(self) -> None: ...

    async def claim_delivery(self, message_id: str) -> bool: ...

    async def append_message(
        self, phone_number: str, message: ConversationMessage
    ) -> None: ...

    async def recent_messages(
        self, phone_number: str, limit: int = HISTORY_LIMIT
    ) -> list[ConversationMessage]: ...

    async def delete_conversations_idle_before(self, cutoff: datetime) -> int: ...

    # Every from-me echo claims a delivery row too (load-bearing dedupe), so
    # webhook_deliveries needs its own pruning independent of conversations.
    async def delete_deliveries_before(self, cutoff: datetime) -> int: ...

    # Takeover Pause state (ADR 0003). A conversation may have no prior
    # messages when a pause is first set, so set_pause must create the
    # conversation record rather than assume it exists.
    async def paused_until(self, phone_number: str) -> datetime | None: ...

    async def set_pause(self, phone_number: str, until: datetime) -> None: ...

    async def clear_pause(self, phone_number: str) -> None: ...


class InMemoryConversationStore:
    """Process-local store implementing the production persistence contract."""

    def __init__(self) -> None:
        self._messages: dict[str, list[ConversationMessage]] = defaultdict(list)
        self._delivery_ids: dict[str, datetime] = {}
        self._paused_until: dict[str, datetime] = {}

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def check_health(self) -> None:
        pass

    async def claim_delivery(self, message_id: str) -> bool:
        if message_id in self._delivery_ids:
            return False
        self._delivery_ids[message_id] = datetime.now(UTC)
        return True

    async def append_message(
        self, phone_number: str, message: ConversationMessage
    ) -> None:
        self._messages[phone_number].append(message)

    async def recent_messages(
        self, phone_number: str, limit: int = HISTORY_LIMIT
    ) -> list[ConversationMessage]:
        return self._messages[phone_number][-limit:]

    async def delete_conversations_idle_before(self, cutoff: datetime) -> int:
        idle_numbers = [
            phone_number
            for phone_number, messages in self._messages.items()
            if messages and max(message.timestamp for message in messages) < cutoff
        ]
        for phone_number in idle_numbers:
            del self._messages[phone_number]
            self._paused_until.pop(phone_number, None)
        return len(idle_numbers)

    async def delete_deliveries_before(self, cutoff: datetime) -> int:
        expired_ids = [
            message_id
            for message_id, received_at in self._delivery_ids.items()
            if received_at < cutoff
        ]
        for message_id in expired_ids:
            del self._delivery_ids[message_id]
        return len(expired_ids)

    async def paused_until(self, phone_number: str) -> datetime | None:
        return self._paused_until.get(phone_number)

    async def set_pause(self, phone_number: str, until: datetime) -> None:
        self._paused_until[phone_number] = until

    async def clear_pause(self, phone_number: str) -> None:
        self._paused_until.pop(phone_number, None)


_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS conversations (
        phone_number TEXT PRIMARY KEY,
        last_message_at TIMESTAMPTZ NOT NULL,
        paused_until TIMESTAMPTZ
    )
    """,
    # ADD COLUMN IF NOT EXISTS makes this safe to re-run against a database
    # created by the previous schema version, which had no paused_until
    # column; the CREATE TABLE above already covers fresh databases.
    """
    ALTER TABLE conversations
        ADD COLUMN IF NOT EXISTS paused_until TIMESTAMPTZ
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation_messages (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        phone_number TEXT NOT NULL
            REFERENCES conversations(phone_number) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'owner')),
        text TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS conversation_messages_recent
        ON conversation_messages (phone_number, created_at DESC, id DESC)
    """,
    # The role CHECK above is inline and unnamed, so Postgres auto-names it
    # conversation_messages_role_check on both the fresh-database CREATE
    # TABLE and any pre-ticket-03 database. Plain ADD CONSTRAINT has no IF
    # NOT EXISTS, so drop-then-add (safe to repeat every start, same spirit
    # as the ADD COLUMN IF NOT EXISTS above) is the idempotent way to widen
    # an existing deployment's constraint to accept the Owner role.
    """
    ALTER TABLE conversation_messages
        DROP CONSTRAINT IF EXISTS conversation_messages_role_check
    """,
    """
    ALTER TABLE conversation_messages
        ADD CONSTRAINT conversation_messages_role_check
            CHECK (role IN ('user', 'assistant', 'owner'))
    """,
    """
    CREATE TABLE IF NOT EXISTS webhook_deliveries (
        message_id TEXT PRIMARY KEY,
        received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
)


class PostgresConversationStore:
    """Postgres-backed conversation history and atomic delivery dedupe."""

    def __init__(
        self,
        database_url: str,
        *,
        required_database_name: str | None = None,
    ) -> None:
        if required_database_name is not None:
            require_database_name(
                database_url,
                required_database_name,
                setting_name="Bella's runtime database URL",
            )
        self._pool = AsyncConnectionPool(
            database_url,
            min_size=1,
            max_size=5,
            open=False,
            name="bella-conversations",
        )

    async def start(self) -> None:
        await self._pool.open(wait=True)
        async with self._pool.connection() as connection:
            for statement in _SCHEMA_STATEMENTS:
                await connection.execute(statement)

    async def close(self) -> None:
        await self._pool.close()

    async def check_health(self) -> None:
        # Bound pool acquisition so a readiness probe cannot hang behind a
        # failed database longer than the container health-check timeout.
        async with self._pool.connection(timeout=3) as connection:
            await connection.execute("SELECT 1")

    async def claim_delivery(self, message_id: str) -> bool:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO webhook_deliveries (message_id)
                VALUES (%s)
                ON CONFLICT DO NOTHING
                """,
                (message_id,),
            )
            return cursor.rowcount == 1

    async def append_message(
        self, phone_number: str, message: ConversationMessage
    ) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                INSERT INTO conversations (phone_number, last_message_at)
                VALUES (%s, %s)
                ON CONFLICT (phone_number) DO UPDATE
                SET last_message_at = GREATEST(
                    conversations.last_message_at,
                    EXCLUDED.last_message_at
                )
                """,
                (phone_number, message.timestamp),
            )
            await connection.execute(
                """
                INSERT INTO conversation_messages
                    (phone_number, role, text, created_at)
                VALUES (%s, %s, %s, %s)
                """,
                (phone_number, message.role, message.text, message.timestamp),
            )

    async def recent_messages(
        self, phone_number: str, limit: int = HISTORY_LIMIT
    ) -> list[ConversationMessage]:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT role, text, created_at
                FROM conversation_messages
                WHERE phone_number = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (phone_number, limit),
            )
            rows = await cursor.fetchall()
        return [
            ConversationMessage(cast(MessageRole, role), text, timestamp)
            for role, text, timestamp in reversed(rows)
        ]

    async def delete_conversations_idle_before(self, cutoff: datetime) -> int:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                DELETE FROM conversations
                WHERE last_message_at < %s
                RETURNING phone_number
                """,
                (cutoff,),
            )
            removed = await cursor.fetchall()
        return len(removed)

    async def delete_deliveries_before(self, cutoff: datetime) -> int:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                DELETE FROM webhook_deliveries
                WHERE received_at < %s
                RETURNING message_id
                """,
                (cutoff,),
            )
            removed = await cursor.fetchall()
        return len(removed)

    async def paused_until(self, phone_number: str) -> datetime | None:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                "SELECT paused_until FROM conversations WHERE phone_number = %s",
                (phone_number,),
            )
            row = await cursor.fetchone()
        return row[0] if row is not None else None

    async def set_pause(self, phone_number: str, until: datetime) -> None:
        async with self._pool.connection() as connection:
            # The conversation row may not exist yet (a takeover can be the
            # first activity in a chat), and last_message_at is NOT NULL, so
            # this upsert supplies the DB wall clock as that placeholder on
            # insert; an existing row's last_message_at is left untouched.
            await connection.execute(
                """
                INSERT INTO conversations (phone_number, last_message_at, paused_until)
                VALUES (%s, CURRENT_TIMESTAMP, %s)
                ON CONFLICT (phone_number) DO UPDATE
                SET paused_until = EXCLUDED.paused_until
                """,
                (phone_number, until),
            )

    async def clear_pause(self, phone_number: str) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                "UPDATE conversations SET paused_until = NULL WHERE phone_number = %s",
                (phone_number,),
            )
