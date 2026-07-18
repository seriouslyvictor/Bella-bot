"""Load the public-safe Knowledge Base and volatile Enrollment Card."""

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml

from bella.seat_count import SeatCountHolder
from bella.yaml_content import parse_yaml_mapping, require_text

WHAT = "Enrollment Card"


@dataclass(frozen=True)
class CourseContent:
    knowledge_base: str
    enrollment_card_fields: dict[str, Any]
    enrollment_url: str
    senai_course_listing_url: str
    human_contact_reply: str
    seat_count_holder: SeatCountHolder

    @classmethod
    def from_files(
        cls,
        knowledge_base_path: Path,
        enrollment_card_path: Path,
        *,
        seat_count_holder: SeatCountHolder | None = None,
    ) -> "CourseContent":
        enrollment_card = enrollment_card_path.read_text(encoding="utf-8")
        parsed = parse_yaml_mapping(enrollment_card, WHAT)
        enrollment_url = require_text(parsed, "enrollment_url", WHAT)
        listing_url = require_text(parsed, "senai_course_listing_url", WHAT)
        parsed.pop("seats", None)
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
            human_contact_reply="\n".join(contact_lines),
            seat_count_holder=seat_count_holder
            or SeatCountHolder(max_age=timedelta(hours=24)),
        )

    def render_enrollment_card(self) -> str:
        fields = dict(self.enrollment_card_fields)
        count = self.seat_count_holder.current_count()
        if count is not None:
            fields["seats"] = f"{count} vagas"
        return yaml.safe_dump(
            fields,
            allow_unicode=True,
            sort_keys=False,
        )
