# Raw course documents never enter the LLM context

The Source Documents (Plano Mestre, Apostila) are internal operational files containing cost targets, contingency plans, infrastructure details, and instructor prep notes. Bella answers only from a curated, public-facing Knowledge Base distilled from them — the raw documents are never placed in any model's context, because no prompt instruction reliably prevents leakage of text that is present in context. The trade-off is a manual curation step whenever the source documents change.

## Considered Options

- Feed raw docs with "don't reveal internals" prompt guardrails — rejected: leakage of in-context text is not reliably preventable.
- Redacted copies of the raw docs — rejected: less polish for marginal savings over full curation.
