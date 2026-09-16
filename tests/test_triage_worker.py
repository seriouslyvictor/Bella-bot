"""Tests for Markdown Inbox Writer, GitHub Issue Publisher, and Triage Worker."""

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from bella.app_registry import AppConfig, AppRegistry
from bella.conversation_store import InMemoryConversationStore
from bella.feedback_collector import FeedbackDraft
from bella.inbox_writer import append_to_inbox, format_inbox_block
from bella.triage_worker import (
    GitHubIssuePublisher,
    TriageWorker,
    format_github_issue_body,
)


def test_format_inbox_block() -> None:
    draft = FeedbackDraft(
        app_id="report_generator9000",
        title="Erro no Playwright",
        observed="Browser crashed during PDF print",
        expected="PDF rendered cleanly",
        evidence="Error log code 137",
        is_complete=True,
    )
    timestamp = datetime(2026, 9, 15, 20, 0, 0, tzinfo=UTC)
    block = format_inbox_block(
        draft=draft,
        phone_number="5511999999999",
        tracking_issue="not created",
        timestamp=timestamp,
    )

    assert "### Erro no Playwright" in block
    assert "- Reported at: 2026-09-15T20:00:00+00:00" in block
    assert "- Status: needs-triage" in block
    assert "- Verified at: not verified" in block
    assert "- Verified by: not verified" in block
    assert "- Tracking issue: not created" in block
    assert "- Reporter: 5511999999999" in block
    assert "- App: report_generator9000" in block
    assert "**Observed:**\n\nBrowser crashed during PDF print" in block
    assert "**Expected:**\n\nPDF rendered cleanly" in block
    assert "**Evidence:**\n\nError log code 137" in block


def test_append_to_inbox_with_marker(tmp_path: Path) -> None:
    inbox_file = tmp_path / "inbox.md"
    initial_content = (
        "# Bella-bot issue inbox\n\n"
        "## Issues\n\n"
        "<!-- Add new issues directly below this comment. -->\n\n"
        "### Existing Issue\n\n"
        "- Reported at: 2026-01-01T00:00:00+00:00\n"
    )
    inbox_file.write_text(initial_content, encoding="utf-8")

    draft = FeedbackDraft(
        app_id="report_generator9000",
        title="Nova Falha",
        observed="Falha observada",
        expected="Esperado ok",
        evidence="Print",
        is_complete=True,
    )
    append_to_inbox(inbox_file, draft, "5511888888888")

    content = inbox_file.read_text(encoding="utf-8")
    marker_pos = content.find("<!-- Add new issues directly below this comment. -->")
    new_issue_pos = content.find("### Nova Falha")
    existing_pos = content.find("### Existing Issue")

    assert marker_pos != -1
    assert new_issue_pos != -1
    assert existing_pos != -1
    assert marker_pos < new_issue_pos < existing_pos


def test_append_to_inbox_without_marker_with_issues_header(tmp_path: Path) -> None:
    inbox_file = tmp_path / "inbox.md"
    initial_content = (
        "# Bella-bot issue inbox\n\n"
        "## Issues\n\n"
        "### Existing Issue\n"
    )
    inbox_file.write_text(initial_content, encoding="utf-8")

    draft = FeedbackDraft(
        app_id="report_generator9000",
        title="Nova Falha",
        observed="Obs",
        expected="Exp",
        evidence="Evi",
        is_complete=True,
    )
    append_to_inbox(inbox_file, draft, "5511888888888")

    content = inbox_file.read_text(encoding="utf-8")
    header_pos = content.find("## Issues")
    new_issue_pos = content.find("### Nova Falha")
    existing_pos = content.find("### Existing Issue")

    assert header_pos < new_issue_pos < existing_pos


def test_append_to_inbox_creates_file_if_not_exists(tmp_path: Path) -> None:
    inbox_file = tmp_path / "sub" / "inbox.md"
    assert not inbox_file.exists()

    draft = FeedbackDraft(
        app_id="report_generator9000",
        title="Primeira Falha",
        observed="Obs",
        expected="Exp",
        evidence="Evi",
        is_complete=True,
    )
    append_to_inbox(inbox_file, draft, "5511888888888")

    assert inbox_file.is_file()
    content = inbox_file.read_text(encoding="utf-8")
    assert "### Primeira Falha" in content
    assert "<!-- Add new issues directly below this comment. -->" in content


