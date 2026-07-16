# 07 — Apostila delivery

**What to build:** When a user asks for the apostila (gate category: apostila request), Bella sends the configured PDF as a native WhatsApp document via Evolution GO send-media, with a short friendly accompanying text. The PDF is a swappable asset referenced by configuration: while the file is absent (it is still being written and will land days from now), Bella instead replies that the apostila is being finalized and will be available soon, and offers to answer questions about its content meanwhile. Dropping the finished PDF into place later requires no code change or redeploy logic beyond the file itself.

**Blocked by:** 04 — Scope Gate + Canned Refusals.

**Status:** ready-for-agent

- [x] "Quero a apostila" / "tem material?" triggers the apostila flow, not a generic answer
- [x] With the PDF configured: user receives it as a document (not a link), with accompanying text
- [x] Without the PDF: user gets the "em breve" reply and an offer to answer content questions
- [x] Swapping/adding the PDF file changes behavior with no code modification
- [x] Send-media failures degrade to an apologetic text reply, and the failure is logged

## Comments

- 2026-07-16: Implemented native document delivery against Evolution Go 0.7.1's `/send/media` JSON contract. The configured file is read and base64-encoded on each request; `./content` is mounted read-only so adding or replacing `apostila.pdf` is visible without rebuilding the image. Missing files and send failures have editable canned fallbacks. Covered through the webhook seam plus a wire-contract test.
