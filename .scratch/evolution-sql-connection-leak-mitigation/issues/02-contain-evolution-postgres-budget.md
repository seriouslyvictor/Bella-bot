# 02 — Contain Evolution's PostgreSQL connection budget

**What to build:** A PostgreSQL safety boundary that prevents Evolution GO from exhausting the shared cluster even if its application-side pool regresses. Fresh and retained stacks must give the existing non-superuser `evolution` role a measured connection budget and role-only idle-session reclamation while leaving Bella's role and cluster-wide capacity unchanged.

**Blocked by:** None — can start immediately.

Status: ready-for-human

- [x] The stack exposes validated Evolution database guardrails with defaults of 30 concurrent connections and a five-minute idle-session timeout
- [x] The dedicated `evolution` login role remains non-superuser and receives `CONNECTION LIMIT 30`
- [x] The five-minute `idle_session_timeout` applies only to the `evolution` role and does not change Bella, the PostgreSQL administrator, or cluster-wide defaults
- [x] The global `max_connections` and `idle_in_transaction_session_timeout` remain unchanged
- [ ] Database reconciliation applies the role password, grants, connection limit, and timeout idempotently on a fresh volume
- [ ] Rerunning reconciliation on a retained volume applies the guardrails without recreating databases, changing owners, losing Evolution state, or altering Bella's grants
- [ ] New Evolution sessions inherit the timeout after the required Evolution-only restart
- [ ] A disposable-cluster test can fill the Evolution role's budget and proves that the next Evolution connection is rejected while Bella and administrator queries still succeed
- [x] Invalid connection-limit or timeout configuration fails safely before unsafe SQL is executed
- [x] The deployment contract tests require the guardrail configuration and continue to prove database-role isolation
- [x] Operator guidance explains how to stop Evolution, reconcile a retained volume, restart Evolution, and verify the applied role attributes
- [x] `DATABASE_SAVE_MESSAGES=false` remains unchanged and is documented as unrelated to the authentication-store leak

## Comments

2026-07-16 — Compose passes the two guardrail values to the idempotent
initializer; the initializer validates them before `psql`, explicitly keeps
`evolution` non-superuser, applies `CONNECTION LIMIT` and a role-only timeout,
and does not alter cluster-wide timeout/capacity settings. The focused 57-test
suite passed, and `docs/deploy.md` now records retained-volume maintenance and
verification. Real fresh/retained-volume reconciliation, timeout inheritance,
state/ACL preservation, and budget-exhaustion isolation still require an
operator-run disposable PostgreSQL exercise.

2026-07-16 review follow-up — Added the executable, fail-closed
`bella.scripts.evolution_connection_limit_proof` path. Unit tests prove its
30-session hold, SQLSTATE `53300` requirement for the 31st connection,
Bella/admin queries, and unconditional cleanup. The environmental checkbox
remains open until an operator runs it on a disposable real PostgreSQL stack.
