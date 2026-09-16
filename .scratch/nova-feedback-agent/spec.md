# Spec — Nova: WhatsApp Feedback Concierge & Issue Triage Agent

**Status:** ready-for-agent

Derived from the design and grilling session on 2026-09-15. Replaces the SENAI course-concierge role with Nova, an interactive WhatsApp feedback agent powered by the Google GenAI SDK (Gemini). Nova identifies user intent, answers app support questions from a grounded knowledge base, guides users through structured feedback collection for target applications (starting with `report_generator9000`), and triages confirmed reports simultaneously into local markdown, PostgreSQL, and GitHub Issues.

Canonical vocabulary: Scope Gate / Router Agent, Canned Refusal, Takeover, Takeover Pause, Owner role, Echo Ledger, Feedback Gathering Flow, Issue Confirmation Invariant, Triaged Inbox.

---

## Problem Statement

Software teams building production apps often receive unstructured bug reports, feature requests, and complaints across fragmented channels (direct chat messages, emails, verbal comments). When users reach out via WhatsApp:

1. **Bug reports arrive incomplete or vague.** Users frequently say "it doesn't work" without mentioning which app they are using, what they expected to happen, what error they saw, or what steps led to the issue.
2. **Triage requires manual back-and-forth.** Developers must spend time asking follow-up questions, synthesizing the conversation into a ticket, and manually opening issues in repository trackers.
3. **Unconfirmed or hallucinated tickets pollute the backlog.** An autonomous assistant that files issues without a human confirmation step risks misinterpreting user intent or filing inaccurate details.
4. **General inquiries distract from triage.** Users also ask how-to questions or off-topic queries; without clear scope classification and grounded support answers, the assistant either acts like an open-ended generic chatbot or fails to answer basic app questions.

---

## Solution

Transform the WhatsApp bot into **Nova**, a warm, technical concierge representing the company:

1. **Gemini-Powered Intent Router (Scope Gate):**
   Every incoming text message is classified by a fast Gemini model into distinct intents:
   - `app_feedback`: Reporting a bug, feature request, or UX feedback.
   - `app_support`: Asking how-to questions or troubleshooting about the target app.
   - `greeting`: Polite greetings and pleasantries.
   - `human_requested`: Requesting a human representative.
   - `out_of_scope`: Off-topic queries, adversarial probes, or general knowledge questions.
   Out-of-scope messages receive pre-written canned refusals (zero LLM generation, preserving prompt-injection resistance).

2. **Grounded App Support:**
   In-scope support questions are answered concisely using a curated, public-facing knowledge base for the target application (starting with `report_generator9000`), strictly disallowing fabrication or hallucinated URLs.

3. **Adaptive Feedback Dialogue with Mandatory Confirmation:**
   When feedback intent is detected:
   - Nova assumes and confirms the default target application (`report_generator9000`).
   - If the user provided full details in their opening message (observed behavior, expected behavior, context), Nova extracts them directly without asking redundant questions.
   - If key information is missing, Nova asks targeted clarifying questions.
   - **Confirmation Invariant:** Nova *always* summarizes the draft issue and requires explicit user confirmation before any issue is published.

4. **Multi-Destination Issue Triage:**
   Upon user confirmation, Nova simultaneously:
   - Appends the formatted ticket to the repository's local inbox file with canonical triage labels (`needs-triage`).
   - Persists the record in a durable PostgreSQL table to survive container restarts.
   - Opens a GitHub Issue on the target repository (`seriouslyvictor/report_generator9000`) via the GitHub API.
   - Sends the user a confirmation message on WhatsApp with the created issue reference/link.

5. **Operational Continuity:**
   Preserves core production infrastructure: WhatsApp gateway integration (Evolution GO), PostgreSQL message deduplication and history, implicit human takeover pause, typing presence simulation, and rate limiting.

---

## User Stories

### Intent Routing & Scope

1. As a user messaging Nova, I want my intent to be understood quickly, so that I am guided to the right response without friction.
2. As a user asking an off-topic question (e.g. general trivia or unrelated code), I want a polite canned decline explaining Nova's role, so that the bot remains focused on our company's apps.
3. As a company owner, I want out-of-scope refusals to contain zero LLM generation, so that prompt-injection attacks cannot alter Nova's refusal responses.
4. As a user greeting Nova, I want a welcoming, natural Portuguese greeting introducing her as Nova, so that I know what she can help me with.
5. As a user asking to speak to a person, I want immediate contact details and an alert forwarded to the team, so that a human can assist me promptly.

