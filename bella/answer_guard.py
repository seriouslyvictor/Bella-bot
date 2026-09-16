"""Output guard for the one-link policy (ADR-0002).

A model cannot be prompted into never emitting a URL, so the allowlist has to
sit on the output. Both patterns share one scheme alternation: a URL form that
reached only one of them would slip the policy.

The allowlist is a sequence, not a single string: a deployment legitimately has
more than one address it may name (the app, the docs), and passing the empty
sequence keeps the strictest reading — no URL survives. Callers go through
``bella.response.ResponsePolicy``, which applies this to model-authored text
only; a reply Nova wrote herself is not scrubbed of her own links.
"""

import re
from collections.abc import Sequence

_SCHEME = r"(?:https?://|www\.)"
# The emphasis a model wraps a URL in is part of the URL as far as a greedy
# match is concerned, so it is captured explicitly: without this, the `**` of
# `**https://example.com**` lands inside the candidate, the comparison against
# the allowlist fails, and an allowed link is deleted — or a removed one leaves
# its orphaned asterisks behind in the reply.
_EMPHASIS = r"(?:\*{1,2}|_{1,2}|~{1,2}|`)"
URL_PATTERN = re.compile(
    rf"(?P<lead>{_EMPHASIS})?(?P<url>{_SCHEME}[^\s<>\])]+)", re.IGNORECASE
)
MARKDOWN_LINK_PATTERN = re.compile(rf"\[([^\]]+)]\(({_SCHEME}[^\s)]+)\)", re.IGNORECASE)
SENTENCE_PUNCTUATION = ".,!?;:"
# Everything that may trail a URL without belonging to it.
TRAILING_PUNCTUATION = SENTENCE_PUNCTUATION + "*_~`\"'"
_LEFTOVER_SPACES = re.compile(r"[ \t]{2,}")
_SPACE_BEFORE_PUNCTUATION = re.compile(r"[ \t]+(?=[.,!?;:])")


def strip_foreign_urls(text: str, allowed_url: str | Sequence[str]) -> str:
    """Remove every URL that is not on the allowlist, keeping link labels."""
    if isinstance(allowed_url, str):
        allowed = {allowed_url} if allowed_url else set()
    else:
        allowed = {url for url in allowed_url if url}

    def replace_markdown(match: re.Match[str]) -> str:
        label, url = match.groups()
        return match.group(0) if url in allowed else label

    def replace_url(match: re.Match[str]) -> str:
        candidate = match.group("url")
        url = candidate.rstrip(TRAILING_PUNCTUATION)
        if url in allowed:
            return match.group(0)
        # Drop the emphasis that wrapped the removed URL, but keep punctuation
        # that belongs to the sentence around it.
        return "".join(
            character
            for character in candidate[len(url) :]
            if character in SENTENCE_PUNCTUATION
        )

    without_foreign_markdown = MARKDOWN_LINK_PATTERN.sub(replace_markdown, text)
    guarded = URL_PATTERN.sub(replace_url, without_foreign_markdown)
    if guarded == text:
        return guarded
    # A removed URL leaves the gap it used to fill; without this the reply
    # reaches the user with "Veja  para detalhes ." instead of a clean sentence.
    collapsed = _LEFTOVER_SPACES.sub(" ", guarded)
    return _SPACE_BEFORE_PUNCTUATION.sub("", collapsed)


def find_urls(text: str) -> tuple[str, ...]:
    """Every URL in trusted text, so an allowlist can be derived from it."""
    return tuple(
        match.group("url").rstrip(TRAILING_PUNCTUATION)
        for match in URL_PATTERN.finditer(text)
    )
