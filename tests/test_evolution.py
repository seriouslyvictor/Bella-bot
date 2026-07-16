"""Wire-level tests for the outbound sender.

Ticket 02 covered EvolutionSender only through a fake, so the headers it
actually builds were never exercised. That gap hid a real problem: /send/text
sits behind the same `Auth` middleware as /instance/connect, so it needs the
instance token too — meaning a GLOBAL_API_KEY in EVOLUTION_API_KEY breaks
replying, not just the deploy scripts.
"""

import asyncio
from pathlib import Path

import httpx

from bella.evolution import EvolutionSender


def _send_response(message_id: str) -> dict[str, object]:
    """The documented Evolution GO send-endpoint response shape: the sent
    message's Info mirrors the webhook delivery shape (data.Info.ID)."""
    return {
        "data": {"Info": {"ID": message_id, "IsFromMe": True}},
        "message": "success",
    }


def test_send_text_authenticates_with_the_instance_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_send_response("3EB0000000000000000010"))

    sender = EvolutionSender(
        base_url="http://evolution-go:8080",
        api_key="the-instance-token",
        instance_id="an-instance-id",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    asyncio.run(sender.send_text("5511999999999", "oi"))

    assert seen[0].headers["apikey"] == "the-instance-token"
    assert str(seen[0].url) == "http://evolution-go:8080/send/text"


def test_send_text_returns_the_providers_message_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_send_response("3EB0000000000000000010"))

    sender = EvolutionSender(
        base_url="http://evolution-go:8080",
        api_key="the-instance-token",
        instance_id="an-instance-id",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    message_id = asyncio.run(sender.send_text("5511999999999", "oi"))

    assert message_id == "3EB0000000000000000010"


def test_send_text_raises_on_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "not authorized"})

    sender = EvolutionSender(
        base_url="http://evolution-go:8080",
        api_key="wrong-kind-of-key",
        instance_id="an-instance-id",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    # The pipeline swallows this (the webhook is already acked) and logs it —
    # what matters is that it surfaces rather than passing silently.
    try:
        asyncio.run(sender.send_text("5511999999999", "oi"))
    except httpx.HTTPStatusError:
        return
    raise AssertionError("expected an HTTPStatusError")


def test_send_document_uses_evolution_go_071_media_contract(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_send_response("3EB0000000000000000007"))

    document = tmp_path / "apostila.pdf"
    document.write_bytes(b"%PDF-1.7 test")
    sender = EvolutionSender(
        base_url="http://evolution-go:8080",
        api_key="the-instance-token",
        instance_id="an-instance-id",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    asyncio.run(sender.send_document("5511999999999", document, "Boa leitura!"))

    assert str(seen[0].url) == "http://evolution-go:8080/send/media"
    assert seen[0].headers["apikey"] == "the-instance-token"
    assert seen[0].read().decode() == (
        '{"number":"5511999999999","url":"JVBERi0xLjcgdGVzdA==",'
        '"type":"document","caption":"Boa leitura!","filename":"apostila.pdf"}'
    )


def test_send_document_returns_the_providers_message_id(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_send_response("3EB0000000000000000007"))

    document = tmp_path / "apostila.pdf"
    document.write_bytes(b"%PDF-1.7 test")
    sender = EvolutionSender(
        base_url="http://evolution-go:8080",
        api_key="the-instance-token",
        instance_id="an-instance-id",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    message_id = asyncio.run(
        sender.send_document("5511999999999", document, "Boa leitura!")
    )

    assert message_id == "3EB0000000000000000007"


def test_health_check_uses_the_unlicensed_server_endpoint() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"status": "ok"})

    sender = EvolutionSender(
        base_url="http://evolution-go:8080",
        api_key="the-instance-token",
        instance_id="an-instance-id",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    asyncio.run(sender.check_health())

    assert str(seen[0].url) == "http://evolution-go:8080/server/ok"
    assert "apikey" not in seen[0].headers
