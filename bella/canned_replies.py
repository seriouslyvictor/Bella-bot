"""Load and rotate editable replies that never pass through a model."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class CannedReplies:
    refusals: tuple[str, ...]
    error_reply: str
    _next_refusal_by_recipient: dict[str, int] = field(default_factory=dict, init=False)

    def take_refusal(self, recipient: str) -> str:
        next_refusal = self._next_refusal_by_recipient.get(recipient, 0)
        refusal = self.refusals[next_refusal % len(self.refusals)]
        self._next_refusal_by_recipient[recipient] = next_refusal + 1
        return refusal

    @classmethod
    def from_yaml(cls, path: Path) -> "CannedReplies":
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("canned replies must be a mapping")
        refusals_by_language = raw.get("refusals")
        if not isinstance(refusals_by_language, dict):
            raise ValueError("canned replies must define refusals")
        refusals = refusals_by_language.get("pt")
        error_reply = raw.get("error_reply")
        if (
            not isinstance(refusals, list)
            or not refusals
            or not all(isinstance(item, str) and item for item in refusals)
            or not isinstance(error_reply, str)
            or not error_reply
        ):
            raise ValueError("canned replies must define pt refusals and error_reply")
        return cls(refusals=tuple(refusals), error_reply=error_reply)
