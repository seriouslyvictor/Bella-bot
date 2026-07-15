# Out-of-scope refusals are canned, never generated

Every inbound message passes a Scope Gate (a cheap classifier call on claude-haiku-4-5) before any answer is generated. Messages ruled out-of-scope receive a pre-written Canned Refusal sent verbatim — the refusal path contains no LLM generation, so prompt injection cannot alter what Bella says when declining. This matters doubly here because the bot is itself a guardrails showcase and course students are explicitly taught adversarial testing (Day 3, "ataque e defesa").

## Consequences

- Every message costs a second (small) model call and ~300ms of extra latency.
- Borderline messages can be misclassified; tuning happens in the classifier prompt, not the refusal texts.
- The answering model still carries scope rules as defense in depth, and outputs pass a link allowlist (SENAI URL only).
