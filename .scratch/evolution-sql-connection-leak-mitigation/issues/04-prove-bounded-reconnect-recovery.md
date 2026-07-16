# 04 — Prove bounded reconnect and recovery behavior

**What to build:** End-to-end evidence that the patched runtime and PostgreSQL guardrails stop the production failure mode. A licensed disposable or staging WhatsApp instance must survive repeated reconnects and database recovery while Evolution's sessions plateau, Bella keeps database access, and persisted instance state remains intact.

**Blocked by:** 01 — Build the patched Evolution GO 0.7.2 runtime; 02 — Contain Evolution's PostgreSQL connection budget; 03 — Expose the Evolution connection-budget check.

Status: ready-for-human

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
- [x] Any pairing loss, API/webhook regression, timeout error, rising connection trend, or retry storm blocks production promotion

## Comments

2026-07-16 — The fail-closed evidence harness and dedicated reconnect runbook
encode provenance/role preflight, at least 30 public reconnects, plateau and
pool ceilings, recovery, state/message checks, artifact hashes, and promotion
blockers. Synthetic positive and negative manifest tests passed as part of the
57-test focused suite; they intentionally are not acceptance evidence. Every
environmental checkbox remains open until an authorized operator runs the
licensed disposable/staging WhatsApp and real-PostgreSQL exercise and retains
the required artifacts.

2026-07-16 review follow-up — Plateau validation now rejects every adjacent
post-plateau increase, including `9, 7, 8`. The production gate now hashes and
parses an actual ticket-04 assessment file and binds its assessed image digest
to the rollout. These are synthetic decision-engine checks only; all licensed
environmental acceptance boxes remain open.

2026-07-16 final re-review — Shared connection-sample parsing now rejects
negative total, authentication-total, and idle counts. The public CLI accepts
PowerShell 5.1 UTF-8 BOM manifests. These unit-backed changes do not replace
the licensed reconnect exercise.
