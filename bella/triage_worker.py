"""Background triage worker and GitHub issue publisher for staged feedback."""

import logging
from typing import Sequence

import httpx

from bella.app_registry import AppRegistry
from bella.conversation_store import ConversationStore, StagedFeedback

logger = logging.getLogger(__name__)

DEFAULT_OWNER_REPO = "seriouslyvictor/report_generator9000"


class GitHubIssuePublisher:
    """Publishes issues to GitHub via REST API."""

    def __init__(
        self,
        token: str,
        base_url: str = "https://api.github.com",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._client = client

    async def publish_issue(
        self,
        title: str,
        body: str,
        owner_repo: str = DEFAULT_OWNER_REPO,
        labels: Sequence[str] | None = None,
    ) -> str:
        if not self._token:
            raise ValueError("GitHub token is required to publish issues")

        if labels is None:
            labels = ["needs-triage"]

        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "Nova-Feedback-Concierge",
        }
        payload = {
            "title": title,
            "body": body,
            "labels": list(labels),
        }
        url = f"{self._base_url}/repos/{owner_repo}/issues"

        if self._client is not None:
            response = await self._client.post(url, json=payload, headers=headers)
        else:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers)

        response.raise_for_status()
        data = response.json()
        html_url = data.get("html_url")
        if not html_url:
            raise ValueError("GitHub API response did not contain html_url")
        return str(html_url)


def format_github_issue_body(feedback: StagedFeedback) -> str:
    """Format staged feedback into markdown for GitHub issue body."""
    return (
        f"### Nova Feedback Intake\n\n"
        f"- **Reporter:** {feedback.phone_number}\n"
        f"- **App:** {feedback.app_id}\n"
        f"- **Staged ID:** {feedback.id}\n"
        f"- **Created At:** {feedback.created_at.isoformat()}\n\n"
        f"#### Observed\n\n"
        f"{feedback.observed}\n\n"
        f"#### Expected\n\n"
        f"{feedback.expected}\n\n"
        f"#### Evidence\n\n"
        f"{feedback.evidence}"
    )


class TriageWorker:
    """Consumes staged feedback and publishes to GitHub in the background."""

    def __init__(
        self,
        store: ConversationStore,
        publisher: GitHubIssuePublisher,
        app_registry: AppRegistry | None = None,
    ) -> None:
        self._store = store
        self._publisher = publisher
        self._app_registry = app_registry

    async def process_pending(self, limit: int = 10) -> list[str]:
        """Process pending staged feedback items."""
        unprocessed = await self._store.get_unprocessed_feedback(limit=limit)
        published_urls: list[str] = []

        for item in unprocessed:
            owner_repo = DEFAULT_OWNER_REPO
            if self._app_registry is not None:
                try:
                    app_config = self._app_registry.get_app(item.app_id)
                    owner_repo = app_config.repo
                except KeyError:
                    pass

            body = format_github_issue_body(item)
            try:
                url = await self._publisher.publish_issue(
                    title=item.title,
                    body=body,
                    owner_repo=owner_repo,
                    labels=["needs-triage"],
                )
                await self._store.mark_feedback_published(item.id, url)
                published_urls.append(url)
            except Exception as exc:
                logger.warning(
                    "Failed to publish staged feedback %s: %s", item.id, exc
                )
                await self._store.mark_feedback_failed(item.id, str(exc))

        return published_urls
