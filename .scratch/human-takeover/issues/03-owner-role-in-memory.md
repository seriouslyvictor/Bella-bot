# 03 — Owner role in conversation memory

**What to build:** During a Takeover, both sides of the human conversation
land in Bella's memory. The owner's in-chat text messages are recorded under a
new, distinct `owner` message role — never as Bella's own words — so that when
Bella resumes and the user refers back to the human conversation, she has the
context and cannot inherit a human commitment (a discount, a promise) as her
own.

- The message-role vocabulary gains `owner` alongside `user` and `assistant`;
  the Postgres role constraint widens accordingly, and the widening must be
  safe to apply to an existing deployed schema.
- Owner-typed text messages in a user chat are appended to that conversation's
  history under the `owner` role. Owner media messages still only re-arm the
  pause (ticket 02) and store nothing.
- On replay into the answering LLM, owner messages are explicitly framed as
  the human owner's words, clearly distinguished from Bella's, so the model
  deflects follow-ups about human commitments instead of elaborating on them.

**Blocked by:** 02 — Implicit Takeover Pause, end to end.

**Status:** ready-for-agent

- [x] An owner text message during a takeover is stored under the `owner` role in that conversation's history
- [x] After resume, the fake answerer's captured history contains the owner message, framed as the human owner's words and distinguishable from assistant turns
- [x] The Postgres role constraint accepts `owner`, and applying the schema to a database created by the previous version succeeds (Postgres-marked test)
- [x] Owner media messages store nothing (pause re-arm only)
- [x] Verified through the webhook seam and the fake answerer's histories — no storage-internal assertions
