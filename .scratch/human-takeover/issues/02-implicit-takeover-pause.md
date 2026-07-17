# 02 — Implicit Takeover Pause, end to end

**What to build:** The core Takeover behavior from ADR 0003, demoable on its
own. When the course owner types into a user's chat from Bella's own number,
Bella goes quiet in that conversation; she wakes up on her own an hour later.

From the user's and owner's perspective:

- Any human-typed from-me message (text or media) in a user chat starts a
  Takeover Pause for that conversation. No command, no announcement.
- Bella's own outgoing replies — which also arrive as from-me webhook echoes —
  never trigger a pause. The pipeline keeps a bounded in-process ledger of
  what it sent; the expected outgoing (recipient, text) is registered *before*
  the send call so an echo that beats the send response still matches, and the
  provider ID is added when the send returns.
- Every further human message re-arms the sliding window: a new settings knob,
  default 1 hour. Expiry checks use an injectable wall-clock, mirroring the
  existing injectable rate-limit clock.
- During the pause, inbound user messages are still deduplicated and still
  appended to conversation memory, but produce no reply of any kind: no Scope
  Gate call, no LLM call, no Canned Refusal, no rate-limit notice, no media
  reply. This is the sanctioned exception to the always-reply invariant —
  update that invariant's stated contract to name it.
- Resume on expiry is forward-only and silent: no backlog answering, no
  announcement.
- Pause state is persisted on the conversation record through new
  conversation-store contract methods (read / set-extend / clear), honored by
  both store implementations, so a restart mid-takeover does not wake Bella.
- From-me messages in group chats stay ignored entirely.

Owner-message *storage* (the `owner` role) is ticket 03 — in this ticket a
human from-me message only affects pause state; nothing is stored for it yet.

**Blocked by:** 01 — Prefactor: senders return provider message IDs.

**Status:** ready-for-agent

- [ ] A foreign from-me text message in a user chat pauses that conversation: subsequent user messages get stored but receive no send of any kind
- [ ] A foreign from-me media message also pauses/re-arms
- [ ] Bella's own echo (matching ledger ID, or matching recipient+text when the echo beats the send response) does not pause
- [ ] Each human message resets the window; a user message arriving after the injected clock passes expiry gets a normal reply, and unanswered pause-era messages are never answered (forward-only)
- [ ] No announcement is sent on pause or resume
- [ ] Pause duration is a config knob defaulting to 1 hour
- [ ] Pause state survives a service restart (persisted in both store implementations; Postgres-marked tests cover the real store)
- [ ] Duplicate webhook deliveries are still deduplicated during a pause
- [ ] Group-chat from-me messages remain ignored
- [ ] All behavior verified through the webhook seam: posted payloads in, fake-sender outbox out
