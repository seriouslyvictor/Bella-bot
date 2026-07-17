"""Evolution GO integration: webhook parsing and the outbound sender.

This module is the single normalization point for Evolution GO's wire shapes
(documented at docs.evolutionfoundation.com.br/evolution-go). If the running
instance's payloads ever differ, this is the only place to adjust.
"""

import asyncio
import base64
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx

logger = logging.getLogger("bella")


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

    text = _extract_text(data.get("Message"))

    return InboundMessage(
        message_id=message_id,
        chat_jid=chat_jid,
        text=text,
        push_name=str(info.get("PushName", "")),
        is_from_me=bool(info.get("IsFromMe", False)),
        is_group=bool(info.get("IsGroup", False)) or chat_jid.endswith("@g.us"),
        message_type=str(info.get("Type", "")),
    )


def _extract_text(message: Any) -> str | None:
    """Text lives under `conversation` for plain DMs and under
    `extendedTextMessage.text` for replies/link previews (whatsmeow shape)."""
    if not isinstance(message, dict):
        return None
    text = message.get("conversation")
    if not isinstance(text, str) or not text.strip():
        extended = message.get("extendedTextMessage")
        text = extended.get("text") if isinstance(extended, dict) else None
    if not isinstance(text, str) or not text.strip():
        return None
    return text


def _read_base64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _extract_message_id(payload: Any) -> str:
    """Send-endpoint responses wrap the sent message in the same Info.ID
    shape as webhook deliveries (data.Info.ID).

    Best-effort: the send already succeeded (the response was a 200) by the
    time this runs, so a missing or malformed id must not turn a delivered
    message into an error reply. On a miss this logs a warning and returns
    "" instead of raising; the pipeline's EchoLedger treats an empty id as
    unregistered and, for text sends, still has the (recipient, text)
    fallback to recognize its own echo.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    info = data.get("Info") if isinstance(data, dict) else None
    message_id = info.get("ID") if isinstance(info, dict) else None
    if not isinstance(message_id, str):
        logger.warning("Evolution GO send response missing data.Info.ID")
        return ""
    return message_id


class WhatsAppSender(Protocol):
    async def send_text(self, number: str, text: str) -> str: ...

    async def send_document(self, number: str, path: Path, caption: str) -> str: ...

    async def check_health(self) -> None: ...


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

    async def send_text(self, number: str, text: str) -> str:
        response = await self._client.post(
            f"{self._base_url}/send/text",
            headers=self._headers,
            json={"number": number, "text": text},
        )
        response.raise_for_status()
        return _extract_message_id(response.json())

    async def send_document(self, number: str, path: Path, caption: str) -> str:
        # Encode in the worker thread too: b64 of a multi-MB PDF is CPU-bound and
        # would otherwise stall every other in-flight message on the event loop.
        encoded = await asyncio.to_thread(_read_base64, path)
        response = await self._client.post(
            f"{self._base_url}/send/media",
            headers=self._headers,
            json={
                "number": number,
                "url": encoded,
                "type": "document",
                "caption": caption,
                "filename": path.name,
            },
        )
        response.raise_for_status()
        return _extract_message_id(response.json())

    async def check_health(self) -> None:
        # /server/ok reflects process availability without requiring an active
        # Evolution license or exposing either API key in a probe.
        response = await self._client.get(f"{self._base_url}/server/ok", timeout=3)
        response.raise_for_status()
