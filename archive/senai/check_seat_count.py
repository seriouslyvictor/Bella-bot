"""Print the current official SENAI-SP seat count."""

import asyncio
import os
from pathlib import Path

from bella.availability import SenaiAvailabilitySource
from bella.config import DEFAULT_ENROLLMENT_CARD_PATH, DEFAULT_KNOWLEDGE_BASE_PATH
from bella.course_content import CourseContent


async def _run() -> int:
    knowledge_base_path = Path(
        os.environ.get("KNOWLEDGE_BASE_PATH", DEFAULT_KNOWLEDGE_BASE_PATH)
    )
    enrollment_card_path = Path(
        os.environ.get("ENROLLMENT_CARD_PATH", DEFAULT_ENROLLMENT_CARD_PATH)
    )
    # Reuses CourseContent's own loading path rather than re-parsing the
    # Enrollment Card here, so there is one owner of that format.
    content = CourseContent.from_files(knowledge_base_path, enrollment_card_path)
    source = SenaiAvailabilitySource(
        content.senai_course_listing_url,
        class_start=content.class_start,
    )
    try:
        count = await source.fetch_count()
    finally:
        await source.close()
    print(count)
    return count


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
