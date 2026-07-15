# 06 — Conversation memory in Postgres

**What to build:** Bella remembers the conversation. Create Bella's own database inside the Evolution stack's Postgres 15 instance (never touching the Evolution databases). Store conversations keyed by phone number with role/text/timestamp messages; load the last 50 messages as context for the answering call so follow-ups ("e quanto custa?", "me manda o link de novo") work naturally across messages and days. Move webhook dedupe records into Postgres so restarts don't cause double replies. Add the retention job: conversations idle for more than 120 days are deleted (LGPD posture — this is the only copy, since Evolution GO runs with message saving disabled). Include a small integration test suite against a real Postgres in addition to the in-memory store fake.

**Blocked by:** 05 — Opus answering from the Knowledge Base.

**Status:** ready-for-agent

- [x] A follow-up question referring to earlier context is answered correctly after a service restart
- [x] History context is capped at 50 messages regardless of conversation length
- [x] Duplicate webhook deliveries produce one reply even across restarts
- [x] Retention job deletes conversations idle >120 days and logs what it removed
- [x] Evolution's own databases are untouched; Bella uses her own database in the shared instance

## Comments

- 2026-07-15: Product decision supersedes the original values: keep the last 50 messages in answering context and retain idle conversations for 120 days.
- 2026-07-15: Implemented with an in-memory contract fake and a real-Postgres integration suite. Local verification: 38 passed, 2 Postgres tests skipped because this machine has no Docker/Postgres; set `BELLA_TEST_DATABASE_URL` to run them.
