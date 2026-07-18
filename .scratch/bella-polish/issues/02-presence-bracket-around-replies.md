# 02 — Presence bracket around every reply

**What to build:** A prospective student messaging Bella sees her come
online and show "typing…" while the reply is being produced, and sees the
indicator clear once the reply arrives — making the seconds of LLM latency
read as Bella thinking rather than the bot being broken.

The outbound sender protocol grows a chat-presence operation (composing and
cleared states toward a chat, plus the online/available signal); the
Evolution GO integration module, as the single normalization point for that
provider's wire shapes, owns the endpoint and payload details. The pipeline
brackets reply production: once it has decided a reply will be sent (after
dedupe, group, Takeover Pause, and rate-limit-silence checks) it signals
composing, and after the send completes or fails it clears the state. The
bracket wraps every user-visible reply path — LLM answers, Canned Refusals,
media replies, apostila delivery, rate-limit notices.

Presence is strictly best-effort: failures are logged and swallowed, never
feeding the error-reply path and never changing reply timing or content.
Paths that deliberately send nothing signal nothing: Takeover Pause,
rate-limit silence, groups, own echoes, control-channel traffic, dropped
events.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [x] A user message produces composing signalled before the send and
      cleared after, observable through the recording fake sender.
- [x] Every reply path is bracketed, including canned refusals and the
      apostila document path.
- [x] A presence failure still delivers the reply unchanged and logs the
      failure.
- [x] A conversation under a Takeover Pause generates no presence traffic;
      neither do rate-limit-silenced messages or group messages.
- [x] The Evolution GO presence request shape is covered by a
      normalization-layer test.
