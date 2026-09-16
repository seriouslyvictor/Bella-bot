# 04 — Adaptive feedback gathering state machine & confirmation invariant

**What to build:** An interactive feedback intake engine that guides users through reporting a bug, feature request, or critique.
- Identifies and confirms the target app (defaulting to `report_generator9000`).
- Adaptive extraction: if the user sends full details in one message, extract immediately; if details are missing (observed vs. expected, error message, steps), ask targeted follow-ups.
- Enforces the **confirmation invariant**: Nova *always* summarizes the draft ticket and requires explicit confirmation ("Sim", "Confirmo", "Pode enviar") before filing. Allows modification or cancellation.
- Tracks feedback conversation state per user phone number with persistent backing.

**Blocked by:** 03 — knowledge base and support.

**Status:** resolved

- [x] Implement `FeedbackState` (`IDLE`, `COLLECTING`, `CONFIRMING`) and draft data model (`app_id`, `title`, `observed`, `expected`, `evidence`).
- [x] Implement multi-turn feedback collector prompting for missing context.
- [x] Implement draft summary generator and confirmation validator.
- [x] Persist active feedback drafts in PostgreSQL so conversations can resume across process restarts.
- [x] Unit tests for single-turn extraction, multi-turn clarification, draft confirmation, and cancellation.

## Implementation Notes

- **Data Models & State Machine**: Implemented `FeedbackPhase` (with `FeedbackState` alias), `FeedbackDraft`, `FeedbackResult`, `ExtractedFeedback` in `bella/feedback_collector.py`.
- **Fast-path vs Multi-turn**:
  - Full details in single turn directly extracts complete draft and transitions to `AWAITING_CONFIRMATION` with formatted ticket summary.
  - Incomplete/vague details transitions to `COLLECTING` and prompts user with targeted follow-up question.
- **Confirmation Invariant & Matchers**:
  - Deterministic matcher `is_confirmation` checks confirmation phrases ("Sim", "Confirmo", "Pode enviar") and guards against negations.
  - Deterministic matcher `is_cancellation` matches cancellation words ("Cancela", "Não", "Esquece") and guards against negative cancellations ("não cancela").
  - `format_draft_summary` formats structured feedback summary in Portuguese with title, observed, expected, and evidence.
  - Active draft is cleared on confirmation or cancellation, resetting phase to `IDLE`.
  - User modifications during `AWAITING_CONFIRMATION` refine the draft using Gemini while keeping the confirmation invariant active.
- **Draft Persistence**:
  - Extended `ConversationStore` protocol with `get_feedback_draft`, `set_feedback_draft`, and `clear_feedback_draft`.
  - Implemented persistence in `InMemoryConversationStore`.
  - Implemented persistence in `PostgresConversationStore` backed by `active_feedback_drafts` table with `ON CONFLICT (phone_number) DO UPDATE`.
- **Testing & Verification**:
  - 10 unit tests in `tests/test_feedback_collector.py` covering fast-path single turn, multi-turn clarification, explicit confirmation, cancellation at both active phases, draft modification, format summary, and store lifecycle.
  - Added PostgreSQL persistence test in `tests/test_postgres_conversation_store.py`.
  - Verified with full test suite (231 passed) and `mypy --strict` (0 issues across 49 files).
