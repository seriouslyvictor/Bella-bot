# 03 — Expose the Evolution connection-budget check

**What to build:** One safe operator check that turns PostgreSQL session state into an actionable Evolution GO connection-budget signal. It must show whether connections are stable or approaching the one-instance safety limit and give operators a precise Evolution-only response before Bella's database access is threatened.

**Blocked by:** 02 — Contain Evolution's PostgreSQL connection budget.

Status: ready-for-human

- [x] One operator command reports Evolution sessions grouped by database and state, with useful client/application identity when PostgreSQL exposes it
- [x] The output includes the total Evolution session count, the configured role limit, and the 24-session warning threshold
- [x] The check exposes a machine-readable success/failure result: below 24 is within budget and 24 or more is a warning requiring intervention
- [x] A repeated-sampling mode or documented comparison makes monotonic growth across reconnect attempts visible even when the total is below 24
- [ ] The check works against the local unified stack and through the equivalent Coolify terminal workflow without printing database passwords or other secrets
- [x] Tests cover a healthy low count, the exact warning threshold, a count above the threshold, and unavailable PostgreSQL
- [x] The incident response captures the connection snapshot and Evolution logs, stops further reconnect attempts, and restarts only Evolution GO
- [x] The incident response explicitly forbids restarting PostgreSQL or raising global `max_connections` as the leak response
- [x] Operational guidance distinguishes Evolution's process-only `/server/ok` signal from the database connection-budget signal
- [x] No implementation mounts the Docker socket or grants an in-stack watchdog host-control privileges

## Comments

2026-07-16 — `bella.scripts.evolution_connection_budget` implements grouped
session output, total/limit/threshold reporting, JSON and exit-status contracts,
repeated sampling, and below-threshold monotonic-growth detection without
printing the DSN. Unit coverage for low, exact-threshold, above-threshold,
unavailable-PostgreSQL, trend, JSON, and prompted-password cases passed in the
57-test focused suite. The dedicated runbook contains the Evolution-only
response and guardrails. A human must still execute the command against the
real local Compose stack and equivalent Coolify terminal/database path.

2026-07-16 review follow-up — The command now reports the actual PostgreSQL
`pg_roles.rolconnlimit` and the separately configured/defaulted expected limit,
and exits `3` on drift. Environment-absent default behavior and drift are unit
covered; real local and Coolify execution remains correctly unchecked.
