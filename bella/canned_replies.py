"""Load the editable replies that never pass through a model."""

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from bella.reply_language import ReplyLanguage
from bella.yaml_content import parse_yaml_mapping, require_text, require_text_list

WHAT = "canned replies"


@dataclass(frozen=True)
class CannedReplies:
    refusals: tuple[str, ...]
    error_reply: str
    apostila_soon_reply: str
    apostila_caption: str
    apostila_error_reply: str
    media_reply: str
    rate_limit_reply: str
    human_contact_intro: str
    translations: dict[str, dict[str, str]]

    def reply(self, key: str, language: ReplyLanguage) -> str:
        default = cast(str, getattr(self, key))
        return self.translations.get(language.value, {}).get(key, default)

    @classmethod
    def from_yaml(cls, path: Path) -> "CannedReplies":
        raw = parse_yaml_mapping(path.read_text(encoding="utf-8"), WHAT)
        refusals = raw.get("refusals")
        if not isinstance(refusals, dict):
            raise ValueError(f"{WHAT} must define refusals")
        translations_raw = raw.get("translations", {})
        if not isinstance(translations_raw, dict):
            raise ValueError(f"{WHAT} translations must be a mapping")
        translation_keys = (
            "media_reply",
            "rate_limit_reply",
            "error_reply",
            "apostila_soon_reply",
            "apostila_caption",
            "apostila_error_reply",
            "human_contact_intro",
        )
        translations: dict[str, dict[str, str]] = {}
        for language in ("en", "es"):
            localized = translations_raw.get(language)
            if not isinstance(localized, dict):
                raise ValueError(f"{WHAT} translations must define {language}")
            translations[language] = {
                key: require_text(localized, key, f"{WHAT} {language} translations")
                for key in translation_keys
            }
        return cls(
            refusals=require_text_list(refusals, "pt", f"{WHAT} refusals"),
            error_reply=require_text(raw, "error_reply", WHAT),
            apostila_soon_reply=require_text(raw, "apostila_soon_reply", WHAT),
            apostila_caption=require_text(raw, "apostila_caption", WHAT),
            apostila_error_reply=require_text(raw, "apostila_error_reply", WHAT),
            media_reply=require_text(raw, "media_reply", WHAT),
            rate_limit_reply=require_text(raw, "rate_limit_reply", WHAT),
            human_contact_intro=require_text(raw, "human_contact_intro", WHAT),
            translations=translations,
        )
