# Spec — Human Takeover: implicit pause when the owner types in a chat

**Status:** ready-for-agent

Derived from a grilling/domain-modeling session on 2026-07-16. Canonical
vocabulary: see CONTEXT.md (Takeover, Takeover Pause, Control Channel, Owner
role). Governing decision record: ADR 0003 — implicit takeover pauses Bella.

## Problem Statement

Bella handles prospective-student conversations end to end, but sometimes the
course owner wants to step into a specific conversation personally — to close
an enrollment, negotiate, or answer something only a human can. Today there is
no way to do that safely: the owner and Bella share one WhatsApp number, and if
the owner starts typing, Bella keeps answering on top of them, embarrassing
the owner mid-conversation with a prospective student. The owner needs Bella
to stop responding in that one chat, temporarily, without ceremony.

## Solution

Implicit Takeover, per ADR 0003. The act of the owner typing into a user's
chat from Bella's own number *is* the signal: any human-typed, from-me message
starts a Takeover Pause for that conversation — a sliding quiet window
(default 1 hour, configurable) reset by every further human message. During
the pause Bella stores messages but sends nothing; the human owns the reply
obligation. The pause ends by expiry or by a `voltar <número>` command sent
over the Control Channel (messages from the admin contact number). Resume is
forward-only and silent — from the user's side there is one continuous number.
Both sides of the human conversation are recorded, with the owner's words
stored under a distinct Owner role so Bella can never mistake a human
commitment for her own.

## User Stories

1. As the course owner, I want to take over a conversation by simply typing into the user's chat from Bella's number, so that I never have to remember a command in the moment.
2. As the course owner, I want Bella to stop replying in a conversation I have taken over, so that she never answers on top of me mid-negotiation.
3. As a prospective student, I want the human takeover to happen in the same chat from the same number, so that the conversation feels continuous and seamless.
4. As a prospective student, I want no bot interjections while I am talking with the human, so that the conversation is not confusing or duplicated.
5. As the course owner, I want every message I type to reset the pause window, so that a slow evening conversation with long gaps is never interrupted by the bot.
6. As the course owner, I want Bella to resume automatically after an hour of my inactivity in that chat, so that a conversation I forgot about does not become a dead number for the user.
7. As the course owner, I want media messages I send (photo, audio, document) to also re-arm the pause, so that human activity counts regardless of message type.
8. As the course owner, I want an early-resume command (`voltar <número>`) sent from my admin number, so that I can hand a conversation back to Bella before the window expires.
9. As the course owner, I want a confirmation reply when I issue `voltar`, so that I know the command took effect.
10. As the course owner, I want an honest reply when `voltar` targets a conversation that is not paused, so that I am never left guessing about state.
11. As the course owner, I want control commands handled deterministically — never routed through the Scope Gate or an LLM — so that takeover control cannot be misclassified or prompt-injected.
12. As the course owner, I want ordinary (non-command) messages from my admin number to flow through the normal pipeline, so that I can test Bella from my own phone.
13. As a prospective student, I want my messages during a takeover recorded in conversation memory, so that Bella has context if I refer back to them later.
14. As the course owner, I want my in-chat messages recorded under a distinct Owner role, so that Bella never repeats or elaborates on a promise only I can make.
15. As a prospective student, I want Bella to make no announcements when pausing or resuming, so that I never see the seams between bot and human.
16. As a prospective student, I want Bella not to answer stale questions from during the takeover after she resumes, so that I don't get out-of-context replies to things the human already handled.
17. As the course owner, I want the pause to survive a service restart, so that a redeploy mid-takeover does not wake Bella into my conversation.
18. As the course owner, I want Bella's own outgoing replies (which also arrive as from-me webhook echoes) never to trigger a pause, so that the bot does not silence itself after every answer.
19. As the operator, I want the pause duration to be a configuration knob with a 1-hour default, so that I can tune it after real use without a code change.
20. As a prospective student, I want rate-limit notices and non-text canned replies suppressed during a takeover, so that the human truly owns the whole conversation.
21. As the course owner, I want takeover to have no effect in group chats, so that Bella's existing never-speak-in-groups rule stays absolute.
22. As the operator, I want duplicate webhook deliveries still deduplicated during a pause, so that pause bookkeeping is not corrupted by redelivery.
23. As a future maintainer, I want the Control Channel parser to be source-agnostic, so that the self-chat on Bella's own number can be added as a second command source without redesign.

## Implementation Decisions

- **From-me classification.** The pipeline stops dropping from-me messages
  unconditionally. A from-me message is Bella's own echo if its provider
  message ID is in a ledger of IDs the pipeline sent; otherwise it is a
  Takeover message. The sender interface widens: send operations return the
  provider message ID of the sent message.
