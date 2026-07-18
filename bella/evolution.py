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
from typing import Any, Literal, Protocol

import httpx

logger = logging.getLogger("bella")

PresenceState = Literal["available", "composing", "paused"]


@dataclass(frozen=True)
class InboundMessage:
    message_id: str
    chat_jid: str
    text: str | None
    media_caption: str | None
    push_name: str
    is_from_me: bool
    is_group: bool
    message_type: str

    @property
    def number(self) -> str:
        """The bare number Evolution GO's send endpoints expect."""
        return self.chat_jid.split("@", 1)[0]


def _canonical_chat_jid(info: dict[str, Any]) -> str | None:
    """The conversation key: the peer's phone-number JID whenever it exists.

    In LID-addressed chats (WhatsApp's privacy aliases, `<digits>@lid`),
    Info.Chat is the peer's LID — and Evolution GO rewrites it to the
    phone-number JID only on inbound messages, because its LID/PN swap
    keys off SenderAlt, which whatsmeow leaves empty on from-me messages.
    Keying on Chat alone therefore splits one conversation in two: the
    owner's Takeover messages under the LID, the user's messages under the
    phone number — so the pause never bites and owner turns land in the
    wrong history. The phone number always travels alongside the LID:
    RecipientAlt on from-me messages, SenderAlt on inbound ones (when the
    swap has not already promoted it into Chat).
    """
    chat_jid = info.get("Chat")
    if not isinstance(chat_jid, str):
        return None
    if not chat_jid.endswith("@lid"):
        return chat_jid
    alt = info.get("RecipientAlt") if info.get("IsFromMe") else info.get("SenderAlt")
    if isinstance(alt, str) and alt.endswith("@s.whatsapp.net"):
        # Alt JIDs can carry a device suffix (user:device@server); the
        # conversation key is the bare user part.
        user = alt.split("@", 1)[0].split(":", 1)[0]
        return f"{user}@s.whatsapp.net"
    # No phone number in the payload: keep the LID so at least both
    # directions of a chat missing it key consistently.
    return chat_jid


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
    chat_jid = _canonical_chat_jid(info)
    if not isinstance(message_id, str) or chat_jid is None:
        return None

    wire_message = data.get("Message")
    if isinstance(wire_message, dict) and "reactionMessage" in wire_message:
        logger.info("reaction event dropped: %s", message_id)
        return None
    text = _extract_text(wire_message)

    return InboundMessage(
        message_id=message_id,
        chat_jid=chat_jid,
        text=text,
        media_caption=_extract_media_caption(wire_message),
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


def _extract_media_caption(message: Any) -> str | None:
    """Extract a media caption without promoting media into a text message.

    Media still follows Bella's non-text behavior, but its caption identifies
    an outbound document echo during the pre-response race and preserves useful
    context when a user sends media during a Takeover Pause.
    """
    if not isinstance(message, dict):
        return None
    for key in ("documentMessage", "imageMessage", "videoMessage"):
        media = message.get(key)
        caption = media.get("caption") if isinstance(media, dict) else None
        if isinstance(caption, str) and caption.strip():
            return caption
    wrapper = message.get("documentWithCaptionMessage")
    nested = wrapper.get("message") if isinstance(wrapper, dict) else None
    if isinstance(nested, dict):
        return _extract_media_caption(nested)
    return None


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

    async def send_presence(self, number: str, state: PresenceState) -> None: ...

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

    async def send_presence(self, number: str, state: PresenceState) -> None:
        response = await self._client.post(
            f"{self._base_url}/message/presence",
            headers=self._headers,
            json={
                "number": number,
                "state": state,
                "isAudio": False,
                "delay": 0,
            },
        )
        response.raise_for_status()

    async def check_health(self) -> None:
        # /server/ok reflects process availability without requiring an active
        # Evolution license or exposing either API key in a probe.
        response = await self._client.get(f"{self._base_url}/server/ok", timeout=3)
        response.raise_for_status()
