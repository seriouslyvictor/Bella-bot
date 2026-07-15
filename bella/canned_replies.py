"""Load the editable replies that never pass through a model."""

from dataclasses import dataclass
from pathlib import Path

from bella.yaml_content import parse_yaml_mapping, require_text, require_text_list

WHAT = "canned replies"


@dataclass(frozen=True)
class CannedReplies:
    refusals: tuple[str, ...]
    error_reply: str

    @classmethod
    def from_yaml(cls, path: Path) -> "CannedReplies":
        raw = parse_yaml_mapping(path.read_text(encoding="utf-8"), WHAT)
        refusals = raw.get("refusals")
        if not isinstance(refusals, dict):
            raise ValueError(f"{WHAT} must define refusals")
        return cls(
            refusals=require_text_list(refusals, "pt", f"{WHAT} refusals"),
            error_reply=require_text(raw, "error_reply", WHAT),
        )
