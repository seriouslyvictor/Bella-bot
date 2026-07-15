"""Output guard for Bella's one-link policy (ADR-0002).

A model cannot be prompted into never emitting a URL, so the allowlist has to
sit on the output. Both patterns share one scheme alternation: a URL form that
reached only one of them would slip the policy.
"""

import re

_SCHEME = r"(?:https?://|www\.)"
URL_PATTERN = re.compile(rf"{_SCHEME}[^\s<>\])]+", re.IGNORECASE)
MARKDOWN_LINK_PATTERN = re.compile(rf"\[([^\]]+)]\(({_SCHEME}[^\s)]+)\)", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,!?;:"


def strip_foreign_urls(text: str, allowed_url: str) -> str:
    def replace_markdown(match: re.Match[str]) -> str:
        label, url = match.groups()
        return match.group(0) if url == allowed_url else label

    def replace_url(match: re.Match[str]) -> str:
        candidate = match.group(0)
        url = candidate.rstrip(TRAILING_PUNCTUATION)
        punctuation = candidate[len(url) :]
        return candidate if url == allowed_url else punctuation

    without_foreign_markdown = MARKDOWN_LINK_PATTERN.sub(replace_markdown, text)
    return URL_PATTERN.sub(replace_url, without_foreign_markdown)
