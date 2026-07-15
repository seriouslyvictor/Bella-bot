"""Output guard for Bella's one-link policy."""

import re

URL_PATTERN = re.compile(r"(?:https?://|www\.)[^\s<>\])]+", re.IGNORECASE)
MARKDOWN_LINK_PATTERN = re.compile(
    r"\[([^\]]+)]\(((?:https?://|www\.)[^\s)]+)\)", re.IGNORECASE
)
TRAILING_PUNCTUATION = ".,!?;:"


class AllowedUrlGuard:
    def __init__(self, allowed_url: str) -> None:
        self._allowed_url = allowed_url

    def apply(self, text: str) -> str:
        def replace_markdown(match: re.Match[str]) -> str:
            label, url = match.groups()
            return match.group(0) if url == self._allowed_url else label

        without_foreign_markdown = MARKDOWN_LINK_PATTERN.sub(replace_markdown, text)

        def replace_url(match: re.Match[str]) -> str:
            candidate = match.group(0)
            url = candidate.rstrip(TRAILING_PUNCTUATION)
            punctuation = candidate[len(url) :]
            return candidate if url == self._allowed_url else punctuation

        return URL_PATTERN.sub(replace_url, without_foreign_markdown)
