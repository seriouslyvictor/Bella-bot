# 05 — Roll out with immutable rollback and exit criteria

**What to build:** A controlled production rollout of the proven patched runtime and database guardrails, with immutable evidence for both the deployed artifact and emergency rollback. The course owner must retain the paired WhatsApp instance and working Bella messages, and maintainers must have an explicit path back to an official image once upstream releases the fix.

**Blocked by:** 04 — Prove bounded reconnect and recovery behavior.

**Status:** ready-for-agent

- [ ] The maintenance window records the pre-change Evolution connection baseline, backup status, official 0.7.2 image digest, instance identity, license state, webhook, and pairing status
- [ ] Evolution is stopped before retained-volume reconciliation so existing leaked sessions are cleared and new sessions inherit the role policy
- [ ] Production is deployed from the proven patched source and patch revisions without using a floating image reference
- [ ] The produced patched image digest is recorded alongside the deployed repository revision and operator-visible version identity
- [ ] License, instance, pairing, webhook, Manager, and Evolution API behavior are verified after deployment
- [ ] A real WhatsApp DM receives Bella's reply after deployment, after an Evolution-only restart, and after a normal unified-stack redeploy
- [ ] The paired instance, Evolution authentication state, Bella conversation history, and database ownership/grants survive the rollout and redeploy checks
- [ ] Production connection-budget output remains below 24 and shows no upward reconnect trend during the observation window
- [ ] The emergency rollback target is the recorded immutable pre-change digest, never `latest`
- [ ] Rollback keeps the PostgreSQL connection limit and idle timeout, is identified as temporary because official 0.7.2 still leaks, and includes active monitoring plus planned Evolution-only restarts
- [ ] The rollback procedure is rehearsed in a disposable environment and the patched runtime is restored successfully afterward
- [ ] Operator documentation records promotion blockers, incident evidence to capture, and the rule to restart Evolution rather than PostgreSQL
- [ ] The custom build is retired only after an official release is verified to contain pull request #117 or an equivalent fix, passes ticket 04's tests, and is pinned by tag and manifest digest
- [ ] The final deployment and contract test suites pass, and no `latest` reference remains in runtime configuration or recovery guidance
