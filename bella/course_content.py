"""Load the public-safe Knowledge Base and volatile Enrollment Card."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from bella.yaml_content import parse_yaml_mapping, require_text

WHAT = "Enrollment Card"


@dataclass(frozen=True)
class CourseContent:
    knowledge_base: str
    enrollment_card_fields: dict[str, Any]
    enrollment_url: str
    senai_course_listing_url: str
    class_start: str
    human_contact_reply: str

    @classmethod
    def from_files(
        cls,
        knowledge_base_path: Path,
        enrollment_card_path: Path,
    ) -> "CourseContent":
        enrollment_card = enrollment_card_path.read_text(encoding="utf-8")
        parsed = parse_yaml_mapping(enrollment_card, WHAT)
        enrollment_url = require_text(parsed, "enrollment_url", WHAT)
        listing_url = require_text(parsed, "senai_course_listing_url", WHAT)
        class_start = parsed.get("class_start", "")
        if not isinstance(class_start, str):
            raise ValueError(f"{WHAT} class_start must be text")
        parsed.pop("seats", None)
        # Operational-only: feeds the availability seam, never the model. Left
        # in enrollment_card_fields it would be a second URL in the rendered
        # Enrollment Card, but the answerer may only ever emit enrollment_url.
        parsed.pop("senai_course_listing_url", None)
        contact_lines = [require_text(parsed, "human_contact", WHAT)]
        for key, label in (
            ("human_contact_phone", "Telefone/WhatsApp"),
            ("owner_contact", "Responsavel pelo curso"),
        ):
            value = parsed.get(key, "")
            if not isinstance(value, str):
                raise ValueError(f"{WHAT} {key} must be text")
            if value:
                contact_lines.append(f"{label}: {value}")
        contact_lines.append(enrollment_url)
        return cls(
            knowledge_base=knowledge_base_path.read_text(encoding="utf-8"),
            enrollment_card_fields=parsed,
            enrollment_url=enrollment_url,
            senai_course_listing_url=listing_url,
            class_start=class_start,
            human_contact_reply="\n".join(contact_lines),
        )

    def render_enrollment_card(self) -> str:
        return yaml.safe_dump(
            self.enrollment_card_fields,
            allow_unicode=True,
            sort_keys=False,
        )
