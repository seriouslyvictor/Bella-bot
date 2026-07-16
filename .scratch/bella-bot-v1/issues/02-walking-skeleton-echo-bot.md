# 02 — Walking skeleton: echo bot

**What to build:** Sending Bella a WhatsApp DM gets a reply — the full inbound/outbound path working end to end with a placeholder brain. FastAPI service with a fixed internal webhook endpoint (constant-time validates the top-level Evolution GO 0.7.1 `instanceToken`, acks authenticated events 200 immediately, and processes asynchronously so slow work never triggers retries), an Evolution GO sender client (send-text against the instance API using the instance token from the environment), and loop protection: ignore `fromMe` events and deduplicate by message id (in-memory is fine at this stage). Establish the test harness that all later tickets use: drive the app in-process through the webhook seam with a fake sender, asserting only on externally observable behavior. Confirm Evolution GO 0.7.1's webhook payload shape and send-text endpoint against the pinned local container.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] A text DM to Bella's number produces a reply (hardcoded/echo) within a few seconds
- [ ] Webhook requests with a missing or incorrect top-level `instanceToken` are rejected
- [ ] Bella never replies to her own messages or to a redelivered duplicate webhook
- [ ] Webhook endpoint returns 200 before processing completes
- [ ] Test suite runs the app in-process with a fake sender and covers the above behaviors
