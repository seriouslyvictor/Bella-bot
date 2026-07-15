"""Conversation history and webhook delivery persistence contracts."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, cast

from psycopg.conninfo import conninfo_to_dict
from psycopg_pool import AsyncConnectionPool

HISTORY_LIMIT = 50

MessageRole = Literal["user", "assistant"]


@dataclass(frozen=True)
class ConversationMessage:
    role: MessageRole
    text: str
    timestamp: datetime


class ConversationStore(Protocol):
    async def start(self) -> None: ...

    async def close(self) -> None: ...

    async def claim_delivery(self, message_id: str) -> bool: ...

    async def append_message(
        self, phone_number: str, message: ConversationMessage
    ) -> None: ...

    async def recent_messages(
        self, phone_number: str, limit: int = HISTORY_LIMIT
    ) -> list[ConversationMessage]: ...

    async def delete_conversations_idle_before(self, cutoff: datetime) -> int: ...


class InMemoryConversationStore:
    """Process-local store implementing the production persistence contract."""

    def __init__(self) -> None:
        self._messages: dict[str, list[ConversationMessage]] = defaultdict(list)
        self._delivery_ids: set[str] = set()

    async def start(self) -> None:
        pass

    async def close(self) -> None:
        pass

    async def claim_delivery(self, message_id: str) -> bool:
        if message_id in self._delivery_ids:
            return False
        self._delivery_ids.add(message_id)
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
        return len(idle_numbers)


_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS conversations (
        phone_number TEXT PRIMARY KEY,
        last_message_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS conversation_messages (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        phone_number TEXT NOT NULL
            REFERENCES conversations(phone_number) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
        text TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS conversation_messages_recent
        ON conversation_messages (phone_number, created_at DESC, id DESC)
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
        database_name = conninfo_to_dict(database_url).get("dbname")
        if required_database_name is not None and database_name != required_database_name:
            raise ValueError(
                f"Bella must use the {required_database_name!r} database, "
                f"not {database_name!r}"
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
