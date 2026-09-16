"""Markdown Inbox Writer for appending feedback issues to inbox.md."""

from datetime import datetime
from pathlib import Path

from bella.feedback_collector import FeedbackDraft

_MARKER = "<!-- Add new issues directly below this comment. -->"
_ISSUES_HEADER = "## Issues"


def format_inbox_block(
    draft: FeedbackDraft,
    phone_number: str,
    tracking_issue: str = "not created",
    timestamp: datetime | None = None,
) -> str:
    """Format a feedback draft into an inbox.md issue block."""
    if timestamp is None:
        timestamp = datetime.now().astimezone()
    iso_timestamp = timestamp.isoformat()

    return (
        f"### {draft.title}\n\n"
        f"- Reported at: {iso_timestamp}\n"
        f"- Status: needs-triage\n"
        f"- Verified at: not verified\n"
        f"- Verified by: not verified\n"
        f"- Tracking issue: {tracking_issue}\n"
        f"- Reporter: {phone_number}\n"
        f"- App: {draft.app_id}\n\n"
        f"**Observed:**\n\n"
        f"{draft.observed}\n\n"
        f"**Expected:**\n\n"
        f"{draft.expected}\n\n"
        f"**Evidence:**\n\n"
        f"{draft.evidence}"
    )


def append_to_inbox(
    inbox_path: Path,
    draft: FeedbackDraft,
    phone_number: str,
    tracking_issue: str = "not created",
    timestamp: datetime | None = None,
) -> None:
    """Append a structured feedback draft directly to inbox.md."""
    block = format_inbox_block(
        draft=draft,
        phone_number=phone_number,
        tracking_issue=tracking_issue,
        timestamp=timestamp,
    )

    if inbox_path.is_file():
        content = inbox_path.read_text(encoding="utf-8")
    else:
        content = f"# Issue inbox\n\n{_ISSUES_HEADER}\n\n{_MARKER}\n"

    if _MARKER in content:
        idx = content.find(_MARKER) + len(_MARKER)
        prefix = content[:idx]
        suffix = content[idx:].lstrip("\r\n")
        if suffix:
            new_content = f"{prefix}\n\n{block}\n\n{suffix}"
        else:
            new_content = f"{prefix}\n\n{block}\n"
    elif _ISSUES_HEADER in content:
        idx = content.find(_ISSUES_HEADER) + len(_ISSUES_HEADER)
        prefix = content[:idx]
        suffix = content[idx:].lstrip("\r\n")
        if suffix:
            new_content = f"{prefix}\n\n{block}\n\n{suffix}"
        else:
            new_content = f"{prefix}\n\n{block}\n"
    else:
        new_content = f"{content.rstrip()}\n\n{block}\n"

    inbox_path.parent.mkdir(parents=True, exist_ok=True)
    inbox_path.write_text(new_content, encoding="utf-8")