@pytest.mark.anyio
async def test_github_issue_publisher_success() -> None:
    captured_request: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request["url"] = str(request.url)
        captured_request["headers"] = dict(request.headers)
        captured_request["json"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            201,
            json={"html_url": "https://github.com/seriouslyvictor/report_generator9000/issues/99"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        publisher = GitHubIssuePublisher(token="ghp_test_token_123", client=client)
        url = await publisher.publish_issue(
            title="Bug no relatório",
            body="Detalhes do erro",
            owner_repo="seriouslyvictor/report_generator9000",
            labels=["needs-triage"],
        )

    assert url == "https://github.com/seriouslyvictor/report_generator9000/issues/99"
    assert (
        captured_request["url"]
        == "https://api.github.com/repos/seriouslyvictor/report_generator9000/issues"
    )
    assert captured_request["headers"]["authorization"] == "Bearer ghp_test_token_123"
    assert captured_request["headers"]["accept"] == "application/vnd.github+json"
    assert captured_request["json"]["title"] == "Bug no relatório"
    assert captured_request["json"]["body"] == "Detalhes do erro"
    assert captured_request["json"]["labels"] == ["needs-triage"]


@pytest.mark.anyio
async def test_github_issue_publisher_missing_token() -> None:
    publisher = GitHubIssuePublisher(token="")
    with pytest.raises(ValueError, match="GitHub token is required"):
        await publisher.publish_issue(title="Test", body="Body")


@pytest.mark.anyio
async def test_github_issue_publisher_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Bad credentials"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        publisher = GitHubIssuePublisher(token="ghp_bad_token", client=client)
        with pytest.raises(httpx.HTTPStatusError):
            await publisher.publish_issue(title="Test", body="Body")


@pytest.mark.anyio
async def test_triage_worker_process_pending_success() -> None:
    store = InMemoryConversationStore()
    phone = "5511999999999"
    draft = FeedbackDraft(
        app_id="report_generator9000",
        title="LibreOffice crash",
        observed="Erro ao processar",
        expected="Relatório ok",
        evidence="Pasta 115",
        is_complete=True,
    )
    staged_id = await store.stage_feedback(phone, draft)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            201,
            json={"html_url": f"https://github.com/seriouslyvictor/report_generator9000/issues/{staged_id}"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        publisher = GitHubIssuePublisher(token="ghp_dummy", client=client)
        worker = TriageWorker(store=store, publisher=publisher)

        published = await worker.process_pending()

    assert len(published) == 1
    assert published[0] == f"https://github.com/seriouslyvictor/report_generator9000/issues/{staged_id}"

    # Verify unprocessed is now empty
    unprocessed = await store.get_unprocessed_feedback()
    assert len(unprocessed) == 0

    # Staged item still exists in store with published status
    staged_record = store._staged_feedback[staged_id]
    assert staged_record.status == "published"
    assert staged_record.github_issue_url == published[0]
    assert staged_record.error_message is None


@pytest.mark.anyio
async def test_triage_worker_process_pending_failure_preserves_staging() -> None:
    store = InMemoryConversationStore()
    phone = "5511999999999"
    draft = FeedbackDraft(
        app_id="report_generator9000",
        title="LibreOffice crash",
        observed="Erro ao processar",
        expected="Relatório ok",
        evidence="Pasta 115",
        is_complete=True,
    )
    staged_id = await store.stage_feedback(phone, draft)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        publisher = GitHubIssuePublisher(token="ghp_dummy", client=client)
        worker = TriageWorker(store=store, publisher=publisher)

        published = await worker.process_pending()

    assert len(published) == 0

    # Unprocessed is empty because status is now 'failed'
    unprocessed = await store.get_unprocessed_feedback()
    assert len(unprocessed) == 0

    # Critical requirement: failures do NOT drop the local staging record!
    staged_record = store._staged_feedback[staged_id]
    assert staged_record.status == "failed"
    assert staged_record.error_message is not None
    assert "Internal Server Error" in staged_record.error_message
    assert staged_record.github_issue_url is None


@pytest.mark.anyio
async def test_triage_worker_custom_app_repo() -> None:
    store = InMemoryConversationStore()
    phone = "5511999999999"
    draft = FeedbackDraft(
        app_id="custom_app",
        title="Custom App Bug",
        observed="Erro",
        expected="Ok",
        evidence="Log",
        is_complete=True,
    )
    staged_id = await store.stage_feedback(phone, draft)

    app_registry = AppRegistry(
        apps={
            "custom_app": AppConfig(
                app_id="custom_app",
                name="Custom App",
                description="Desc",
                repo="org/custom_repo",
                knowledge_base="",
            )
        }
    )

    requested_url = ""

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requested_url
        requested_url = str(request.url)
        return httpx.Response(201, json={"html_url": "https://github.com/org/custom_repo/issues/1"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        publisher = GitHubIssuePublisher(token="ghp_dummy", client=client)
        worker = TriageWorker(store=store, publisher=publisher, app_registry=app_registry)
        published = await worker.process_pending()

    assert len(published) == 1
    assert "https://api.github.com/repos/org/custom_repo/issues" in requested_url
