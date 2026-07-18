import functools
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from typing import Any

import pytest
from fastapi.testclient import TestClient

from bella.app import create_app
from bella.canned_replies import CannedReplies
from bella.config import Settings
from bella.conversation_store import ConversationMessage, InMemoryConversationStore
from bella.course_content import CourseContent
from bella.pipeline import AnswerResult, Pipeline
from bella.rate_limit import RateLimitPolicy
from bella.scope_gate import RouteCategory

TEST_API_KEY = "test-instance-token"


class FakeSender:
    """Records outbound messages instead of calling Evolution GO."""

    def __init__(
        self,
        fail: bool = False,
        *,
        fail_document: bool = False,
        fail_numbers: set[str] | None = None,
        unhealthy: bool = False,
    ) -> None:
        self.sent: list[tuple[str, str]] = []
        self.sent_documents: list[tuple[str, Path, str]] = []
        self.fail = fail
        self.fail_document = fail_document
        self.fail_numbers = fail_numbers or set()
        self.unhealthy = unhealthy
        self._next_message_id = 1

    async def send_text(self, number: str, text: str) -> str:
        if self.fail or number in self.fail_numbers:
            raise RuntimeError("simulated send failure")
        self.sent.append((number, text))
        return self._issue_message_id()

    async def send_document(self, number: str, path: Path, caption: str) -> str:
        if self.fail_document:
            raise RuntimeError("simulated document send failure")
        self.sent_documents.append((number, path, caption))
        return self._issue_message_id()

    def _issue_message_id(self) -> str:
        message_id = f"FAKE-MSG-{self._next_message_id}"
        self._next_message_id += 1
        return message_id

    async def check_health(self) -> None:
        if self.unhealthy:
            raise RuntimeError("simulated dependency failure")


class FakeScopeGate:
    def __init__(
        self,
        category: RouteCategory = RouteCategory.COURSE_QUESTION,
        *,
        fail: bool = False,
    ) -> None:
        self.category = category
        self.fail = fail
        self.seen: list[str] = []

    async def classify(self, text: str) -> RouteCategory:
        self.seen.append(text)
        if self.fail:
            raise RuntimeError("simulated Scope Gate failure")
        return self.category


class FakeAnswerer:
    def __init__(
        self,
        response: str | None = None,
        *,
        fail: bool = False,
        needs_handoff: bool = False,
    ) -> None:
        self.seen: list[tuple[str, RouteCategory]] = []
        self.histories: list[list[ConversationMessage]] = []
        self.response = response
        self.fail = fail
        self.needs_handoff = needs_handoff

    async def answer(
        self,
        text: str,
        category: RouteCategory,
        history: Sequence[ConversationMessage],
    ) -> AnswerResult:
        self.seen.append((text, category))
        self.histories.append(list(history))
        if self.fail:
            raise RuntimeError("simulated answering failure")
        return AnswerResult(
            self.response or f"placeholder answer: {text}",
            needs_handoff=self.needs_handoff,
        )


def make_settings() -> Settings:
    return Settings(
        evolution_url="http://evolution-go:8080",
        evolution_api_key=TEST_API_KEY,
        evolution_instance_id="unused-in-tests",
        bella_internal_url="http://bella:8000",
        anthropic_api_key="unused-in-tests",
    )


@functools.cache
def course_content() -> CourseContent:
    """The real shipped content, parsed once per test run."""
    settings = make_settings()
    return CourseContent.from_files(
        settings.knowledge_base_path, settings.enrollment_card_path
    )


@functools.cache
def canned_replies() -> CannedReplies:
    """The real shipped replies, parsed once per test run."""
    return CannedReplies.from_yaml(make_settings().canned_replies_path)


def make_test_client(
    sender: FakeSender,
    *,
    scope_gate: FakeScopeGate | None = None,
    answerer: FakeAnswerer | None = None,
    conversation_store: InMemoryConversationStore | None = None,
    apostila_path: Path | None = None,
    admin_contact: str = "",
    rate_limit_max_messages: int = 10,
    rate_limit_window_seconds: int = 60,
    rate_limit_clock: Callable[[], float] | None = None,
    takeover_pause_seconds: int = 3600,
    takeover_clock: Callable[[], datetime] | None = None,
    raise_server_exceptions: bool = True,
) -> TestClient:
    pipeline = Pipeline(
        sender,
        scope_gate or FakeScopeGate(),
        answerer or FakeAnswerer(),
        canned_replies(),
        course_content().enrollment_url,
        conversation_store or InMemoryConversationStore(),
        apostila_path or make_settings().apostila_path,
        course_content().human_contact_reply,
        admin_contact,
        RateLimitPolicy(rate_limit_max_messages, rate_limit_window_seconds),
        rate_limit_clock or monotonic,
        takeover_pause_seconds,
        takeover_clock or (lambda: datetime.now(UTC)),
    )
    app = create_app(make_settings(), pipeline)
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def make_webhook_payload(
    text: str | None = "oi",
    *,
    message_id: str = "3EB0MSG0001",
    from_me: bool = False,
    is_group: bool = False,
    chat: str = "5511999999999@s.whatsapp.net",
    sender_alt: str = "",
    recipient_alt: str = "",
    message_type: str = "text",
    media_caption: str | None = None,
) -> dict[str, Any]:
    """Simulates an Evolution GO 'Message' webhook delivery.

    LID-addressed chats put the peer's `@lid` alias in Chat and carry the
    phone number in SenderAlt (inbound) or RecipientAlt (from-me); whatsmeow
    marshals absent alt JIDs as empty strings, so the defaults mirror the
    plain phone-number-addressed delivery.
    """
    message: dict[str, Any] = {}
    if text is not None:
        message["conversation"] = text
    elif media_caption is not None:
        message[f"{message_type}Message"] = {"caption": media_caption}
    return {
        "event": "Message",
        "data": {
            "Info": {
                "Chat": chat,
                "Sender": chat,
                "SenderAlt": sender_alt,
                "RecipientAlt": recipient_alt,
                "IsFromMe": from_me,
                "IsGroup": is_group,
                "ID": message_id,
                "Type": message_type,
                "PushName": "Teste",
                "Timestamp": "2026-07-14T10:00:00-03:00",
                "MediaType": "",
            },
            "Message": message,
        },
        "instanceId": "249aad2e-0000-0000-0000-000000000000",
        "instanceToken": TEST_API_KEY,
    }


@pytest.fixture()
def sender() -> FakeSender:
    return FakeSender()


@pytest.fixture()
def client(sender: FakeSender) -> TestClient:
    return make_test_client(sender)
