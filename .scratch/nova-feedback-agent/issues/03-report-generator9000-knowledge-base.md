# 03 — Grounded knowledge base and support for report_generator9000

**What to build:** Create an app registry and replace the SENAI knowledge base with curated documentation for `report_generator9000` (SEBRAETEC technical report generation, spreadsheet inputs, stages, PDF rendering, Word masters, and common failure modes). Implement `GeminiSupportAnswerer` to provide grounded answers for user questions about `report_generator9000`. Update canned replies with Nova's warm, technical persona in PT-BR.

**Blocked by:** 02 — Gemini SDK integration.

**Status:** resolved

- [x] Define the application configuration schema (`AppConfig`) holding app ID, name, description, repo, and knowledge base.
- [x] Create `content/apps/report_generator9000.md` with distilled public operational knowledge from `D:\report_generator9000`.
- [x] Implement `GeminiSupportAnswerer` answering strictly from the grounded knowledge base.
- [x] Update `content/canned_replies.yaml` for Nova (greetings, out-of-scope refusals, rate-limit notices, media replies).
- [x] Unit tests for `GeminiSupportAnswerer` asserting grounded answers and honest deflections.

## Implementation Notes

- **AppConfig & AppRegistry (`bella/app_registry.py`)**:
  - Implemented `AppConfig` dataclass (`app_id`, `name`, `description`, `repo`, `knowledge_base`).
  - Implemented `AppRegistry` with support for multiple apps, default fallback to `report_generator9000`, and automatic loading from `content/apps/`.
- **Knowledge Base (`content/apps/report_generator9000.md` & `content/knowledge_base.md`)**:
  - Curated comprehensive documentation distilled from `D:\report_generator9000`:
    - Architecture & SEBRAETEC Final Technical Report (`RELATÓRIO TÉCNICO FINAL`).
    - Canonical vocabulary: Demanda, Pasta, Temas (`Inserção digital - Desenvolvimento de WebSite`, `Implantação de Loja Virtual`), Especialista, Run, 9 Stages, Masters (`MASTER.docx`, `MASTER-LOJA-VIRTUAL.docx`), Tokens (`{{NOME}}`), Slots, Blocks, Lista de Páginas, Sources of truth, and Placeholders (`GATED`, `TOOL_BLOCKED`, `UNDECLARED`, `REVIEW`).
    - Automated pipeline stages, Playwright captures, and LibreOffice headless PDF generation.
    - Troubleshooting guide: spreadsheet formatting, site timeouts, missing Gated Inputs, storefront checkout pendências.
    - Docker container execution and development ports (8000 backend, 5173 frontend).
  - Synchronized `content/knowledge_base.md` to reflect `report_generator9000`.
- **GeminiSupportAnswerer (`bella/gemini_answerer.py`)**:
  - Implemented `GeminiSupportAnswerer` adhering to the `Answerer` protocol and returning `AnswerResult`.
  - Configured with Nova persona: warm, polite, and technical assistant in PT-BR representing the company.
  - Strict grounding rules with Pydantic structured output (`SupportAnswerPayload` with `answer` and `needs_handoff`).
  - Supports conversation history translation, human takeover preservation (`<owner_message>`), and prompt-injection resistance.
- **Canned Replies (`content/canned_replies.yaml`)**:
  - Updated refusals, media reply, rate limit reply, and error reply to reflect Nova's identity as technical concierge for `report_generator9000`.
  - Retained required legacy translation keys ensuring 100% backward compatibility for existing webhook tests.
- **Unit Tests (`tests/test_gemini_answerer.py`)**:
  - 6 unit tests covering:
    - Grounded questions answered from knowledge base with `needs_handoff=False`.
    - Unknown questions answered with honest deflection and `needs_handoff=True`.
    - Fallback JSON text parsing.
    - Empty response and empty answer error handling (`ValueError`).
    - Framing of history, owner message markers, and role translation.
- **Verification**:
  - `mypy --strict`: Success across all 47 source files.
  - `pytest`: 222 passed, 7 skipped, 0 failures.
