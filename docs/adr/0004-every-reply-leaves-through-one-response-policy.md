# Every reply leaves through one Response Policy

Each branch of the pipeline — canned refusals, greetings, the grounded
answerer, the feedback dialogue, handoffs, media and rate-limit notices —
produces a `Response` and hands it to a single `ResponsePolicy`
(`bella/response.py`), applied in `Pipeline._reply_with_presence`. Nothing
reaches a user any other way. A `Response` declares who authored it: text the
bot itself owns (`CANNED`, `CONTROL`) is only formatted, while model-authored
text (`ANSWERER`, `FEEDBACK`) additionally passes the URL allowlist of
ADR-0002. The guard is therefore a property of the source, not of whichever
code path remembered to call it.

The policy guarantees four things about every outbound message:

1. **No foreign URL** in model-authored text (ADR-0002), with the allowlist
   configured per deployment (`ALLOWED_REPLY_URLS`) rather than derived from
   one content file.
2. **WhatsApp formatting.** Markdown headings, `**bold**` and `-` bullets are
   rewritten deterministically; a model cannot be reliably prompted out of
   emitting them, and WhatsApp renders them as literal punctuation.
3. **Never empty.** A branch that produces blank text degrades to the canned
   error reply in the user's language. The always-reply invariant is not
   satisfied by sending an empty message.
4. **Readable length.** An over-long reply is split on the widest boundary
   that fits — paragraph, line, sentence, then a hard cut — up to a chunk
   budget, beyond which it is visibly truncated.

## Consequences

- A new reply branch gets the whole contract by construction; the only thing
  it must decide is its `ResponseSource`.
- Conversation history stores the finalized text, so replayed context is what
  the user actually saw, not what a branch intended to send.
- Formatting is deterministic and testable without a model call, which is why
  the rules live here rather than in a system prompt.
- Reply production runs under a deadline, so a provider that never answers
  degrades to the canned error reply instead of silence.
- Canned replies are trusted: an operator who puts a link in a canned reply or
  in `HUMAN_CONTACT_REPLY` gets to keep it.
