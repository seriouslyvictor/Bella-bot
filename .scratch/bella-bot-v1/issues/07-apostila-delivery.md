# 07 — Apostila delivery

**What to build:** When a user asks for the apostila (gate category: apostila request), Bella sends the configured PDF as a native WhatsApp document via Evolution GO send-media, with a short friendly accompanying text. The PDF is a swappable asset referenced by configuration: while the file is absent (it is still being written and will land days from now), Bella instead replies that the apostila is being finalized and will be available soon, and offers to answer questions about its content meanwhile. Dropping the finished PDF into place later requires no code change or redeploy logic beyond the file itself.

**Blocked by:** 04 — Scope Gate + Canned Refusals.

**Status:** ready-for-agent

- [ ] "Quero a apostila" / "tem material?" triggers the apostila flow, not a generic answer
- [ ] With the PDF configured: user receives it as a document (not a link), with accompanying text
- [ ] Without the PDF: user gets the "em breve" reply and an offer to answer content questions
- [ ] Swapping/adding the PDF file changes behavior with no code modification
- [ ] Send-media failures degrade to an apologetic text reply, and the failure is logged
