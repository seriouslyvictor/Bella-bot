"""Wire-level tests for the outbound sender.

Ticket 02 covered EvolutionSender only through a fake, so the headers it
actually builds were never exercised. That gap hid a real problem: /send/text
sits behind the same `Auth` middleware as /instance/connect, so it needs the
instance token too — meaning a GLOBAL_API_KEY in EVOLUTION_API_KEY breaks
replying, not just the deploy scripts.
"""

import asyncio

import httpx

from bella.evolution import EvolutionSender


def test_send_text_authenticates_with_the_instance_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"message": "success"})

    sender = EvolutionSender(
        base_url="http://evolution-go:8080",
        api_key="the-instance-token",
        instance_id="an-instance-id",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    asyncio.run(sender.send_text("5511999999999", "oi"))

    assert seen[0].headers["apikey"] == "the-instance-token"
    assert str(seen[0].url) == "http://evolution-go:8080/send/text"


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
