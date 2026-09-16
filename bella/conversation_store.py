"""Conversation history and webhook delivery persistence contracts."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, cast

from psycopg_pool import AsyncConnectionPool

from bella.database import require_database_name
from bella.feedback_collector import FeedbackDraft, FeedbackPhase

HISTORY_LIMIT = 50

MessageRole = Literal["user", "assistant", "owner"]


@dataclass(frozen=True)
class ConversationMessage:
    role: MessageRole
    text: str
    timestamp: datetime


@dataclass(frozen=True)
class StagedFeedback:
    id: int
    phone_number: str
    app_id: str
    title: str
    observed: str
    expected: str
    evidence: str
    created_at: datetime
    status: str = "staged"
    github_issue_url: str | None = None
    error_message: str | None = None


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

    async def get_feedback_draft(
        self, phone_number: str
    ) -> tuple[FeedbackPhase, FeedbackDraft | None]: ...

    async def set_feedback_draft(
        self,
        phone_number: str,
        phase: FeedbackPhase,
        draft: FeedbackDraft | None,
    ) -> None: ...

    async def clear_feedback_draft(self, phone_number: str) -> None: ...

    async def stage_feedback(
        self, phone_number: str, draft: FeedbackDraft
    ) -> int: ...

    async def get_unprocessed_feedback(
        self, limit: int = 10
    ) -> list[StagedFeedback]: ...

    async def mark_feedback_published(
        self, staged_id: int, github_issue_url: str
    ) -> None: ...

    async def mark_feedback_failed(
        self, staged_id: int, error_message: str
    ) -> None: ...


class InMemoryConversationStore:
    """Process-local store implementing the production persistence contract."""

    def __init__(self) -> None:
        self._messages: dict[str, list[ConversationMessage]] = defaultdict(list)
        self._delivery_ids: dict[str, datetime] = {}
        self._paused_until: dict[str, datetime] = {}
        self._feedback_drafts: dict[str, tuple[FeedbackPhase, FeedbackDraft | None]] = {}
        self._staged_feedback: dict[int, StagedFeedback] = {}
        self._next_staged_id: int = 1

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
            self._feedback_drafts.pop(phone_number, None)
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

    async def get_feedback_draft(
        self, phone_number: str
    ) -> tuple[FeedbackPhase, FeedbackDraft | None]:
        return self._feedback_drafts.get(phone_number, (FeedbackPhase.IDLE, None))

    async def set_feedback_draft(
        self,
        phone_number: str,
        phase: FeedbackPhase,
        draft: FeedbackDraft | None,
    ) -> None:
        self._feedback_drafts[phone_number] = (phase, draft)

    async def clear_feedback_draft(self, phone_number: str) -> None:
        self._feedback_drafts.pop(phone_number, None)

    async def stage_feedback(
        self, phone_number: str, draft: FeedbackDraft
    ) -> int:
        staged_id = self._next_staged_id
        self._next_staged_id += 1
        item = StagedFeedback(
            id=staged_id,
            phone_number=phone_number,
            app_id=draft.app_id,
            title=draft.title,
            observed=draft.observed,
            expected=draft.expected,
            evidence=draft.evidence,
            created_at=datetime.now(UTC),
            status="staged",
        )
        self._staged_feedback[staged_id] = item
        return staged_id

    async def get_unprocessed_feedback(
        self, limit: int = 10
    ) -> list[StagedFeedback]:
        unprocessed = [
            item for item in self._staged_feedback.values() if item.status == "staged"
        ]
        unprocessed.sort(key=lambda item: item.id)
        return unprocessed[:limit]

    async def mark_feedback_published(
        self, staged_id: int, github_issue_url: str
    ) -> None:
        if staged_id in self._staged_feedback:
            prev = self._staged_feedback[staged_id]
            self._staged_feedback[staged_id] = StagedFeedback(
                id=prev.id,
                phone_number=prev.phone_number,
                app_id=prev.app_id,
                title=prev.title,
                observed=prev.observed,
                expected=prev.expected,
                evidence=prev.evidence,
                created_at=prev.created_at,
                status="published",
                github_issue_url=github_issue_url,
                error_message=None,
            )

    async def mark_feedback_failed(
        self, staged_id: int, error_message: str
    ) -> None:
        if staged_id in self._staged_feedback:
            prev = self._staged_feedback[staged_id]
            self._staged_feedback[staged_id] = StagedFeedback(
                id=prev.id,
                phone_number=prev.phone_number,
                app_id=prev.app_id,
                title=prev.title,
                observed=prev.observed,
                expected=prev.expected,
                evidence=prev.evidence,
                created_at=prev.created_at,
                status="failed",
                github_issue_url=prev.github_issue_url,
                error_message=error_message,
            )


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
    """
    CREATE TABLE IF NOT EXISTS active_feedback_drafts (
        phone_number TEXT PRIMARY KEY,
        phase TEXT NOT NULL,
        app_id TEXT NOT NULL,
        title TEXT NOT NULL,
        observed TEXT NOT NULL,
        expected TEXT NOT NULL,
        evidence TEXT NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feedback_staging (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        phone_number TEXT NOT NULL,
        app_id TEXT NOT NULL,
        title TEXT NOT NULL,
        observed TEXT NOT NULL,
        expected TEXT NOT NULL,
        evidence TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'staged' CHECK (status IN ('staged', 'published', 'failed')),
        github_issue_url TEXT,
        error_message TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
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

    async def get_feedback_draft(
        self, phone_number: str
    ) -> tuple[FeedbackPhase, FeedbackDraft | None]:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT phase, app_id, title, observed, expected, evidence
                FROM active_feedback_drafts
                WHERE phone_number = %s
                """,
                (phone_number,),
            )
            row = await cursor.fetchone()
        if row is None:
            return (FeedbackPhase.IDLE, None)
        phase_str, app_id, title, observed, expected, evidence = row
        phase = FeedbackPhase(phase_str)
        draft = (
            FeedbackDraft(
                app_id=app_id,
                title=title,
                observed=observed,
                expected=expected,
                evidence=evidence,
                is_complete=True,
            )
            if (title or observed or expected)
            else None
        )
        return (phase, draft)

    async def set_feedback_draft(
        self,
        phone_number: str,
        phase: FeedbackPhase,
        draft: FeedbackDraft | None,
    ) -> None:
        app_id = draft.app_id if draft else ""
        title = draft.title if draft else ""
        observed = draft.observed if draft else ""
        expected = draft.expected if draft else ""
        evidence = draft.evidence if draft else ""
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                INSERT INTO active_feedback_drafts
                    (phone_number, phase, app_id, title, observed, expected, evidence, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (phone_number) DO UPDATE
                SET phase = EXCLUDED.phase,
                    app_id = EXCLUDED.app_id,
                    title = EXCLUDED.title,
                    observed = EXCLUDED.observed,
                    expected = EXCLUDED.expected,
                    evidence = EXCLUDED.evidence,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (phone_number, phase.value, app_id, title, observed, expected, evidence),
            )

    async def clear_feedback_draft(self, phone_number: str) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                "DELETE FROM active_feedback_drafts WHERE phone_number = %s",
                (phone_number,),
            )

    async def stage_feedback(
        self, phone_number: str, draft: FeedbackDraft
    ) -> int:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                INSERT INTO feedback_staging
                    (phone_number, app_id, title, observed, expected, evidence)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    phone_number,
                    draft.app_id,
                    draft.title,
                    draft.observed,
                    draft.expected,
                    draft.evidence,
                ),
            )
            row = await cursor.fetchone()
            if row is None:
                raise RuntimeError("Failed to retrieve generated id for staged feedback")
            return int(row[0])

    async def get_unprocessed_feedback(
        self, limit: int = 10
    ) -> list[StagedFeedback]:
        async with self._pool.connection() as connection:
            cursor = await connection.execute(
                """
                SELECT id, phone_number, app_id, title, observed, expected, evidence, created_at, status, github_issue_url, error_message
                FROM feedback_staging
                WHERE status = 'staged'
                ORDER BY id ASC
                LIMIT %s
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            return [
                StagedFeedback(
                    id=int(row[0]),
                    phone_number=str(row[1]),
                    app_id=str(row[2]),
                    title=str(row[3]),
                    observed=str(row[4]),
                    expected=str(row[5]),
                    evidence=str(row[6]),
                    created_at=cast(datetime, row[7]),
                    status=str(row[8]),
                    github_issue_url=cast(str | None, row[9]),
                    error_message=cast(str | None, row[10]),
                )
                for row in rows
            ]

    async def mark_feedback_published(
        self, staged_id: int, github_issue_url: str
    ) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                UPDATE feedback_staging
                SET status = 'published',
                    github_issue_url = %s,
                    error_message = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (github_issue_url, staged_id),
            )

    async def mark_feedback_failed(
        self, staged_id: int, error_message: str
    ) -> None:
        async with self._pool.connection() as connection:
            await connection.execute(
                """
                UPDATE feedback_staging
                SET status = 'failed',
                    error_message = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (error_message, staged_id),
            )

