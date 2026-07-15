# Spec: Bella Bot v1 — WhatsApp Course Concierge

Status: ready-for-agent

## Problem Statement

Prospective students of the SENAI Osasco course "IA Generativa Aplicada à Programação" have questions — what the course covers, whether it fits their level, when the next class starts, how to enroll — and today there is no always-available channel to answer them. The course also needs a living proof of its own pitch: the instructor demos "the kind of bot we can build at the course," and right now that demo doesn't exist on WhatsApp, where the audience actually is.

## Solution

Bella: a WhatsApp course concierge, reachable via the Evolution GO instance already running on the VPS. She answers questions about the course from a curated Knowledge Base, sends the apostila PDF as a native WhatsApp document, guides users to the SENAI enrollment page using an editable Enrollment Card, and strictly declines everything else through an injection-proof Scope Gate with Canned Refusals. She remembers each conversation, mirrors the user's language, and forwards a Handoff Notification to the course owner when a human is needed. She is herself the demo: "fui construída com as mesmas técnicas que você vai aprender no curso."

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
23. As a course owner, I want conversations idle for more than 30 days deleted automatically, so that data retention stays LGPD-friendly.
24. As a course owner, I want Bella to ignore group chats entirely, so that she never embarrasses the course in a classroom group.
25. As an operator, I want the service to run as a container on the existing VPS via Coolify, so that no new infrastructure is needed.
26. As an operator, I want Bella to reuse the Evolution stack's Postgres with her own database, so that no second database server consumes VPS resources.
27. As an operator, I want a health endpoint, so that Coolify can monitor and restart the service.
28. As an operator, I want the webhook endpoint to reject requests that don't carry the expected shared secret, so that outsiders can't inject fake messages.
29. As an operator, I want all secrets (Anthropic key, Evolution API key, DB password, webhook secret) supplied via environment variables, so that nothing sensitive lives in the repo.
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
- Answering call: `claude-opus-4-8`, adaptive thinking left at defaults, system prompt = persona + rules + Knowledge Base + Enrollment Card, marked with `cache_control` for prompt caching. Volatile content (history, user message) after the cached prefix.
- Output guard: strip/reject any URL in the answer that is not the configured SENAI enrollment URL.
- Intent handling for the apostila: when the user asks for the material, Bella sends the configured PDF via Evolution GO send-media (native WhatsApp document) with a short accompanying text. The PDF path is config; launch asset is the cleaned chapters 1–2 preview.
- Handoff: on "quero falar com uma pessoa" or an in-scope question Bella can't answer from her material, she replies with the SENAI contact from the Enrollment Card AND sends a Handoff Notification (user number + question summary) to the course owner's WhatsApp number via the same Evolution GO API.
- Language: reply in the user's language; Portuguese by default; mention that the course is taught in Portuguese when replying in another language.

**Content assets (editable without code changes)**
- Knowledge Base: one curated markdown file distilled from the Source Documents (pitch, arc of the 6 Saturdays, outcomes, audience/prerequisites, format, apostila description). Public-safe by construction.
- Enrollment Card: one config file — enrollment URL, unit, next turma dates, schedule, price, SENAI/owner contact. Bella answers volatile enrollment facts only from it; missing facts get an honest deflection plus the link.
- Canned Refusal templates: a small set of friendly pt-BR decline messages (with variants for other languages), rotated to avoid robotic repetition.

**Storage**
- Reuse the Evolution stack's Postgres 15 (internal-only at `postgres:5432` on the stack's Docker network; no published ports). Bella gets her own database (e.g. `bella`) in that instance — she never touches `evogo_auth`/`evogo_users`.
- Deployment consequence: the Bella container must join the Evolution compose stack's Docker network (deploy as a service in that stack, or attach via a shared Coolify network) to reach Postgres and `evolution-go:8080` internally.
- Schema: conversations keyed by phone number; messages with role, text, timestamp. Last ~20 messages loaded as answering context. A retention job deletes conversations idle > 30 days. Also a processed-message-id record for webhook dedupe.

**Evolution GO integration**
- Inbound: Evolution GO webhook configured to POST message events to Bella's endpoint. The endpoint validates a shared secret (header or URL token) and answers 200 quickly; processing is async so slow LLM calls never cause webhook retries/timeouts.
- Outbound: send-text and send-media calls to the Evolution GO HTTP API (internal `evolution-go:8080`, authenticated with the instance API key; `GLOBAL_API_KEY` is available in the stack). Exact endpoint paths/payloads to be confirmed against the running instance's docs during implementation.
- Filters: ignore group JIDs, ignore `fromMe` events, dedupe by message id, canned "text only" reply for non-text message types.

**Configuration and operations**
- All secrets via environment variables: Anthropic API key, Evolution API key, webhook shared secret, Postgres URL, owner notification number.
- Health endpoint for Coolify. Structured logging: message id, gate verdict, action taken, send result; log content minimally.
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

- Build-time inputs still needed from the course owner: Evolution GO instance name + API key + webhook setup, owner WhatsApp number for notifications, exact SENAI Osasco enrollment URL and turma details (dates/price/contact), and the cleaned chapters 1–2 preview PDF (can be generated from the Apostila docx).
- Evolution GO runs with `DATABASE_SAVE_MESSAGES: 'false'`, so Bella's own history store is the only message persistence — retention policy applies to the only copy.
- Cost expectation: ~US$0.01 per answered message (cached Opus prompt + Haiku gate); trivial at demo-bot volume.
- Glossary in `CONTEXT.md`; binding decisions in `docs/adr/0001` and `docs/adr/0002`.
