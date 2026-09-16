# 05 — Decoupled staging and background triage worker (Markdown inbox, PostgreSQL, GitHub)

**What to build:** Decouple the user-facing Intake Agent from GitHub mutations via a Staging Boundary:
1. **Intake & Local Staging:** When a user confirms a feedback draft, Nova persists the structured record to PostgreSQL (`feedback_staging` table) and appends to `inbox.md` (`needs-triage`). Nova immediately confirms to the user on WhatsApp (<1.5s), holding zero GitHub credentials.
2. **Asynchronous Triage Worker:** A background worker (FastAPI `BackgroundTask` or queue consumer) with isolated `GITHUB_TOKEN` credentials reads the staged item, validates/deduplicates against `seriouslyvictor/report_generator9000`, creates the GitHub Issue with label `needs-triage`, and updates the staging row with the issue URL.
3. **Follow-up Notification:** (Optional/configurable) Sends a follow-up WhatsApp message to the user with the created issue link once published.

**Blocked by:** 04 — feedback dialogue state machine.

**Status:** resolved

- [x] Add `feedback_staging` table schema and persistence operations to `PostgresConversationStore`.
- [x] Implement `MarkdownInboxWriter` appending to `inbox.md`.
- [x] Implement `TriageWorker` / `GitHubIssuePublisher` running in background with isolated `GITHUB_TOKEN`.
- [x] Ensure the user receives an immediate WhatsApp response upon confirmation, without waiting for GitHub API latency.
- [x] Unit tests verifying that the webhook never hangs on GitHub API calls and failures in GitHub retry safely without dropping local staging records.

## Implementation Notes

- **Staging Storage**:
  - Defined `StagedFeedback` dataclass in `bella/conversation_store.py`.
  - Added staging operations (`stage_feedback`, `get_unprocessed_feedback`, `mark_feedback_published`, `mark_feedback_failed`) to `ConversationStore` protocol.
  - Implemented staging in `InMemoryConversationStore` with incremental IDs and status tracking.
  - Implemented staging in `PostgresConversationStore` with `feedback_staging` table in `_SCHEMA_STATEMENTS`.
- **Markdown Inbox Writer**:
  - Implemented `bella/inbox_writer.py` with `format_inbox_block` and `append_to_inbox`.
  - Inserts new issues immediately below `<!-- Add new issues directly below this comment. -->` (or under `## Issues`).
- **GitHub Publisher & Background Triage Worker**:
  - Implemented `GitHubIssuePublisher` in `bella/triage_worker.py` calling `POST /repos/{owner_repo}/issues` with isolated `GITHUB_TOKEN` and label `needs-triage`.
  - Implemented `TriageWorker` in `bella/triage_worker.py` processing staged items, updating status to `published` on success or `failed` with error message on failure.
  - Failure guarantees that local staging records are retained and never dropped.
- **Config**:
  - Added `github_token` and `inbox_path` to `Settings` in `bella/config.py`.
- **Fast-path Local Intake**:
  - Updated `FeedbackCollector` in `bella/feedback_collector.py` to stage locally and append to `inbox.md` upon user confirmation, immediately returning a WhatsApp response (<1.5s) without calling GitHub synchronously.
- **Verification**:
  - 10 unit tests in `tests/test_triage_worker.py` covering formatting, file creation, marker-based insertion, publisher requests, mock HTTP errors, and worker success/failure retention.
  - Integration lifecycle tests in `tests/test_postgres_conversation_store.py`.
  - Full test suite passing: 241 passed, 10 skipped.
  - `mypy --strict` passes with 0 issues across 52 source files.
