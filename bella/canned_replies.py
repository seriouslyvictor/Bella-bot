"""Load the editable replies that never pass through a model."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from bella.reply_language import ReplyLanguage
from bella.yaml_content import parse_yaml_mapping, require_text, require_text_list

WHAT = "canned replies"

# Every key a translation block may localize. Adding a key here is all a new
# localized canned reply needs; `reply()` falls back to the pt-BR field.
TRANSLATABLE_KEYS = (
    "media_reply",
    "rate_limit_reply",
    "error_reply",
    "human_contact_intro",
    "greeting_reply",
    "no_contact_reply",
)


@dataclass(frozen=True)
class CannedReplies:
    refusals: tuple[str, ...]
    error_reply: str
    media_reply: str
    rate_limit_reply: str
    human_contact_intro: str
    translations: dict[str, dict[str, str]]
    greeting_reply: str = ""
    apostila_soon_reply: str = ""
    apostila_caption: str = "Documento"
    apostila_error_reply: str = ""
    no_contact_reply: str = ""
    # Per-language refusal rotations, keyed by language code. `refusals` above
    # stays the pt-BR rotation so existing callers keep working.
    localized_refusals: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def reply(self, key: str, language: ReplyLanguage) -> str:
        default = cast(str, getattr(self, key, ""))
        return self.translations.get(language.value, {}).get(key, default)

    def refusals_for(self, language: ReplyLanguage) -> tuple[str, ...]:
        """The refusal rotation for a language, falling back to pt-BR.

        An out-of-scope message is the one reply a user gets in their own
        words without a model ever running, so shipping a localized rotation
        and then answering everyone in Portuguese defeats the point.
        """
        return self.localized_refusals.get(language.value) or self.refusals

    @classmethod
    def from_yaml(cls, path: Path) -> "CannedReplies":
        raw = parse_yaml_mapping(path.read_text(encoding="utf-8"), WHAT)
        refusals = raw.get("refusals")
        if not isinstance(refusals, dict):
            raise ValueError(f"{WHAT} must define refusals")
        translations_raw = raw.get("translations", {})
        if not isinstance(translations_raw, dict):
            raise ValueError(f"{WHAT} translations must be a mapping")
        translations: dict[str, dict[str, str]] = {}
        for language in ("en", "es"):
            localized = translations_raw.get(language)
            if not isinstance(localized, dict):
                raise ValueError(f"{WHAT} translations must define {language}")
            translations[language] = {
                key: require_text(localized, key, f"{WHAT} {language} translations")
                for key in TRANSLATABLE_KEYS
                if key in localized
            }
        localized_refusals = {
            language: require_text_list(refusals, language, f"{WHAT} refusals")
            for language in ("pt", "en", "es")
            if language in refusals
        }
        return cls(
            refusals=require_text_list(refusals, "pt", f"{WHAT} refusals"),
            error_reply=require_text(raw, "error_reply", WHAT),
            greeting_reply=str(raw.get("greeting_reply", "")),
            apostila_soon_reply=str(raw.get("apostila_soon_reply", "")),
            apostila_caption=str(raw.get("apostila_caption", "Documento")),
            apostila_error_reply=str(raw.get("apostila_error_reply", "")),
            no_contact_reply=str(raw.get("no_contact_reply", "")),
            media_reply=require_text(raw, "media_reply", WHAT),
            rate_limit_reply=require_text(raw, "rate_limit_reply", WHAT),
            human_contact_intro=require_text(raw, "human_contact_intro", WHAT),
            translations=translations,
            localized_refusals=localized_refusals,
        )
