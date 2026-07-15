import functools
from typing import Any

import pytest
from fastapi.testclient import TestClient

from bella.app import create_app
from bella.canned_replies import CannedReplies
from bella.config import Settings
from bella.course_content import CourseContent
from bella.pipeline import Pipeline
from bella.scope_gate import RouteCategory

TEST_SECRET = "test-webhook-secret"


class FakeSender:
    """Records outbound messages instead of calling Evolution GO."""

    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail = fail

    async def send_text(self, number: str, text: str) -> None:
        if self.fail:
            raise RuntimeError("simulated send failure")
        self.sent.append((number, text))


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
    def __init__(self, response: str | None = None, *, fail: bool = False) -> None:
        self.seen: list[tuple[str, RouteCategory]] = []
        self.response = response
        self.fail = fail

    async def answer(self, text: str, category: RouteCategory) -> str:
        self.seen.append((text, category))
        if self.fail:
            raise RuntimeError("simulated answering failure")
        return self.response or f"placeholder answer: {text}"


def make_settings() -> Settings:
    return Settings(
        evolution_url="http://evolution-go:8080",
        evolution_api_key="unused-in-tests",
        evolution_instance_id="unused-in-tests",
        webhook_secret=TEST_SECRET,
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
    raise_server_exceptions: bool = True,
) -> TestClient:
    pipeline = Pipeline(
        sender,
        scope_gate or FakeScopeGate(),
        answerer or FakeAnswerer(),
        canned_replies(),
        course_content().enrollment_url,
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
    message_type: str = "text",
) -> dict[str, Any]:
    """Simulates an Evolution GO 'Message' webhook delivery."""
    message: dict[str, Any] = {}
    if text is not None:
        message["conversation"] = text
    return {
        "event": "Message",
        "data": {
            "Info": {
                "Chat": chat,
                "Sender": chat,
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
        "instanceToken": "not-a-real-token",
    }


@pytest.fixture()
def sender() -> FakeSender:
    return FakeSender()


@pytest.fixture()
def client(sender: FakeSender) -> TestClient:
    return make_test_client(sender)
