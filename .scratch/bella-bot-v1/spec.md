# Spec: Bella Bot v1 — WhatsApp Course Concierge

Status: ready-for-agent

## Problem Statement

Prospective students of the SENAI-SP course "IA Generativa Aplicada à Programação" have questions — what the course covers, whether it fits their level, when the next class starts, how to enroll — and today there is no always-available channel to answer them. The course also needs a living proof of its own pitch: the instructor demos "the kind of bot we can build at the course," and right now that demo doesn't exist on WhatsApp, where the audience actually is. The offering unit is a volatile fact owned by the Enrollment Card.

## Solution

Bella: a WhatsApp course concierge, deployed with Evolution GO 0.7.1 and PostgreSQL 15 as a single Docker Compose stack on the existing VPS via Coolify. The same production Compose file runs under the local Docker Engine, with a local-only port overlay, so development mirrors production. She answers questions about the course from a curated Knowledge Base, sends the apostila PDF as a native WhatsApp document, guides users to the SENAI enrollment page using an editable Enrollment Card, and strictly declines everything else through an injection-proof Scope Gate with Canned Refusals. She remembers each conversation, mirrors the user's language, and forwards a Handoff Notification to the course owner when a human is needed. She is herself the demo: "fui construída com as mesmas técnicas que você vai aprender no curso."

## User Stories

1. As a prospective student, I want to ask Bella what the course covers, so that I can decide whether it's right for me.
2. As a prospective student, I want to ask about prerequisites ("preciso saber programar?"), so that I know if I qualify.
3. As a prospective student, I want to ask about format and schedule (6 Saturdays, 48h), so that I can check it fits my routine.
4. As a prospective student, I want to ask what I will build during the course, so that I understand the practical outcomes.
5. As a prospective student, I want to ask when the next class (turma) starts and what it costs, so that I can plan enrollment.
6. As a prospective student, I want to receive the enrollment link when I ask how to sign up, so that I can enroll immediately.
7. As a prospective student, I want to request the apostila and receive it as a PDF document in the chat, so that I can preview the course material.
8. As a prospective student, I want Bella to remember what we discussed earlier in the conversation, so that I don't have to repeat myself across messages and days.
9. As a prospective student, I want honest answers ("isso eu não sei — confere na página de inscrição") when Bella lacks a fact, so that I'm never misled by an invented date or price.
10. As a prospective student writing in English or Spanish, I want Bella to reply in my language while noting the course is taught in Portuguese, so that I can still get informed.
11. As a prospective student, I want to ask for a human and receive the SENAI contact, so that I can resolve things Bella can't.
12. As a prospective student who sends a voice note or image, I want a friendly reply saying Bella only reads text for now, so that I know how to proceed.
13. As a prospective student, I want Bella to greet me warmly and explain what she can help with on first contact, so that I know what to ask.
14. As a prospective student, I want Bella to tell me she was built with the techniques taught in the course when I ask what/who she is, so that the demo sells itself.
15. As a curious or adversarial user, I want off-topic requests (homework, recipes, general ChatGPT use) politely declined with a fixed message, so that the bot stays on-mission.
16. As an adversarial user attempting prompt injection ("ignore suas instruções..."), I want my message to never reach the answering model when out of scope, so that the refusal cannot be manipulated.
17. As a course owner, I want internal details from the Source Documents (costs, contingency plans, infrastructure) to be impossible for the bot to reveal, so that prospects never see operational laundry.
18. As a course owner, I want a Handoff Notification forwarded to my WhatsApp when a user asks for a human or Bella can't answer an in-scope question, so that I can follow up personally.
19. As a course owner, I want to update the Enrollment Card (dates, price, URL, contact) by editing one config file, so that a new turma requires no code change.
20. As a course owner, I want to replace the apostila PDF by swapping one file, so that the final version ships without a deploy.
21. As a course owner, I want the Knowledge Base to be a reviewable markdown file, so that I can audit exactly what Bella is allowed to know.
22. As a course owner, I want the only link Bella ever sends to be the SENAI enrollment URL, so that she can never be tricked into sending arbitrary links.
23. As a course owner, I want conversations idle for more than 120 days deleted automatically, so that data retention stays LGPD-friendly.
24. As a course owner, I want Bella to ignore group chats entirely, so that she never embarrasses the course in a classroom group.
25. As an operator, I want Bella, Evolution GO 0.7.1, and PostgreSQL 15 deployed from GitHub as one Coolify Compose stack that also runs locally, so that local debugging mirrors the VPS.
26. As an operator, I want Bella and Evolution GO to share one PostgreSQL 15 server while using isolated databases, so that data stays separated without a second database server.
27. As an operator, I want separate liveness and dependency-aware readiness endpoints, so that Coolify can distinguish a running process from a bot that can persist and reply.
28. As an operator, I want the webhook endpoint to reject requests whose Evolution instance token is missing or incorrect, so that outsiders can't inject fake messages.
29. As an operator, I want all secrets (Anthropic key, Evolution global and instance keys, DB passwords) supplied via environment variables, so that nothing sensitive lives in the repo.
30. As an operator, I want structured logs of each message's path (gate verdict, answer/refusal, send result) without storing more content than necessary, so that I can debug behavior.
31. As an operator, I want Bella to deduplicate webhook deliveries and ignore her own outbound messages echoed back, so that she never loops or double-replies.
32. As an operator, I want per-number rate limiting, so that a flood from one user can't run up API costs.
33. As an operator, I want the answering call to use prompt caching on the stable system prompt, so that per-message cost stays around a cent.
34. As a developer, I want the whole pipeline testable by POSTing simulated webhooks with faked outbound boundaries, so that tests survive refactors.