- **Echo race closure.** The expected outgoing (recipient, text) is registered
  in the ledger *before* the send call is made, and the provider ID is added
  when the call returns — so a webhook echo that beats the send response still
  matches by (recipient, text). Without this Bella would pause herself after
  every reply (ADR 0003, consequence 1).
- **Ledger bounds.** The ledger is in-process and bounded (LRU-style eviction,
  same spirit as the existing per-recipient refusal rotation). A ledger miss
  after eviction or a restart mis-reads one echo as human and pauses one
  conversation for the window — a bounded, invisible failure accepted by
  design.
- **Pause state.** A `paused_until` timestamp on the existing conversations
  record, exposed through new conversation-store contract methods (read pause
  state, set/extend pause, clear pause). Both store implementations (in-memory
  and Postgres) honor the contract; persistence makes pauses restart-safe.
- **Sliding semantics.** Every human-typed from-me message in a user chat sets
  `paused_until = now + window`. The window is a new settings knob, default
  1 hour. Pause expiry checks use an injectable wall-clock, mirroring the
  existing injectable rate-limit clock.
- **During the pause.** Inbound user messages are still deduplicated and still
  appended to conversation memory, but produce no reply of any kind: no
  Scope Gate call, no LLM call, no Canned Refusal, no rate-limit notice, no
  media reply. This is the sanctioned exception to the pipeline's always-reply
  invariant (ADR 0003, consequence 2).
- **Owner role.** The message-role vocabulary gains `owner` alongside `user`
  and `assistant`; the Postgres role CHECK constraint widens accordingly
  (migration on existing deployments). Owner-typed text messages are stored
  under this role; owner media messages re-arm the pause but store nothing.
  On replay into the answering LLM, owner messages are explicitly framed as
  the human owner's words, never Bella's.
- **Control Channel.** Inbound messages from the admin contact number are
  checked against a command parser before the Scope Gate. `voltar <número>`
  (number matching digits-only, tolerant of formatting) clears the pause for
  that conversation and replies to the admin with a confirmation, or with a
  not-paused notice. Unrecognized admin messages fall through to the normal
  pipeline. The parser takes a command text plus reply-target, independent of
  which source delivered it, so the self-chat source can be added later.
- **Resume.** Forward-only: only messages arriving after expiry or `voltar`
  get bot replies; no backlog processing. Silent: no user-facing announcement
  on pause or resume.
- **Group and admin chats.** From-me messages in group chats stay ignored
  (Bella never speaks in groups). Human from-me messages in the admin chat may
  technically pause that "conversation"; harmless and not special-cased.

## Testing Decisions

- All behavior is tested through the existing webhook seam: POST simulated
  Evolution GO webhook payloads, assert only on the fake sender's outbox and
  HTTP responses. No new seams. Prior art: the existing webhook behavioral
  test suite and its test-client factory.
- The fake sender returns deterministic provider message IDs so tests can
  replay Bella's own echoes (must not pause) versus foreign from-me messages
  (must pause), including the echo-beats-send-response race.
- Pause expiry is driven by the injectable clock, mirroring how rate-limit
  tests already control time — no sleeps.
- Owner-role recording and LLM framing are observed through the fake
  answerer's captured histories, not by inspecting storage internals.
- Pause-state persistence methods are covered by the existing per-implementation
  store test pattern (shared contract exercised against the in-memory store;
  Postgres-marked tests for the real store, including the CHECK-constraint
  migration on a pre-existing schema).
- Good tests here assert external behavior only: who received which messages,
  and what history the answerer saw. Ledger internals, SQL, and parser
  structure are not asserted on.

## Out of Scope

- The self-chat command source (recognized future Control Channel source; the
  parser must merely not preclude it).
- Any explicit *pause* command — pausing is implicit only (ADR 0003).
- Answering backlog messages on resume, or any pause/resume announcements.
- Takeover in group chats.
- Multiple human agents, takeover assignment, or any dashboard/UI.
- Changes to the Handoff Notification flow (it already exists and often
  precedes a takeover, but is untouched here).
- Rate-limit accounting changes beyond suppressing notices during a pause.

## Further Notes

- The Handoff Notification the owner already receives contains the user's
  number — the natural copy source for `voltar <número>`.
- Expected usage of `voltar` is rare (the 1-hour slide usually suffices); it
  exists as the escape hatch that makes a longer-than-needed pause cheap.
- The always-reply invariant's docstring should be updated to name the
  Takeover Pause as its one sanctioned exception, so a future reader does not
  "fix" the silence as a bug.
