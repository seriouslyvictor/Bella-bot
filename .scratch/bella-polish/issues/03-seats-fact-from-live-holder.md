# 03 — Seats fact rendered from a live holder; retire the hand-edited field

**What to build:** Bella stops telling every prospective student that 19
openings remain. The hand-edited seats field leaves the editable Enrollment
Card file, and the Enrollment Card presented to the answering model is
rendered per answer with the seats fact injected from a shared live-count
holder. While the holder is empty or its value has exceeded the maximum
acceptable age, the seats fact is simply absent — and the existing
honest-deflection grounding rule takes over: Bella says she cannot confirm
the current count and gives the enrollment URL. Bella never falls back to a
stale or hand-written number.

This ticket is deliberately shippable before any scraping exists: with an
always-empty holder, Bella's seat answers become honest deflections instead
of a stale lie. It is also the prefactor that makes the refresher ticket
easy — the answerer currently freezes its context blocks at construction,
and this slice moves the Enrollment Card rendering to per-answer with the
live fact injected. Note the accepted trade-off from the spec: the
Enrollment Card block is prompt-cached, and a changed count invalidates
that cache entry; at multi-hour refresh cadence this is negligible.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [x] The editable Enrollment Card file no longer carries a hand-edited
      seats value.
- [x] With a fresh count in the holder, the rendered Enrollment Card block
      contains that count as the seats fact.
- [x] With an empty holder, or a value older than the maximum acceptable
      age, the seats fact is absent from the rendered block.
- [x] The maximum acceptable age is configurable through the environment.
- [x] Existing answerer and pipeline behavior is otherwise unchanged.
