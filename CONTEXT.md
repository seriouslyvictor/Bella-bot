# Bella Bot

WhatsApp course-concierge chatbot for the SENAI-SP course "IA Generativa Aplicada à Programação" (the offering unit is a volatile fact owned by the Enrollment Card). It answers prospective students' questions about the course, offers the apostila PDF, and guides users to enrollment — and declines everything else. It doubles as a live demo of the kind of assistant the course teaches students to build.

## Language

**Knowledge Base**:
The curated, public-facing distillation of the course documents that the bot answers from. It is the only course content that ever enters the LLM's context.
_Avoid_: raw docs, source documents (those are inputs to curation, never bot context)

**Bella**:
The WhatsApp course concierge — the course's own assistant persona, self-referential ("built with what the course teaches"). Talks to prospective students.
_Avoid_: conflating with the in-class Bella Vista demo

**Bella Vista Demo**:
The Bella Vista Cosméticos chatbot students build on Day 3 of the course. A classroom artifact, unrelated to this repo's runtime.

**Enrollment Card**:
The model-facing enrollment facts rendered into Bella's context. Its editable config owns the SENAI URLs, unit, next class date, schedule, and price; a fresh seat count may be injected only from the official SENAI availability holder. Stale or unavailable seat counts are omitted. The rendered Enrollment Card is the only source Bella may use for volatile enrollment facts; anything absent from it gets an honest deflection plus the link.

**Scope Gate**:
The classifier step every inbound message passes before any answer is generated. Labels a message in-scope (course, apostila, enrollment, greetings) or out-of-scope.
_Avoid_: filter, moderation (that's a different concern)

**Canned Refusal**:
A pre-written, friendly decline template sent verbatim when the Scope Gate rules a message out-of-scope. Contains no LLM generation, so it cannot be prompt-injected.

**Handoff Notification**:
The message forwarded to the course owner when a user asks for a human or Bella cannot answer an in-scope question. Bella also gives the user the SENAI contact from the Enrollment Card.

**Takeover**:
The course owner typing directly into a user's chat from Bella's own number. Implicitly starts a Takeover Pause for that conversation; no command is involved.
_Avoid_: handoff (that's the notification to the owner, which often precedes a takeover)

**Takeover Pause**:
The per-conversation sliding quiet period (default 1 hour, reset by every Takeover message) during which Bella stores messages but never answers them, because the human owns the conversation. The sanctioned exception to always-reply. Ends by expiry or by a resume command on the Control Channel.

**Control Channel**:
The path for owner commands to Bella. First source: messages from the admin contact number; recognized future source: the self-chat on Bella's own number. Commands never reach the Scope Gate or the LLM. Two commands: `voltar <numero>` ends a Takeover Pause, and `diag` runs the Self-Test.

**Self-Test**:
The `diag` command's dependency probe — database, WhatsApp gateway, router model, agent model, feedback extractor — reported back to the admin chat with each one's real error. It exists because every failure inside reply production degrades to the same canned apology, so without it an operator with no log access cannot tell an outage from a bad answer. The same error text is also pushed to the admin (throttled) the first time a reply fails.

**Owner** (message role):
A human-typed message sent from Bella's number in a user chat. Never Bella's own words; stored under a distinct role so the LLM cannot mistake a human's commitments for its own.

**Source Documents**:
The internal course files (Plano Mestre, Apostila) that the Knowledge Base is distilled from. Contain internal operational details and must never be exposed to the bot or users.
