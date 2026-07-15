# 08 — Handoff + admin notification

**What to build:** The human escape hatch. When a user asks for a person (gate category: human-requested) or Bella cannot answer an in-scope question from her material, she replies with the SENAI/owner contact from the Enrollment Card — and sends a Handoff Notification to the course owner's WhatsApp (the admin contact number from the environment) through the same Evolution GO API. The notification carries the user's number and a brief summary of what they wanted, so the owner can follow up personally. Notifications must not loop: messages from the admin contact number never trigger notifications about themselves.

**Blocked by:** 05 — Opus answering from the Knowledge Base.

**Status:** ready-for-agent

- [ ] "Quero falar com uma pessoa" gets the SENAI contact AND fires a Handoff Notification to the admin number
- [ ] An in-scope question Bella deflects ("não sei") also fires a notification with the question summary
- [ ] Notification includes the user's number and question context
- [ ] Messages from the admin number don't generate notification loops
- [ ] Notification send failures are logged but never block or degrade the user-facing reply
