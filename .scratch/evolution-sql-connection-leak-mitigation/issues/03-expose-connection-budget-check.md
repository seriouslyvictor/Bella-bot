# 03 — Expose the Evolution connection-budget check

**What to build:** One safe operator check that turns PostgreSQL session state into an actionable Evolution GO connection-budget signal. It must show whether connections are stable or approaching the one-instance safety limit and give operators a precise Evolution-only response before Bella's database access is threatened.

**Blocked by:** 02 — Contain Evolution's PostgreSQL connection budget.

**Status:** ready-for-agent

- [ ] One operator command reports Evolution sessions grouped by database and state, with useful client/application identity when PostgreSQL exposes it
- [ ] The output includes the total Evolution session count, the configured role limit, and the 24-session warning threshold
- [ ] The check exposes a machine-readable success/failure result: below 24 is within budget and 24 or more is a warning requiring intervention
- [ ] A repeated-sampling mode or documented comparison makes monotonic growth across reconnect attempts visible even when the total is below 24
- [ ] The check works against the local unified stack and through the equivalent Coolify terminal workflow without printing database passwords or other secrets
- [ ] Tests cover a healthy low count, the exact warning threshold, a count above the threshold, and unavailable PostgreSQL
- [ ] The incident response captures the connection snapshot and Evolution logs, stops further reconnect attempts, and restarts only Evolution GO
- [ ] The incident response explicitly forbids restarting PostgreSQL or raising global `max_connections` as the leak response
- [ ] Operational guidance distinguishes Evolution's process-only `/server/ok` signal from the database connection-budget signal
- [ ] No implementation mounts the Docker socket or grants an in-stack watchdog host-control privileges
