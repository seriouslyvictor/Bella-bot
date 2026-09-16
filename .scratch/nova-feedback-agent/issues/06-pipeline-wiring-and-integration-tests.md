# 06 — Pipeline wiring, deployment config, and end-to-end integration tests

**What to build:** Wire all Nova components together in `bella/pipeline.py`, `bella/composition.py`, and `bella/app.py`. Update `docker-compose.yml` and environment contracts with `GEMINI_API_KEY` and `GITHUB_TOKEN`. Update end-to-end integration tests in `tests/test_webhook.py` verifying the full pipeline at the highest seam (`POST /webhook`).

**Blocked by:** 05 — multi-sink issue publisher.

**Status:** resolved

- [x] Update `Pipeline` to orchestrate `GeminiScopeGate`, `GeminiSupportAnswerer`, `FeedbackCollector`, and `IssuePublisher`.
- [x] Wire the production object graph in `bella/composition.py`.
- [x] Update `docker-compose.yml`, `Dockerfile`, and `.env.example`.
- [x] Update and expand `tests/test_webhook.py` covering the complete lifecycle:
  - Intent routing and canned out-of-scope refusals.
  - App support queries answered from knowledge base.
  - Complete feedback report fast-path to confirmation.
  - Vague feedback prompting follow-ups.
  - Confirmed feedback writing to `inbox.md`, database, and calling GitHub mock.
  - Implicit takeover pause and resume command via admin control channel.
- [x] Verify full test suite passes cleanly with `pytest` and `mypy --strict`.

## Implementation Notes

- **Pipeline Wiring** (`bella/pipeline.py`):
  - Updated `Pipeline` to accept `feedback_collector`, `support_answerer`, and `triage_worker`.
  - Implemented session-first routing: active feedback sessions (draft phase not IDLE) are routed directly to `feedback_collector.process_turn`.
  - When user confirms a draft, `triage_worker.process_pending()` is scheduled as a tracked background task (`self._background_tasks`).
  - Implemented intent-routed branches for `OUT_OF_SCOPE` (canned refusal rotation), `GREETING` (canned greeting response), `HUMAN_REQUESTED` (handoff reply + admin notification), `APP_FEEDBACK` (enters collector), and `APP_SUPPORT` (answers via support answerer).
  - Background tasks are awaited on pipeline close for clean shutdown.
- **Production Object Graph** (`bella/composition.py`):
  - Replaced legacy Anthropic dependencies with Nova collaborators: `google-genai` client, `GeminiScopeGate`, `AppRegistry`, `GeminiSupportAnswerer`, `FeedbackCollector`, `GitHubIssuePublisher`, and `TriageWorker`.
  - Created `Runtime` holding configured `Pipeline` and `TriageWorker`.
- **Configuration & Container Contracts**:
  - Replaced `ANTHROPIC_API_KEY` with `GEMINI_API_KEY`, `GEMINI_ROUTER_MODEL`, `GEMINI_AGENT_MODEL`, `GITHUB_TOKEN`, and `BELLA_DISPLAY_NAME=Nova` across `.env.example`, `docker-compose.yml`, and `bella/config.py`.
  - Added `APPS_DIR` and `INBOX_PATH` to `Dockerfile` and `Settings`.
  - Removed obsolete SENAI seat count environment variables.
  - Updated `tests/test_deployment_stack.py` compose assertions.
- **End-to-End Integration Tests** (`tests/test_webhook.py`):
  - Added test suite for Nova lifecycle through the highest seam (`POST /webhook`):
    - `test_nova_out_of_scope_canned_refusal`: verifies canned refusal for out-of-scope input.
    - `test_nova_greeting_pleasantry_reply`: verifies canned pleasantry for greetings.
    - `test_nova_app_support_answered_from_knowledge_base`: verifies KB answering for support questions.
    - `test_nova_feedback_lifecycle_fast_path_confirm_and_publish`: covers full two-turn cycle: fast-path extraction to `AWAITING_CONFIRMATION` summary -> user confirmation -> staging in DB -> markdown inbox append -> background triage publication to GitHub mock.
    - `test_nova_feedback_vague_prompts_clarification_then_confirms`: verifies multi-turn clarification on incomplete input.
    - `test_nova_feedback_cancellation_clears_state`: verifies explicit cancellation resets state and clears active draft.
- **Verification**:
  - Full test suite: 247 passed, 10 skipped in 4.22s.
  - Strict type checking: `mypy --strict` passes with 0 errors across 52 source files.
