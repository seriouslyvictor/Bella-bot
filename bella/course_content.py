"""Load the public-safe Knowledge Base and volatile Enrollment Card."""

from dataclasses import dataclass
from pathlib import Path

from bella.yaml_content import parse_yaml_mapping, require_text

WHAT = "Enrollment Card"


@dataclass(frozen=True)
class CourseContent:
    knowledge_base: str
    enrollment_card: str
    enrollment_url: str

    @classmethod
    def from_files(
        cls, knowledge_base_path: Path, enrollment_card_path: Path
    ) -> "CourseContent":
        enrollment_card = enrollment_card_path.read_text(encoding="utf-8")
        parsed = parse_yaml_mapping(enrollment_card, WHAT)
        return cls(
            knowledge_base=knowledge_base_path.read_text(encoding="utf-8"),
            enrollment_card=enrollment_card,
            enrollment_url=require_text(parsed, "enrollment_url", WHAT),
        )
