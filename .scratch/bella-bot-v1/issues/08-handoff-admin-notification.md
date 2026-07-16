# 08 — Handoff + admin notification

**What to build:** The human escape hatch. When a user asks for a person (gate category: human-requested) or Bella cannot answer an in-scope question from her material, she replies with the SENAI/owner contact from the Enrollment Card — and sends a Handoff Notification to the course owner's WhatsApp (the admin contact number from the environment) through the same Evolution GO API. The notification carries the user's number and a brief summary of what they wanted, so the owner can follow up personally. Notifications must not loop: messages from the admin contact number never trigger notifications about themselves.

**Blocked by:** 05 — Opus answering from the Knowledge Base.

**Status:** ready-for-agent

- [x] "Quero falar com uma pessoa" gets the SENAI contact AND fires a Handoff Notification to the admin number
- [x] An in-scope question Bella deflects ("não sei") also fires a notification with the question summary
- [x] Notification includes the user's number and question context
- [x] Messages from the admin number don't generate notification loops
- [x] Notification send failures are logged but never block or degrade the user-facing reply

## Comments

- 2026-07-16: Implemented direct human-request routing and schema-backed `needs_handoff` output for grounded answers using Anthropic's current `output_config.format` API. Both paths give the user the Enrollment Card contact and notify `ADMIN_CONTACT`; admin self-notifications are suppressed and notification failures are isolated and logged.
