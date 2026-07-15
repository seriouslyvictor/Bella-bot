# 05 — Opus answering from the Knowledge Base

**What to build:** In-scope questions get real answers. The answering call uses `claude-opus-4-8` with a system prompt assembling Bella's persona (course concierge, self-referential "fui construída com as mesmas técnicas que você vai aprender", warm and amicable), scope rules as defense in depth, the Knowledge Base, and the Enrollment Card — with the stable prefix marked for prompt caching and volatile content (history, user message) after it. Volatile enrollment facts come only from the Enrollment Card; anything absent gets an honest deflection plus the enrollment link. Replies mirror the user's language (noting the course is taught in Portuguese when replying in another language). An output guard ensures the only URL Bella ever sends is the configured SENAI enrollment URL.

**Blocked by:** 01 — Content assets; 04 — Scope Gate + Canned Refusals.

**Status:** ready-for-agent

- [ ] Course questions are answered accurately from the Knowledge Base in natural pt-BR
- [ ] Enrollment questions answered from the Enrollment Card (dates, unit, bolsa, in-person confirmation rules) with the link included when relevant
- [ ] A question whose answer isn't in the KB/Card gets an honest "não sei" + link, not an invention
- [ ] Messages in English/Spanish get replies in that language with the Portuguese-course note
- [ ] Any non-SENAI URL in a model answer is stripped or the reply regenerated — verified via a scripted fake answer containing a foreign link
- [ ] Repeated requests hit the prompt cache (verified once against the real API via usage fields)
