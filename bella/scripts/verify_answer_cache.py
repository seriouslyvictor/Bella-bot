"""Verify the answering prefix is read from cache on a repeated call."""

import asyncio

from anthropic import AsyncAnthropic

from bella.anthropic_answerer import AnthropicAnswerer
from bella.config import Settings
from bella.course_content import CourseContent
from bella.scope_gate import RouteCategory


async def verify() -> None:
    settings = Settings.from_env()
    content = CourseContent.from_files(
        settings.knowledge_base_path, settings.enrollment_card_path
    )
    client = AsyncAnthropic(api_key=settings.anthropic_api_key, max_retries=1)
    answerer = AnthropicAnswerer(client, content)
    question = "Em uma frase, qual é a duração do curso?"

    await answerer.answer(question, RouteCategory.COURSE_QUESTION, [])
    first = answerer.last_cache_read_tokens
    await answerer.answer(question, RouteCategory.COURSE_QUESTION, [])
    second = answerer.last_cache_read_tokens

    print(f"First call cache read tokens: {first}")
    print(f"Second call cache read tokens: {second}")
    if second <= 0:
        raise SystemExit("FAILED: the second request did not read prompt-cache tokens")
    print("OK: repeated answering request read the stable prefix from prompt cache.")


def main() -> None:
    asyncio.run(verify())


if __name__ == "__main__":
    main()