### App Support & Knowledge Grounding

6. As a user of `report_generator9000`, I want to ask how to generate a report or resolve spreadsheet issues, so that I can unblock my work directly in WhatsApp.
7. As a product engineer, I want Nova's support answers grounded strictly in the target app's knowledge base, so that she never invents features or instructions that do not exist.
8. As a user, I want concise, WhatsApp-friendly responses rather than walls of text, so that the guidance is readable on mobile.

### Feedback Collection & Confirmation

9. As a user reporting a bug, I want Nova to recognize that I am providing feedback about `report_generator9000`, so that I don't have to navigate a complex menu.
10. As a user who already gave a complete bug description in my initial message, I want Nova to skip redundant questions and proceed straight to confirmation, so that I don't waste time repeating myself.
11. As a user who sent a vague complaint (e.g., "the PDF generation failed"), I want Nova to ask what happened versus what was expected and what error was shown, so that the team gets actionable reproduction context.
12. As a user submitting feedback, I want Nova to present a clear draft summary (title, app, what happened, expected behavior, context) before anything is saved, so that I can verify my report is accurate.
13. As a product engineer, I want an issue filed *only* after explicit user confirmation, so that the issue tracker is not filled with accidental or misunderstood tickets.
14. As a user, I want the ability to adjust or cancel my feedback draft during the confirmation step, so that mistakes can be corrected before submission.

### Multi-Destination Issue Publishing

15. As a product engineer, I want confirmed feedback automatically appended to the local inbox markdown file, so that local development workflows and agent triage see new items immediately.
16. As an operator, I want confirmed issues stored in PostgreSQL, so that reports are never lost if the container restarts or local files are rebuilt.
17. As a developer maintaining `report_generator9000`, I want confirmed reports created as GitHub Issues with the `needs-triage` label, so that our team can manage them in our standard project tracker.
18. As a user who just reported an issue, I want to receive the GitHub Issue link or ticket number on WhatsApp, so that I can track progress on my feedback.
19. As an operator, I want the bot to degrade gracefully if the GitHub API is unreachable (saving to local markdown and PostgreSQL, and logging the error), so that the user's feedback is never lost.

### Operational Safety & Takeover

20. As a company owner, I want to type directly in a WhatsApp conversation from Nova's number to seamlessly take over the chat, so that Nova immediately pauses and does not talk over me.
21. As a company owner, I want to send `voltar <phone>` to resume Nova's automated responses in a paused conversation, so that I can hand the conversation back to the bot when I'm done.
22. As a user sending messages rapidly, I want a rate limit notice followed by temporary silence if flooding occurs, so that the service remains protected against abuse.
23. As a user chatting with Nova, I want to see a typing presence indicator while she prepares answers, so that the interaction feels natural.

---

## Implementation Decisions

### 1. Persona & Branding Configuration
- The bot's external display name and persona is configured as **Nova**.
- Internal package naming remains unchanged to eliminate unnecessary refactoring risks.
- System prompts are written in Portuguese (PT-BR), presenting Nova as a warm, knowledgeable technical concierge.

### 2. Gemini Client & Model Strategy
- Replace the Anthropic SDK with the official Google GenAI Python SDK (`google-genai`).
- Introduce environment-driven model selection with resilient defaults:
  - `GEMINI_ROUTER_MODEL`: Defaults to `gemini-3.8-flash` (or `gemini-3.5-flash-lite` for high-throughput).
  - `GEMINI_AGENT_MODEL`: Defaults to `gemini-3.8-flash`.
- Router decisions utilize Gemini structured output with strict Pydantic schemas.
- Generation utilizes explicit system instructions, temperature 0 for predictable routing, and structured schemas for feedback extraction.

### 3. Target Application Registry
- Implement an application registry configuration holding metadata for supported apps:
  - Identifier (`report_generator9000`).
  - Display name and short description.
  - GitHub repository (`seriouslyvictor/report_generator9000`).
  - App-specific knowledge base path.
- The system defaults to `report_generator9000` for initial conversations, while maintaining an extensible architecture that accepts additional apps in the future without pipeline rewrites.

