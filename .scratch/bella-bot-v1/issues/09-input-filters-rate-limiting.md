# 09 — Input filters + rate limiting

**What to build:** The remaining input policy from the spec. Group-chat messages are silently ignored — Bella never replies in a group, even when mentioned. Non-text DMs (voice notes, images, stickers, documents) get the friendly "text only for now" canned reply. A per-number rate limit (sliding window) protects API costs: users exceeding it get a polite canned "muitas mensagens" reply once, then silence until the window clears — and rate-limited traffic never reaches the LLM calls.

**Blocked by:** 02 — Walking skeleton: echo bot.

**Status:** ready-for-agent

- [ ] Messages with group JIDs produce no reply of any kind
- [ ] A voice note or image in a DM gets the "text only" canned reply, with no LLM call
- [ ] A burst beyond the rate limit gets one polite cap message, then silence until the window resets
- [ ] Rate-limited and filtered messages never invoke the gate or answering models — verified via the fake LLM
- [ ] Limits and canned texts are configurable without code changes
