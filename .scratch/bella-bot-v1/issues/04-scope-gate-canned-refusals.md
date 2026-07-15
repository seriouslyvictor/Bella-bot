# 04 — Scope Gate + Canned Refusals

**What to build:** Every inbound text passes the Scope Gate before anything is generated (ADR-0002). A `claude-haiku-4-5` classifier call with structured output labels the message with a category: course question, apostila request, enrollment question, greeting/pleasantry, "who/what are you", human-requested, or out-of-scope. Out-of-scope messages get one of the Canned Refusal templates sent verbatim — the answering model is never invoked and no generation happens on the refusal path. In-scope categories flow onward (a placeholder answer is acceptable until ticket 05). The category vocabulary is the routing contract that tickets 05, 07, and 08 build on.

**Blocked by:** 02 — Walking skeleton: echo bot.

**Status:** ready-for-agent

- [ ] Off-topic messages (homework, recipes, general chat) receive a Canned Refusal verbatim
- [ ] Prompt-injection attempts ("ignore suas instruções…") that are out-of-scope never reach the answering path — verified via the fake LLM recording zero answer calls
- [ ] Greetings and course questions are classified in-scope and flow onward
- [ ] Refusal variants rotate so repeated offenders don't get the identical string every time
- [ ] Gate failures (LLM error/timeout) degrade safely: a polite retry message, never an unguarded answer
