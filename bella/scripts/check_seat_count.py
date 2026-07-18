"""Print the current official SENAI-SP opening count."""

import asyncio
import os
from pathlib import Path

from bella.availability import SenaiAvailabilitySource
from bella.config import DEFAULT_ENROLLMENT_CARD_PATH
from bella.yaml_content import parse_yaml_mapping, require_text


async def _run() -> int:
    card_path = Path(
        os.environ.get("ENROLLMENT_CARD_PATH", DEFAULT_ENROLLMENT_CARD_PATH)
    )
    card = parse_yaml_mapping(
        card_path.read_text(encoding="utf-8"),
        "Enrollment Card",
    )
    listing_url = require_text(
        card,
        "senai_course_listing_url",
        "Enrollment Card",
    )
    source = SenaiAvailabilitySource(listing_url)
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
