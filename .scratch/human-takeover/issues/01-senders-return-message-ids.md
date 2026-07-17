# 01 — Prefactor: senders return provider message IDs

**What to build:** A pure prefactor with zero behavior change. The WhatsApp
sender contract's send operations (text and document) return the provider
message ID of the message they sent, instead of returning nothing. The
Evolution sender extracts the ID from the send-endpoint response; the test
fake returns deterministic IDs. Call sites keep working unchanged — nothing
consumes the ID yet. This makes ticket 02's echo ledger a small change
instead of a tangled one ("make the change easy, then make the easy change").

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] Send operations on the sender contract return the provider message ID
- [ ] The Evolution sender reads the ID from the actual send response shape (verify against the running instance's documented/observed payload; the normalization point for wire shapes is the single place adjusted)
- [ ] The fake sender returns deterministic, unique IDs so later tests can replay echoes
- [ ] No behavior change: every existing test passes without modification beyond the fake's signature
