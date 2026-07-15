"""Behavioral tests through the webhook seam (see spec: Testing Decisions).

Everything is driven by POSTing simulated Evolution GO webhook payloads;
assertions observe only the fake sender and HTTP responses.
"""

from fastapi.testclient import TestClient

from bella.app import create_app
from tests.conftest import TEST_SECRET, FakeSender, make_settings, make_webhook_payload

WEBHOOK = f"/webhook/{TEST_SECRET}"


def test_text_message_gets_a_reply(client: TestClient, sender: FakeSender) -> None:
    response = client.post(WEBHOOK, json=make_webhook_payload("olá bella"))

    assert response.status_code == 200
    assert len(sender.sent) == 1
    number, text = sender.sent[0]
    assert number == "5511999999999"
    assert "olá bella" in text


def test_wrong_secret_is_rejected_and_nothing_sent(
    client: TestClient, sender: FakeSender
) -> None:
    response = client.post("/webhook/wrong-secret", json=make_webhook_payload())

    assert response.status_code == 403
    assert sender.sent == []


def test_own_messages_are_ignored(client: TestClient, sender: FakeSender) -> None:
    response = client.post(WEBHOOK, json=make_webhook_payload(from_me=True))

    assert response.status_code == 200
    assert sender.sent == []


def test_duplicate_delivery_gets_one_reply(
    client: TestClient, sender: FakeSender
) -> None:
    payload = make_webhook_payload("oi", message_id="DUPLICATED")

    first = client.post(WEBHOOK, json=payload)
    second = client.post(WEBHOOK, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(sender.sent) == 1


def test_non_message_event_is_acked_and_ignored(
    client: TestClient, sender: FakeSender
) -> None:
    response = client.post(
        WEBHOOK,
        json={"event": "Connection", "data": {"state": "open"}},
    )

    assert response.status_code == 200
    assert sender.sent == []


def test_message_without_text_is_acked_and_ignored(
    client: TestClient, sender: FakeSender
) -> None:
    # Media handling arrives in ticket 09; the skeleton just stays silent.
    response = client.post(
        WEBHOOK, json=make_webhook_payload(None, message_type="image")
    )

    assert response.status_code == 200
    assert sender.sent == []


def test_send_failure_still_acks_the_webhook(sender: FakeSender) -> None:
    failing = FakeSender(fail=True)
    app = create_app(settings=make_settings(), sender=failing)
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(WEBHOOK, json=make_webhook_payload())

    assert response.status_code == 200
    assert failing.sent == []


def test_malformed_body_is_acked_and_ignored(
    client: TestClient, sender: FakeSender
) -> None:
    # Evolution retries on non-2xx; garbage must not cause a retry storm.
    response = client.post(WEBHOOK, json={"unexpected": "shape"})

    assert response.status_code == 200
    assert sender.sent == []


def test_health_endpoint(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
