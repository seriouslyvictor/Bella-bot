"""The one place a reply becomes outbound WhatsApp text.

Every branch of the pipeline — canned refusals, the grounded answerer, the
feedback dialogue, handoffs — produces a :class:`Response` and hands it to a
:class:`ResponsePolicy`. Nothing reaches the user without passing through
``ResponsePolicy.finalize``. That single funnel is what makes the reply
contract enforceable instead of aspirational: before it existed the URL guard
ran on one branch only, model-authored follow-up questions went out raw, and
an empty string was a sendable reply.

Two properties the funnel owns:

* **Trust tiers.** A reply Nova wrote herself (``CANNED``, ``CONTROL``) is
  authored by us and is only formatted. A reply a model wrote (``ANSWERER``,
  ``FEEDBACK``) is untrusted output and additionally passes the URL allowlist
  (ADR 0002) — the guard is a property of the source, not of one code path.
* **Never empty, never silent.** ``finalize`` always returns at least one
  non-empty chunk; a response that normalizes away to nothing degrades to the
  policy's fallback text rather than to an empty send, which the always-reply
  invariant (see ``bella.pipeline``) forbids.
"""

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from bella.answer_guard import strip_foreign_urls
from bella.reply_language import ReplyLanguage

logger = logging.getLogger("bella")

# WhatsApp accepts 4096 characters per message, but a wall of text is unusable
# on a phone. Chunking below that keeps replies readable; the chunk cap stops a
# runaway generation from turning into a burst of messages.
DEFAULT_MAX_LENGTH = 1600
DEFAULT_MAX_CHUNKS = 3
ELLIPSIS = "…"


class ResponseSource(StrEnum):
    """Who authored the text — which decides how much scrubbing it needs."""

    CANNED = "canned"
    CONTROL = "control"
    ANSWERER = "answerer"
    FEEDBACK = "feedback"

    @property
    def is_model_authored(self) -> bool:
        return self in (ResponseSource.ANSWERER, ResponseSource.FEEDBACK)


@dataclass(frozen=True)
class Response:
    """One reply, before formatting and before it is split into messages."""

    text: str
    source: ResponseSource = ResponseSource.CANNED
    language: ReplyLanguage = ReplyLanguage.PORTUGUESE
    needs_handoff: bool = False
    # The apostila/document branch sends its own payload; the text is still
    # recorded as the reply, but no second send happens.
    already_sent: bool = False


_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
_HORIZONTAL_RULE = re.compile(r"^\s*([-*_])\s*(?:\1\s*){2,}$")
_BULLET = re.compile(r"^(\s*)[-*+]\s+")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.DOTALL)
_UNDERLINE_ITALIC = re.compile(r"__(?=\S)(.+?)(?<=\S)__", re.DOTALL)
_STRIKETHROUGH = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~", re.DOTALL)
_SURVIVING_MARKDOWN_LINK = re.compile(r"\[([^\]]+)]\((\S+?)\)")
_BLANK_RUN = re.compile(r"\n{3,}")
_SENTENCE_END = re.compile(r"(?<=[.!?…])\s+")


def normalize_for_whatsapp(text: str) -> str:
    """Rewrite Markdown a model emits into what WhatsApp actually renders.

    WhatsApp understands ``*bold*``, ``_italic_``, ``~strike~`` and code
    fences — not ``**bold**``, headings or ``-`` bullets, which reach the user
    as literal punctuation. Prompting a model to avoid Markdown is unreliable,
    so the rewrite happens here, deterministically, for every reply.
    """
    lines: list[str] = []
    for raw_line in text.replace("\r\n", "\n").split("\n"):
        line = raw_line.rstrip()
        if _HORIZONTAL_RULE.match(line):
            continue
        heading = _HEADING.match(line)
        if heading is not None:
            title = heading.group(1).strip()
            lines.append(f"*{title}*" if title else "")
            continue
        lines.append(_BULLET.sub(r"\1• ", line))
    normalized = "\n".join(lines)
    normalized = _BOLD.sub(r"*\1*", normalized)
    normalized = _UNDERLINE_ITALIC.sub(r"_\1_", normalized)
    normalized = _STRIKETHROUGH.sub(r"~\1~", normalized)
    # Any link still carrying Markdown syntax here was allowed by the URL
    # guard; WhatsApp would show the brackets verbatim, so flatten it.
    normalized = _SURVIVING_MARKDOWN_LINK.sub(r"\1: \2", normalized)
    return _BLANK_RUN.sub("\n\n", normalized).strip()


