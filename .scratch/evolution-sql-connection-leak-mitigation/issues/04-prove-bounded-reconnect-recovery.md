# 04 — Prove bounded reconnect and recovery behavior

**What to build:** End-to-end evidence that the patched runtime and PostgreSQL guardrails stop the production failure mode. A licensed disposable or staging WhatsApp instance must survive repeated reconnects and database recovery while Evolution's sessions plateau, Bella keeps database access, and persisted instance state remains intact.

**Blocked by:** 01 — Build the patched Evolution GO 0.7.2 runtime; 02 — Contain Evolution's PostgreSQL connection budget; 03 — Expose the Evolution connection-budget check.

**Status:** ready-for-agent

- [ ] The test environment verifies the patched image provenance, the non-superuser Evolution role, the 30-session role limit, and the five-minute role timeout before exercising reconnects
- [ ] A licensed disposable or staging instance completes at least 30 start/reconnect cycles through Evolution's public behavior
- [ ] Connection samples taken before, during, and after the exercise plateau instead of increasing with reconnect count
- [ ] `evogo_auth` never exceeds the patched pool's 20-open-connection ceiling and total Evolution sessions remain below the 24-session warning threshold
- [ ] No `too many clients` error, connection refusal, or two-second database retry storm occurs
- [ ] After the exercise becomes quiet, no more than five idle `evogo_auth` sessions remain
- [ ] PostgreSQL can be unavailable during the first authentication-store initialization, return, and then allow Evolution to recover through a new public connect attempt without restarting Evolution
- [ ] After waiting beyond the server-side idle timeout, the next Evolution API operation and WhatsApp message succeed without a user-visible transient failure
- [ ] Bella's own PostgreSQL query succeeds while disposable Evolution sessions are driven to the 24-session warning boundary
- [ ] An Evolution-only restart and a normal Compose redeploy preserve the paired instance, license state, webhook, authentication data, and messaging behavior
- [ ] A real WhatsApp DM receives Bella's reply before and after the reconnect/restart exercise
- [ ] Connection samples, relevant logs, image identity, and message results are retained as reviewable acceptance evidence
- [ ] Any pairing loss, API/webhook regression, timeout error, rising connection trend, or retry storm blocks production promotion