### 4. Adaptive Feedback State Machine
- Maintain conversation state per phone number tracking the feedback intake lifecycle:
  - `IDLE`: Normal conversation, routed per message.
  - `COLLECTING_FEEDBACK`: Asking targeted clarifying questions to complete required fields (observed, expected, evidence/context).
  - `AWAITING_CONFIRMATION`: Draft issue presented; awaiting explicit confirmation ("Sim", "Confirmo") or modification/cancellation.
- In-memory state with PostgreSQL backing ensures multi-turn feedback collection survives process restarts.

### 5. Decoupled Two-Phase Triage (Dual-LLM & Staging Boundary)
In accordance with the Dual-LLM security pattern and Anthropic/Google Cloud agentic best practices:
1. **Intake Agent (Nova - Quarantined):** Interacts with the user on WhatsApp. Holds **zero GitHub credentials or mutation tools**. Collects and validates details (`observed`, `expected`, `evidence`), obtains user confirmation, and emits a structured Pydantic payload.
2. **Staging & Local Persistence (Trust Boundary):** Immediately persists the confirmed feedback into PostgreSQL (`feedback_staging` table) and appends to the local `inbox.md` (`needs-triage`). Nova sends an instant confirmation reply to the user (<1.5s), avoiding WhatsApp webhook timeouts.
3. **Triage & Publishing Worker (Privileged Background Agent):** Runs asynchronously (via FastAPI background tasks or dedicated worker) with isolated `GITHUB_TOKEN` credentials. Performs issue deduplication/validation against `seriouslyvictor/report_generator9000`, creates the GitHub Issue with canonical label `needs-triage`, and updates the staging record with the issue URL. Optionally notifies the user on WhatsApp with the resulting issue link.

### 6. Archiving SENAI Artifacts
- Move SENAI-specific course documents, syllabus PDFs, enrollment configuration, and the SENAI availability scraper to an `archive/senai/` directory.
- Replace `content/knowledge_base.md` with distilled documentation of `report_generator9000` (domain concepts, spreadsheet requirements, common issues, and usage rules).

---

## Testing Decisions

### What Makes a Good Test
Tests must verify external behavioral contracts and invariants, never private implementation details. A good test asserts:
- Inbound webhooks produce expected outbound WhatsApp messages and presence states.
- Out-of-scope messages trigger verbatim canned refusals without invoking generative models.
- Complete feedback messages trigger draft summaries with confirmation requests.
- Confirmed feedback writes to the local inbox, stores to PostgreSQL, and calls the GitHub API.
- Human owner typing triggers an implicit takeover pause.

### Testing Seams
The primary testing seam is the **FastAPI Webhook endpoint (`POST /webhook`)** with injected collaborators:
- **WhatsApp Sender Seam**: In-memory fake capturing sent texts, documents, and presence signals.
- **Gemini Client Seam**: Protocol-level fake or recorded structured responses for routing and feedback extraction.
- **Database Seam**: PostgreSQL test container / in-memory conversation and feedback store.
- **GitHub API Seam**: HTTP mock for GitHub REST issue creation endpoints.

Testing at this single highest seam validates the complete asynchronous pipeline from webhook ingestion to delivery deduplication, rate limiting, routing, feedback dialog, issue persistence, and outbound WhatsApp replies.

### Prior Art
- `tests/test_webhook.py`: Exhaustive end-to-end webhook integration tests covering deduplication, routing, canned refusals, and rate limiting.
- `tests/test_conversation_store.py` and `tests/test_postgres_conversation_store.py`: Persistence and schema migration testing.
- `tests/test_control_channel.py`: Command parsing and takeover pause management.

---

## Out of Scope

- Multi-tenant authentication (Nova represents one company across direct WhatsApp chats).
- WhatsApp Group chat participation (Nova drops group messages per existing policy).
- In-chat image/screenshot OCR processing (media messages receive a canned reply requesting text descriptions; media captions are captured as evidence).
- Automatic bidirectional GitHub issue comment syncing back into WhatsApp chats (once an issue is filed and link provided, conversation stays focused on immediate feedback).

---

## Further Notes

- The GitHub integration requires `GITHUB_TOKEN` set in the environment with `repo` (issues:write) permission.
- The knowledge base for `report_generator9000` should be kept concise and focused on common user workflows and error recovery to maintain low latency and context token efficiency.
