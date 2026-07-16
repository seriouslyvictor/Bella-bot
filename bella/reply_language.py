"""Small deterministic language hint for replies that must bypass the LLM."""

import re
import unicodedata
from enum import StrEnum


class ReplyLanguage(StrEnum):
    PORTUGUESE = "pt"
    ENGLISH = "en"
    SPANISH = "es"


SPANISH_MARKERS = frozenset(
    {
        "quiero",
        "hablar",
        "persona",
        "puedes",
        "enviar",
        "cuaderno",
        "inscripcion",
        "gracias",
    }
)
ENGLISH_MARKERS = frozenset(
    {
        "can",
        "could",
        "please",
        "send",
        "workbook",
        "person",
        "human",
        "enrollment",
        "thanks",
    }
)


def detect_reply_language(text: str | None) -> ReplyLanguage:
    """Recognize common English/Spanish request words; default safely to pt-BR."""
    if not text:
        return ReplyLanguage.PORTUGUESE
    normalized = unicodedata.normalize("NFKD", text.casefold())
    words = set(re.findall(r"[a-z]+", normalized))
    if words & SPANISH_MARKERS:
        return ReplyLanguage.SPANISH
    if words & ENGLISH_MARKERS:
        return ReplyLanguage.ENGLISH
    return ReplyLanguage.PORTUGUESE
