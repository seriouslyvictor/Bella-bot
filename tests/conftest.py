from typing import Any

import pytest
from fastapi.testclient import TestClient

from bella.app import create_app
from bella.config import Settings

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


def make_settings() -> Settings:
    return Settings(
        evolution_url="http://evolution-go:8080",
        evolution_api_key="unused-in-tests",
        evolution_instance_id="unused-in-tests",
        webhook_secret=TEST_SECRET,
    )


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
    app = create_app(settings=make_settings(), sender=sender)
    return TestClient(app)