## Implementation Decisions

Decisions below were settled in the grilling session; two are recorded as ADRs and are binding.

**Architecture and pipeline**
- One small Python + FastAPI service. Pipeline per inbound message: webhook → filter (groups, media, self-echo, dedupe) → Scope Gate → answer or Canned Refusal → reply via Evolution GO.
- ADR-0001: the Source Documents never enter any model context. The bot answers only from the curated Knowledge Base plus the Enrollment Card.
- ADR-0002: out-of-scope messages get a Canned Refusal sent verbatim — no generation on the refusal path. The answering prompt still carries scope rules as defense in depth.
- Scope Gate: `claude-haiku-4-5`, structured output, classifies in-scope (course content, apostila, enrollment, greetings/pleasantries, "who are you") vs out-of-scope.
- Answering call: `claude-sonnet-5`, thinking explicitly disabled for latency, system prompt = persona + rules + Knowledge Base + Enrollment Card, marked with `cache_control` for prompt caching. Volatile content (history, user message) after the cached prefix.
- Output guard: strip/reject any URL in the answer that is not the configured SENAI enrollment URL.
- Intent handling for the apostila: when the user asks for the material, Bella sends the configured PDF via Evolution GO send-media (native WhatsApp document) with a short accompanying text. The PDF path is config; launch asset is the cleaned chapters 1–2 preview.
- Handoff: on "quero falar com uma pessoa" or an in-scope question Bella can't answer from her material, she replies with the SENAI contact from the Enrollment Card AND sends a Handoff Notification (user number + question summary) to the course owner's WhatsApp number via the same Evolution GO API.
- Language: reply in the user's language; Portuguese by default; mention that the course is taught in Portuguese when replying in another language.

**Content assets (editable without code changes)**
- Knowledge Base: one curated markdown file distilled from the Source Documents (pitch, arc of the 6 Saturdays, outcomes, audience/prerequisites, format, apostila description). Public-safe by construction.
- Enrollment Card: one config file — enrollment URL, unit, next turma dates, schedule, price, SENAI/owner contact. Bella answers volatile enrollment facts only from it; missing facts get an honest deflection plus the link.
- Canned Refusal templates: a small set of friendly pt-BR decline messages (with variants for other languages), rotated to avoid robotic repetition.

**Storage**
- The unified stack owns one Postgres 15 service, internal-only at `postgres:5432` with persistent storage and no production host port. Separate login roles enforce the boundary: Bella owns only `bella`, while Evolution owns only `evogo_auth`/`evogo_users`.
- Bella, Evolution GO, and Postgres run in one Compose project and communicate over a Compose-managed network by stable service names: `evolution-go:8080` and `postgres:5432`. The stack has no dependency on an existing Coolify or VPS-specific external network.
- Schema: conversations keyed by phone number; messages with role, text, timestamp. The last 50 messages are loaded as answering context. A retention job deletes conversations idle > 120 days. Also a processed-message-id record for webhook dedupe.

