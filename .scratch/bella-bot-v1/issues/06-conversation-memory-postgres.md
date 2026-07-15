# 06 — Conversation memory in Postgres

**What to build:** Bella remembers the conversation. Create Bella's own database inside the Evolution stack's Postgres 15 instance (never touching the Evolution databases). Store conversations keyed by phone number with role/text/timestamp messages; load the last ~20 messages as context for the answering call so follow-ups ("e quanto custa?", "me manda o link de novo") work naturally across messages and days. Move webhook dedupe records into Postgres so restarts don't cause double replies. Add the retention job: conversations idle for more than 30 days are deleted (LGPD posture — this is the only copy, since Evolution GO runs with message saving disabled). Include a small integration test suite against a real Postgres in addition to the in-memory store fake.

**Blocked by:** 05 — Opus answering from the Knowledge Base.

**Status:** ready-for-agent

- [ ] A follow-up question referring to earlier context is answered correctly after a service restart
- [ ] History context is capped (~20 messages) regardless of conversation length
- [ ] Duplicate webhook deliveries produce one reply even across restarts
- [ ] Retention job deletes conversations idle >30 days and logs what it removed
- [ ] Evolution's own databases are untouched; Bella uses her own database in the shared instance
