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
An editable config file (SENAI URL, unit, next class date, schedule, price) injected into the bot's context. The only source Bella may use for volatile enrollment facts; anything absent from it gets an honest deflection plus the link.

**Scope Gate**:
The classifier step every inbound message passes before any answer is generated. Labels a message in-scope (course, apostila, enrollment, greetings) or out-of-scope.
_Avoid_: filter, moderation (that's a different concern)

**Canned Refusal**:
A pre-written, friendly decline template sent verbatim when the Scope Gate rules a message out-of-scope. Contains no LLM generation, so it cannot be prompt-injected.

**Handoff Notification**:
The message forwarded to the course owner when a user asks for a human or Bella cannot answer an in-scope question. Bella also gives the user the SENAI contact from the Enrollment Card.

**Source Documents**:
The internal course files (Plano Mestre, Apostila) that the Knowledge Base is distilled from. Contain internal operational details and must never be exposed to the bot or users.
