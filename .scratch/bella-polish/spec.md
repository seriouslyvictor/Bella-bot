# Spec — Bella polish: live seat count, presence signalling, reaction handling

**Status:** ready-for-agent

Derived from the inbox triage session on 2026-07-18. Bundles the three
verified inbox items (live opening count, online/typing presence, message
reactions) into one polish pass. Canonical vocabulary: see CONTEXT.md
(Enrollment Card, Knowledge Base, Takeover, Takeover Pause, Owner role,
Canned Refusal, Scope Gate).

## Problem Statement

Three rough edges make Bella feel less trustworthy and less alive than a
human concierge:

1. **The seat count lies.** Bella always says 19 openings remain, because the
   seats value is a hand-edited field in the Enrollment Card. As enrollment
   progresses the real number drops, so the single fact most likely to push a
   prospective student to act is also the fact most likely to be wrong.
2. **Replies appear out of thin air.** Bella never shows online presence or a
   "typing…" indication while preparing a reply. Answers materialize without
   any visible activity, which reads as artificial — exactly the wrong
   impression for a bot whose sales pitch is being a live demo of the course.
3. **Reactions get a confused reply.** When a user reacts to a message with
   an emoji, Bella treats the reaction event as a message she cannot read and
   replies that she does not understand it. Worse, if the course owner reacts
   to a user's message from Bella's own number, that from-me event is
   currently indistinguishable from Takeover typing and would silence Bella
   in that chat for an hour.

## Solution

