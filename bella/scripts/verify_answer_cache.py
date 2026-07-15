"""Verify the Opus answering prefix is read from cache on a repeated call."""

import asyncio

from bella.anthropic_answerer import AnthropicAnswerer
from bella.config import Settings
from bella.course_content import CourseContent
from bella.scope_gate import RouteCategory


async def verify() -> None:
    settings = Settings.from_env()
    content = CourseContent.from_files(
        settings.knowledge_base_path, settings.enrollment_card_path
    )
    answerer = AnthropicAnswerer(settings.anthropic_api_key, content)
    question = "Em uma frase, qual é a duração do curso?"

    await answerer.answer(question, RouteCategory.COURSE_QUESTION)
    first = answerer.last_cache_usage
    await answerer.answer(question, RouteCategory.COURSE_QUESTION)
    second = answerer.last_cache_usage

    print(
        "First call cache usage: "
        f"creation={first.creation_input_tokens}, read={first.read_input_tokens}"
    )
    print(
        "Second call cache usage: "
        f"creation={second.creation_input_tokens}, read={second.read_input_tokens}"
    )
    if second.read_input_tokens <= 0:
        raise SystemExit("FAILED: the second request did not read prompt-cache tokens")
    print("OK: repeated answering request read the stable prefix from prompt cache.")


def main() -> None:
    asyncio.run(verify())


if __name__ == "__main__":
    main()

