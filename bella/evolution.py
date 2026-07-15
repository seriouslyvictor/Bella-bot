"""Evolution GO integration: webhook parsing and the outbound sender.

This module is the single normalization point for Evolution GO's wire shapes
(documented at docs.evolutionfoundation.com.br/evolution-go). If the running
instance's payloads ever differ, this is the only place to adjust.
"""

from dataclasses import dataclass
from typing import Any, Protocol

import httpx


@dataclass(frozen=True)
class InboundMessage:
    message_id: str
    chat_jid: str
    text: str | None
    push_name: str
    is_from_me: bool
    is_group: bool
    message_type: str

    @property
    def number(self) -> str:
        """The bare number Evolution GO's send endpoints expect."""
        return self.chat_jid.split("@", 1)[0]


def parse_webhook(payload: Any) -> InboundMessage | None:
    """Normalize an Evolution GO webhook delivery into an InboundMessage.

    Returns None for non-message events and for payloads that don't match the
    documented shape — the webhook must always be acked, never retried, so
    parsing is deliberately forgiving.
    """
    if not isinstance(payload, dict) or payload.get("event") != "Message":
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    info = data.get("Info")
    if not isinstance(info, dict):
        return None
    message_id = info.get("ID")
    chat_jid = info.get("Chat")
    if not isinstance(message_id, str) or not isinstance(chat_jid, str):
        return None

    message = data.get("Message")
    text = message.get("conversation") if isinstance(message, dict) else None
    if not isinstance(text, str) or not text.strip():
        text = None

    return InboundMessage(
        message_id=message_id,
        chat_jid=chat_jid,
        text=text,
        push_name=str(info.get("PushName", "")),
        is_from_me=bool(info.get("IsFromMe", False)),
        is_group=bool(info.get("IsGroup", False)),
        message_type=str(info.get("Type", "")),
    )


class WhatsAppSender(Protocol):
    async def send_text(self, number: str, text: str) -> None: ...


class EvolutionSender:
    """Sends messages through the Evolution GO HTTP API."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        instance_id: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=30)
        self._base_url = base_url.rstrip("/")
        self._headers = {"apikey": api_key, "instanceId": instance_id}

    async def send_text(self, number: str, text: str) -> None:
        response = await self._client.post(
            f"{self._base_url}/send/text",
            headers=self._headers,
            json={"number": number, "text": text},
        )
        response.raise_for_status()
