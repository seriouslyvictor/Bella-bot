# Evolution GO connection-budget check

Evolution GO has a dedicated PostgreSQL role with a 30-session limit. For the
single Evolution instance in this stack, 24 sessions (80% of that limit) is the
warning threshold. This check observes only the `evolution` role and excludes
its own observer connection.

The check reports each group by database, state, application name, and client
address or hostname, followed by the total, actual `pg_roles.rolconnlimit`,
configured expected limit, threshold, and trend. A mismatch fails closed with
exit `3`; reconcile the retained role before trusting the budget. It never
prints the connection string or password. The database
password can be supplied by `EVOLUTION_CONNECTION_BUDGET_DSN`,
`POSTGRES_AUTH_DB`, or `EVOLUTION_DB_PASSWORD`; the commands below use a secure
interactive prompt so the password does not enter shell history.

## Run the check

For a local unified stack started with `docker-compose.local.yml`, run from the
repository root in PowerShell. Replace the port if `POSTGRES_HOST_PORT` is not
`5432`:

```powershell
.\.venv\Scripts\python.exe -m bella.scripts.evolution_connection_budget --host 127.0.0.1 --port 5432 --prompt-password
$LASTEXITCODE
```

In Coolify, open a terminal for the deployed `bella` service and run:

```sh
python -m bella.scripts.evolution_connection_budget --prompt-password
echo $?
```

Enter `EVOLUTION_DB_PASSWORD` at the prompt. The default service DNS name is
`postgres`; no database port needs to be published in Coolify. If the password
is already injected into a short-lived operator environment, omit
`--prompt-password`. Do not put a password directly in a command-line argument.

The exit status is the automation contract:

- `0`: within budget and no monotonic growth was observed.
- `2`: warning; at least one sample is 24 or higher, or repeated samples grew
  monotonically.
- `3`: the check could not run because configuration or PostgreSQL was
  unavailable. At the role limit, the observer connection can itself be
  refused, so treat an unexpected `3` during reconnect trouble as an incident.

For JSON output, add `--json`. The document contains `status`, `total`, the
observed `limit`, `configured_limit`, `threshold`, `trend`, and grouped samples.
The process exit status remains authoritative.

## Check reconnect growth

Collect several samples while a controlled connect/reconnect exercise runs in
another terminal:

```powershell
.\.venv\Scripts\python.exe -m bella.scripts.evolution_connection_budget --host 127.0.0.1 --port 5432 --prompt-password --samples 6 --interval 10
```

For Coolify, use the same `--samples 6 --interval 10` options on the in-service
command. Each sample prints its total and delta. A healthy bounded pool reaches
a plateau. A total that grows on every successive sample is reported as
`MONOTONIC_GROWTH` and exits `2`, even below 24. Stop the exercise immediately
on either warning condition; do not keep reconnecting to see whether the role
limit eventually stops it.

The command always reads the actual `evolution` role limit from PostgreSQL.
`EVOLUTION_DB_CONNECTION_LIMIT` is only the expected deployment value and
defaults to `30` when it is absent, including local and Coolify terminal runs.
Any drift is an error, not a new implicit budget. The warning threshold is
intentionally fixed at `24` for the current single-instance topology. Adding an
Evolution instance or changing the role limit requires a new measured budget
and reconnect test; do not scale this threshold by guesswork.

The separate role-only idle-session circuit breaker is configured by
`EVOLUTION_DB_IDLE_SESSION_TIMEOUT` and defaults to `5min`. It can reclaim a
future leaked idle session, but it is not evidence that the pool is healthy and
does not replace this check. It must remain scoped to the `evolution` role.

## Incident response

At exit `2`, at 24 or more sessions, or when reconnect samples keep growing:

1. Stop all manual and automated Evolution connect/reconnect attempts.
2. Save the complete connection-budget output with a timestamp. Capture
   Evolution GO logs covering the growth window as well. Locally, use
   `docker compose logs --since 30m evolution-go`; in Coolify, use the
   Evolution service's log view/export.
3. Restart **only** the `evolution-go` service. Locally, run
   `docker compose restart evolution-go`; in Coolify, restart only the
   Evolution service.
4. Rerun the single-sample check, then verify the paired instance, webhook, and
   a real inbound/outbound WhatsApp message. If counts begin growing again,
   stop reconnect attempts and keep Evolution isolated while escalating with
   the captured evidence.

Do **not** restart PostgreSQL. That interrupts Bella and every other healthy
database client. Do **not** raise PostgreSQL's global `max_connections`; it
only delays exhaustion and increases the potential blast radius. The response
is Evolution-only because restarting Evolution releases its pools without
discarding the persisted pairing/authentication data in PostgreSQL.

The stack's `/server/ok` health check remains useful, but it proves only that
Evolution's HTTP process responds. It does not inspect `pg_stat_activity`, show
pool growth, prove database capacity, or trigger an automatic restart. A green
`/server/ok` response never overrides a connection-budget warning.

This is an operator observation tool, not an in-stack watchdog. It neither
mounts the Docker socket nor has permission to restart host services.
