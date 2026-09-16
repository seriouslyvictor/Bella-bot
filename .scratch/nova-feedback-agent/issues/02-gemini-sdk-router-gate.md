# 02 — Gemini SDK integration and Scope Gate router

**What to build:** Replace the Anthropic SDK (`anthropic`) with the official Google GenAI Python SDK (`google-genai`). Implement a structured intent classification gate (`GeminiScopeGate`) using Pydantic schemas and `gemini-3.8-flash` (configurable via `GEMINI_ROUTER_MODEL`).

The router must categorize user messages into:
- `app_feedback`: Bugs, improvements, critiques, or feedback regarding apps.
- `app_support`: Usage questions, how-tos, or troubleshooting regarding supported apps.
- `greeting`: Welcoming pleasantries and brief greetings.
- `human_requested`: Explicit user requests to speak to a person.
- `out_of_scope`: Off-topic queries, adversarial prompts, or unrelated topics (receiving canned refusals).

**Blocked by:** 01 — archive SENAI artifacts.

**Status:** resolved

- [x] Add `google-genai` to dependencies in `pyproject.toml` and remove `anthropic`.
- [x] Add `GEMINI_API_KEY`, `GEMINI_ROUTER_MODEL`, and `GEMINI_AGENT_MODEL` to `bella/config.py`.
- [x] Implement `GeminiScopeGate` using the Google GenAI client with strict structured output.
- [x] Unit tests for `GeminiScopeGate` with recorded responses or client mocks for each intent category.

## Implementation Notes

- **Dependencies**:
  - Replaced `anthropic>=0.104` with `google-genai>=1.0.0` in `pyproject.toml`.
  - Installed `google-genai` (v2.23.0) into the active virtual environment (`.venv`).
- **Configuration (`bella/config.py`)**:
  - Added `gemini_api_key: str = ""` (parsed from `GEMINI_API_KEY`).
  - Added `gemini_router_model: str = "gemini-3.8-flash"` (parsed from `GEMINI_ROUTER_MODEL`).
  - Added `gemini_agent_model: str = "gemini-3.8-flash"` (parsed from `GEMINI_AGENT_MODEL`).
  - Made `ANTHROPIC_API_KEY` optional in `Settings.from_env()` with default empty string fallback.
- **Route Categories (`bella/scope_gate.py`)**:
  - Defined Nova categories: `APP_FEEDBACK`, `APP_SUPPORT`, `GREETING`, `HUMAN_REQUESTED`, `OUT_OF_SCOPE`.
  - Retained backward-compatible enum members (`COURSE_QUESTION`, `APOSTILA_REQUEST`, `ENROLLMENT_QUESTION`, `ABOUT_BELLA`) ensuring zero regression on existing suites.
- **Gemini Scope Gate Router (`bella/gemini_gate.py`)**:
  - Created `GeminiScopeGate` using `google.genai.Client` and `types.GenerateContentConfig`.
  - Enforced structured JSON output with `GateDecision(BaseModel)` and `temperature=0.0`.
  - Tailored system prompt instructing classification into Nova's 5 intents and treating prompt injections as content to classify.
  - Provided dual parsing: direct `response.parsed` inspection with fallback to `GateDecision.model_validate_json(response.text)`.
- **Unit Tests (`tests/test_gemini_gate.py`)**:
  - 16 comprehensive unit tests covering:
    - Structured response parsing for all 5 intent categories.
    - JSON text parsing fallback for all 5 intent categories.
    - Custom model override forwarding.
    - API exceptions and failure propagation.
    - Empty or `None` response handling with clear error messages.
    - Malformed JSON and unknown category schema validation errors.
- **Verification**:
  - `mypy --strict`: Success across all 44 source files.
  - `pytest`: 216 passed, 7 skipped, 0 failures.