1. **Live seat count with a freshness policy.** The seats fact of the
   Enrollment Card stops being hand-edited and becomes sourced exclusively
   from the SENAI-SP course listing (the course's VER TURMAS class details) —
   the one source the reporter designated. A scheduled background refresher
   fetches the current availability and caches it with a fetch timestamp.
   Bella answers instantly from the cached value; when the value is older
   than the configured maximum age (or was never fetched), the seats fact is
   simply absent from the Enrollment Card, and the existing honest-deflection
   rule takes over: Bella says she cannot confirm the current count and gives
   the enrollment URL. Bella never falls back to a stale or hand-written
   number.
2. **Presence around every reply.** Every reply Bella sends to a user chat is
   bracketed by presence signalling: she appears online and shows "typing…"
   while the reply is being produced, and clears that state once the reply is
   sent. Presence is strictly best-effort — a presence failure is logged and
   never delays, blocks, or replaces a reply. Silence stays silent: no
   presence is signalled for conversations under a Takeover Pause,
   rate-limit-silenced traffic, group messages, or dropped events.
3. **Reactions are silently ignored.** Reaction events (including reaction
   removals) are recognized at the wire-normalization point and dropped
   before they ever become pipeline messages — regardless of emoji, of which
   message was reacted to, or of direction. No reply, no canned "I don't
   understand", no conversation-history entry, and, for from-me reactions, no
   Takeover Pause: the owner reacting 👍 to a user's message is not typing
   into the conversation and must not silence Bella. Ordinary messages that
   merely contain emoji continue through the normal pipeline untouched.

## User Stories

### Live seat count

1. As a prospective student, I want Bella to tell me the current number of openings for the course, so that I can trust her answer when deciding whether to enroll now.
2. As the course owner, I want the opening count read exclusively from the SENAI-SP class details behind the course's VER TURMAS action, so that Bella can never contradict the official enrollment system.
3. As the course owner, I want the count refreshed on a schedule in the background, so that conversations stay instant and no user ever waits on a SENAI-SP page load.
4. As a prospective student, I want Bella to say honestly that she cannot confirm the current count — and point me at the enrollment page — when the cached value is stale or missing, so that I am never misled by an outdated number.
5. As the course owner, I want Bella to never quote the old hand-written seat count as a fallback, so that a scraping outage degrades to honesty instead of to a lie.
6. As the course owner, I want to stop hand-editing the seats field when enrollment changes, so that the Enrollment Card cannot silently drift from reality.
7. As an operator, I want every failed fetch or parse of the SENAI-SP page logged with a reason, so that a page-structure change is noticed instead of silently starving the count.
8. As an operator, I want the refresh interval and the maximum acceptable age of the cached count configurable through the environment, so that freshness can be tuned without a code change.
9. As the course owner, I want a transient SENAI-SP outage to be invisible to users while the last good count is still within its maximum age, so that a hiccup does not immediately cost Bella her most persuasive fact.

### Presence and typing indication

10. As a prospective student, I want to see a "typing…" indication while Bella prepares her reply, so that the conversation feels like talking to a responsive person.
11. As a prospective student, I want Bella to appear online while she is handling my message, so that the interaction does not feel like messaging a machine that was never there.
12. As a prospective student, I want the typing indication cleared once the reply arrives, so that the chat never shows a phantom "typing…" after Bella has finished.
13. As a prospective student, I want the typing indication during LLM-answered questions especially, so that the seconds of generation latency read as Bella thinking rather than as the bot being broken.
14. As the course owner, I want presence signalling to be strictly best-effort, so that a presence hiccup can never delay, replace, or suppress an actual reply.
15. As the course owner, I want no typing indication in a conversation under a Takeover Pause, so that users never see the bot "typing" while I own the conversation.
16. As the course owner, I want no presence signalling for silenced traffic (rate-limit silence, group messages, dropped events), so that deliberate silence stays completely silent.

### Message reactions

17. As a WhatsApp user, I want my reaction to one of Bella's messages to be silently ignored, so that I never get a confusing "I don't understand" reply to a 👍.
18. As a WhatsApp user, I want removing a reaction to be ignored the same way, so that toggling a reaction never provokes a reply.
19. As a WhatsApp user, I want ordinary messages that contain emoji to still be answered normally, so that ignoring reactions never swallows a real message.
20. As the course owner, I want my own reactions sent from Bella's number to not start a Takeover Pause, so that acknowledging a user's message with a 👍 does not silence Bella in that chat for an hour.
21. As an operator, I want dropped reaction events visible in the logs, so that traffic remains observable even when Bella deliberately does nothing.

## Implementation Decisions

### Live seat count

- A new **availability source** abstraction owns the entire interaction with
  SENAI-SP at the HTTP boundary: fetching the designated course-listing page,
  locating the course "Inteligências Artificiais Generativas Aplicada a
  Programação - ChatGPT", following its VER TURMAS action to the class
  details, and parsing the current opening count out of them. This is the one
  new seam introduced by this spec (confirmed with the developer); page
  parsing lives entirely behind it.
- A **seat-count refresher** background job — following the pattern of the
  existing retention job started at application lifespan — invokes the
  availability source on a fixed interval and stores the parsed count with a
  fetched-at timestamp in a shared holder.
- The Enrollment Card remains the sole authority for volatile enrollment
  facts. The card presented to the answering model is rendered per answer
  with the live seats fact injected from the shared holder; the hand-edited
  `seats` field is removed from the editable card file so there is no stale
  value to fall back to. A fact that is absent is already handled by the
  existing honest-deflection grounding rule, which is exactly the desired
  stale-count behavior.
- Freshness policy: refresh interval defaulting to 6 hours and maximum
  acceptable age defaulting to 24 hours, both overridable through the
  environment. A failed refresh keeps the last good value until it exceeds
  the maximum age; after that the seats fact is omitted.
- Every anomaly — unreachable page, missing course row, missing VER TURMAS
  target, unparseable availability — is one and the same failure mode: log a
  warning with the reason and count the refresh as failed. A page-structure
  change therefore degrades to the honest deflection within one maximum-age
  window, never to a wrong number.
- The SENAI-SP course-listing URL that seeds the fetch is a new field of the
  editable Enrollment Card file, next to the enrollment URL it already owns.
- Known trade-off: the Enrollment Card context block is prompt-cached; a
  changed count invalidates that cache entry. At a multi-hour refresh cadence
  this cost is negligible and the single-authority rule wins.

### Presence and typing indication

- The outbound sender protocol grows a chat-presence operation (composing and
  paused/cleared states toward a specific chat, plus the online/available
  signal). The Evolution GO integration module — the declared single
  normalization point for that provider's wire shapes — owns the endpoint and
  payload details.
- The pipeline brackets reply production: once it has decided a reply will be
  sent (after dedupe, group, Takeover Pause, and rate-limit-silence checks),
  it signals composing; after the send completes (or fails), it clears the
  state. The bracket wraps every user-visible reply path — LLM answers,
  Canned Refusals, media replies, apostila delivery, rate-limit notices.
- All presence calls are fire-and-best-effort: failures are logged and
  swallowed; they never feed the error-reply path and never change reply
  timing or content.
- Paths that deliberately send nothing signal nothing: Takeover Pause,
  rate-limit silence, groups, own echoes, control-channel traffic to the
  admin, and dropped reaction events.

### Message reactions

- Reaction deliveries (and reaction removals) are recognized and dropped at
  the wire-normalization point, before a pipeline message exists. They are
  logged and produce no delivery claim, no reply, no history entry, no
  presence, and no Takeover signal.
- Consequence made explicit: a from-me reaction is not Takeover typing.
  Consistent with ADR 0003's definition of Takeover as the owner *typing*
  into a chat — a reaction is an annotation on an existing message, not a
  turn in the conversation, so it must not arm or extend a Takeover Pause.
- Text extraction for ordinary messages is unchanged; a normal message whose
  body is only emoji still flows through the Scope Gate pipeline.

## Testing Decisions

- Tests assert external behavior only: what came in through the webhook, what
  the sender was asked to do, what the stored conversation looks like — never
  internal call sequences.
- **Reactions and presence** ride the existing highest seam: POST a simulated
  Evolution GO webhook delivery through the test client and assert on the
  recording fake sender (the established pattern of the webhook and takeover
  test suites). The fake sender grows presence-recording alongside its
  existing send-recording. Cases: a reaction delivery is acked with no sends
  and no pause armed (a follow-up user message still gets answered); a
  from-me reaction does not pause the conversation; an emoji-only text
  message is still answered; a user message shows composing signalled before
  the send and cleared after; a presence failure still delivers the reply; a
  paused conversation generates no presence traffic.
- **Seat count** tests sit behind the new availability-source seam: a fake
  source returns canned SENAI-SP page payloads or programmed failures, and a
  fake clock drives the freshness policy. Cases: a successful refresh puts
  the live count into the rendered Enrollment Card fact; a failure inside the
  maximum age keeps the last good count; beyond the maximum age the seats
  fact is omitted; every anomaly logs a warning. The real page-parsing logic
  is covered against captured fixture payloads inside the seam.
- Wire-shape coverage follows the existing Evolution GO normalization tests:
  reaction payload recognition on the way in, presence request shape on the
  way out.
- Prior art: the webhook/takeover suites for pipeline behavior, the retention
  job tests for the background-job pattern, and the answerer system-block
  unit tests for context rendering.

## Out of Scope

- Real-time or on-demand seat fetching and bounded-cache hybrids — the triage
  decision was scheduled background refresh only.
- Any richer reaction semantics: sentiment capture, storing reactions in
  conversation memory, or Bella reacting back.
- Persistent always-online presence, read receipts, or presence outside the
  reply bracket.
- Changes to the Scope Gate, group policy, input filters (Bella v1 ticket
  09), or Takeover mechanics beyond the explicit reaction exemption.
- Notifying the owner when the seat count changes or reaches zero.

## Further Notes

- All three decisions (background refresh, ignore-all reactions, single
  combined spec) were made by the user during the 2026-07-18 triage of
  `inbox.md`; the three inbox entries now track this spec.
- The 6-hour/24-hour freshness defaults are proposals sized to how fast
  course enrollment actually moves; they are environment-tunable and can be
  revisited once the first real turma's numbers are observed.
- If SENAI-SP ever exposes a structured availability endpoint, only the
  availability source behind the seam needs to change.