**Evolution GO integration**
- Runtime image: official `evoapicloud/evolution-go:0.7.1`, pinned by both version and manifest digest. Version changes are explicit deployment decisions.
- Inbound: Evolution GO webhook configured to POST message events to Bella's fixed internal `/webhook` endpoint. Bella constant-time validates the top-level `instanceToken` present in 0.7.1 events against the configured instance token and answers authenticated events 200 quickly; processing is async so slow LLM calls never cause webhook retries/timeouts. A URL secret is deliberately avoided because 0.7.1 logs full webhook URLs.
- Outbound: send-text and send-media calls to the Evolution GO HTTP API at internal `evolution-go:8080`, authenticated with the instance token rather than `GLOBAL_API_KEY`. The Bella adapter and its tests target the 0.7.1 wire contract; the local stack provides the pinned runtime for smoke testing.
- Filters: ignore group JIDs, ignore `fromMe` events, dedupe by message id, canned "text only" reply for non-text message types.

**Configuration and operations**
- All secrets via environment variables: Anthropic API key, separate Evolution global/instance keys, separate Postgres role passwords, and owner notification number. Compose derives internal URLs and DSNs.
- `docker-compose.yml` is the authoritative production stack definition for local Docker Engine and Coolify deployment from GitHub; `docker-compose.local.yml` only adds loopback port bindings for local inspection.
- Evolution, Postgres, and Bella's Python base use immutable manifest digests; Bella installs a Python 3.12-resolved, hash-verified runtime lock so a later Coolify build cannot silently change the tested stack.
- Local configuration comes from an ignored `.env` based on `.env.example`; Coolify supplies the same variable contract in production. Internal service URLs and database DSNs are derived in Compose.
- Bella and Evolution state survive container recreation in one named Postgres volume; initialization deterministically creates separate owners and databases.
- `/health` reports process liveness; `/ready` checks Postgres and Evolution and drives the container/Coolify health status. Restart policies recover process exits, while unhealthy status requires alerting and operator remediation. Structured logging: message id, gate verdict, action taken, send result; log content minimally.
- Per-number rate limit (e.g. sliding window) with a canned "muitas mensagens" reply when exceeded.

## Testing Decisions

- Single test seam: the webhook endpoint, driven in-process (ASGI test client). Tests POST simulated Evolution GO webhook payloads and assert only on externally observable behavior.
- Three outbound boundaries are injected interfaces with fakes in tests: the LLM provider (scripted gate verdicts and answers), the WhatsApp sender (records sent texts/media), and the conversation store (in-memory fake for fast tests; real Postgres for a small integration suite).
- Good tests assert behavior, not implementation: "out-of-scope webhook → fake sender received a Canned Refusal verbatim AND the answer model was never called", "apostila request → send-media called with the configured PDF", "group message → nothing sent", "duplicate webhook → one reply", "handoff → owner number received a notification", "answer containing a foreign URL → link stripped/regenerated".
- Greenfield repo: no prior test art; this spec's suite establishes the pattern.

## Out of Scope

- Voice-note transcription and any media understanding (v2 candidate).
- Responding in group chats.
- Live human handoff/transfer (only the static contact + Handoff Notification).
- RAG/vector search — the Knowledge Base fits in the prompt.
- Admin UI or dashboard; content is edited as files/config.
- Telegram or any channel other than WhatsApp via Evolution GO.
- Enrollment inside the chat (payments, forms) — Bella only guides to the SENAI page.
- Multi-course support; Bella serves exactly this course.
- Automated re-curation of the Knowledge Base when Source Documents change (manual step by design, per ADR-0001).

## Further Notes

- Deployment-time inputs still needed from the course owner: Evolution GO instance name + token + pairing/webhook setup, owner WhatsApp number for notifications, enrollment URL and turma details owned by the Enrollment Card (dates/price/contact), and the cleaned chapters 1–2 preview PDF (can be generated from the Apostila docx).
- Evolution GO runs with `DATABASE_SAVE_MESSAGES: 'false'`, so Bella's own history store is the only message persistence — retention policy applies to the only copy.
- Cost expectation: ~US$0.01 per answered message (cached Opus prompt + Haiku gate); trivial at demo-bot volume.
- Glossary in `CONTEXT.md`; binding decisions in `docs/adr/0001` and `docs/adr/0002`.
