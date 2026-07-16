# Implicit takeover: human activity on Bella's number pauses the bot

The course owner takes over a conversation by simply typing into the user's
chat from Bella's own WhatsApp number — the act of typing *is* the signal.
Any human-typed, from-me message pauses Bella in that conversation for a
sliding window (default 1 hour, config-tunable, reset by every further human
message). We rejected an explicit pause command because its failure mode is
the exact scenario the feature exists to prevent: the owner forgets the
command and Bella answers on top of them mid-conversation. The failure mode
of the implicit signal — Bella staying quiet slightly too long — is bounded
and cheap, and an explicit early-resume command (`voltar <número>` from the
admin contact number) covers it.

## Consequences

- Bella's own replies also arrive as from-me webhooks, so the pipeline keeps
  a ledger of the message IDs it sends and registers the expected outgoing
  (number, text) *before* the send call, to close the race where the webhook
  echo beats the send response. Without this, Bella would pause herself after
  every reply.
- During a Takeover Pause, user messages are stored but never answered — a
  deliberate exception to the pipeline's "always send the user a reply"
  invariant, because the human owns the reply obligation. Do not "fix" the
  silence.
- Resume is forward-only and silent: no backlog answering, no announcement.
  From the user's side there is one continuous number.
- Both sides of the human conversation are recorded; owner messages use a
  distinct `owner` role (schema migration widens the role CHECK) and are
  marked as the human's words on LLM replay, so Bella never inherits a human
  promise as her own.
- Pause state persists in Postgres (`paused_until` on `conversations`), so a
  restart mid-takeover does not wake Bella.
