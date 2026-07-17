# 04 — Control Channel: `voltar` early resume

**What to build:** The owner's escape hatch for ending a Takeover Pause before
it expires. Messages from the admin contact number pass through a command
parser *before* the Scope Gate; commands are handled deterministically and
never touch an LLM, so takeover control cannot be misclassified or
prompt-injected.

- `voltar <número>` clears the Takeover Pause for that conversation and Bella
  replies to the admin with a confirmation. Number matching is digits-only and
  tolerant of formatting (the owner will paste from a Handoff Notification,
  which is the natural copy source).
- `voltar` for a conversation that is not paused gets an honest "not paused"
  notice — the owner is never left guessing about state.
- Unrecognized messages from the admin number fall through to the normal
  pipeline unchanged, so the owner can still test Bella from their own phone.
- The parser is source-agnostic: it takes command text plus a reply target,
  independent of which channel delivered it, so the self-chat on Bella's own
  number can be added as a second Control Channel source later without
  redesign (recognized future source; out of scope here).
- Resume via `voltar` behaves exactly like resume via expiry: forward-only and
  silent toward the user.

**Blocked by:** 02 — Implicit Takeover Pause, end to end. (Independent of 03.)

**Status:** ready-for-agent

- [ ] `voltar <número>` from the admin number clears the pause; the next user message in that chat gets a normal bot reply
- [ ] The admin receives a confirmation reply; the user receives nothing at resume time
- [ ] `voltar` targeting a non-paused conversation replies to the admin with a not-paused notice
- [ ] Number matching tolerates formatting differences (punctuation, country-code spacing) against the stored conversation key
- [ ] Command messages never reach the Scope Gate or answerer (fake gate/answerer record no calls)
- [ ] Non-command admin messages flow through the normal pipeline
- [ ] Verified through the webhook seam: admin-number payloads in, fake-sender outbox out
