"""Load the public-safe Knowledge Base and volatile Enrollment Card."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class CourseContent:
    knowledge_base: str
    enrollment_card: str
    enrollment_url: str

    @classmethod
    def from_files(
        cls, knowledge_base_path: Path, enrollment_card_path: Path
    ) -> "CourseContent":
        knowledge_base = knowledge_base_path.read_text(encoding="utf-8")
        enrollment_card = enrollment_card_path.read_text(encoding="utf-8")
        parsed: Any = yaml.safe_load(enrollment_card)
        if (
            not isinstance(parsed, dict)
            or not isinstance(parsed.get("enrollment_url"), str)
            or not parsed["enrollment_url"]
        ):
            raise ValueError("Enrollment Card must define enrollment_url")
        return cls(
            knowledge_base=knowledge_base,
            enrollment_card=enrollment_card,
            enrollment_url=parsed["enrollment_url"],
        )