def split_for_whatsapp(
    text: str,
    max_length: int = DEFAULT_MAX_LENGTH,
    max_chunks: int = DEFAULT_MAX_CHUNKS,
) -> tuple[str, ...]:
    """Split an over-long reply on the widest boundary that still fits.

    Paragraph, then line, then sentence, then a hard cut — a reply is never
    dropped for being long, but it also never arrives as one unreadable wall
    or as an unbounded burst of messages.
    """
    if len(text) <= max_length:
        return (text,)
    chunks: list[str] = []
    remaining = text
    while remaining and len(chunks) < max_chunks:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            remaining = ""
            break
        head, remaining = _split_once(remaining, max_length)
        chunks.append(head)
    if remaining:
        # Out of chunks with text left: mark the truncation rather than
        # letting the reply end mid-thought with no sign anything was cut.
        last = chunks[-1].rstrip()
        budget = max_length - len(ELLIPSIS)
        chunks[-1] = f"{last[:budget].rstrip()} {ELLIPSIS}".strip()
    return tuple(chunk for chunk in chunks if chunk)


def _split_once(text: str, max_length: int) -> tuple[str, str]:
    window = text[:max_length]
    for separator in ("\n\n", "\n"):
        cut = window.rfind(separator)
        if cut > 0:
            return text[:cut].rstrip(), text[cut:].lstrip()
    sentence_cut = 0
    for match in _SENTENCE_END.finditer(window):
        sentence_cut = match.end()
    if sentence_cut > 0:
        return text[:sentence_cut].rstrip(), text[sentence_cut:].lstrip()
    space_cut = window.rfind(" ")
    if space_cut > 0:
        return text[:space_cut].rstrip(), text[space_cut:].lstrip()
    return window, text[max_length:].lstrip()


@dataclass(frozen=True)
class ResponsePolicy:
    """The reply contract: what every outbound message must satisfy.

    ``allowed_urls`` is the ADR 0002 allowlist applied to model-authored text.
    An empty allowlist keeps the strict reading — a model may emit no URL at
    all — but each removal is logged, because a deployment whose links are
    silently deleted from every answer looks identical to a model that never
    links.
    """

    fallback_text: str
    allowed_urls: tuple[str, ...] = ()
    max_length: int = DEFAULT_MAX_LENGTH
    max_chunks: int = DEFAULT_MAX_CHUNKS
    translations: dict[str, str] = field(default_factory=dict)

    def fallback_for(self, language: ReplyLanguage) -> str:
        return self.translations.get(language.value, self.fallback_text)

    def finalize(self, response: Response) -> tuple[str, ...]:
        """Guard, format and split one reply into the messages to send."""
        text = response.text or ""
        if response.source.is_model_authored:
            guarded = strip_foreign_urls(text, self.allowed_urls)
            if guarded != text:
                logger.info(
                    "response guard removed a URL from %s output",
                    response.source.value,
                )
            text = guarded
        text = normalize_for_whatsapp(text)
        if not text:
            logger.warning(
                "empty %s response, falling back to the canned reply",
                response.source.value,
            )
            text = normalize_for_whatsapp(self.fallback_for(response.language))
        return split_for_whatsapp(text, self.max_length, self.max_chunks)


def policy_from_urls(
    fallback_text: str,
    allowed_urls: Sequence[str],
    *,
    translations: dict[str, str] | None = None,
) -> ResponsePolicy:
    """Build a policy from a possibly-empty, possibly-blank URL allowlist."""
    return ResponsePolicy(
        fallback_text=fallback_text,
        allowed_urls=tuple(url.strip() for url in allowed_urls if url.strip()),
        translations=dict(translations or {}),
    )
