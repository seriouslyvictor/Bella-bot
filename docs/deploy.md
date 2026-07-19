# Unified Docker stack: local Docker Engine and Coolify

`docker-compose.yml` is the production deployment artifact. It runs Bella, the
Bella-owned Evolution GO `0.7.2-pr117` backport, and PostgreSQL 15 in one
Compose project with stable service DNS and no VPS-specific external network.

The production file publishes no host ports. `docker-compose.local.yml` only
adds loopback bindings for local development; it does not change the images,
volumes, dependencies, health checks, or internal URLs used on the VPS.

## Architecture

| Service | Runtime | Internal address | Persistent state |
|---|---|---|---|
| `bella` | Built from this repo with a digest-pinned Python base and `requirements.lock` | `http://bella:8000` | `bella` database in `postgres_data` |
| `evolution-go` | Built as `bella/evolution-go:0.7.2-pr117-0328955` from pinned Evolution GO 0.7.2 source plus the three reviewed PR #117 patches | `http://evolution-go:8080` | `evogo_auth` and `evogo_users` in `postgres_data` |
| `postgres` | Built as `bella/postgres:15-alpine-init1`: the digest-pinned `postgres:15-alpine` base with the database initializer baked in | `postgres:5432` | `postgres_data` |

The default bridge network is project-scoped and created by Compose. Postgres
has no production port binding. Coolify may route an HTTPS domain to
`evolution-go:8080` for the Manager, activation, and pairing; Bella remains
internal-only because Evolution posts its webhooks directly to
`http://bella:8000`.

The stack references no repository host paths at runtime: Coolify starts
containers from a build-container checkout the host daemon cannot see, so the
initializer ships inside the Postgres image and Bella's content ships inside
Bella's image rather than as a `configs:` file or bind mount.

On a new Postgres volume, `deploy/postgres/init-databases.sh` (baked into the
image at `/docker-entrypoint-initdb.d/10-init-databases.sh`) creates isolated
`bella` and `evolution` login roles and the three databases they own. Bella
cannot connect to Evolution's databases, and Evolution cannot connect to
Bella's. This replaces the old manual `provision_database` operator script.

The `evolution` role remains non-superuser and has two role-only circuit
breakers: `CONNECTION LIMIT 30` and `idle_session_timeout = 5min`. They do not
change Bella's role, the administrator role, the cluster-wide
`max_connections`, or `idle_in_transaction_session_timeout`. The application
pool fix remains primary; `DATABASE_SAVE_MESSAGES=false` does not bypass the
WhatsMeow authentication store and is not a connection-leak mitigation.

Image digests, checksummed Evolution source and patches, and
`requirements.lock` are deliberate deployment inputs. The Evolution build
pins both base images by digest, verifies the source archive checksum, and
fails if any reviewed patch no longer applies exactly. Record the produced
image content digest during acceptance; the local image tag is an explicit
build identity, not a substitute for artifact evidence. The current empty-cache
`linux/amd64` build record is in
[`deploy/evolution/BUILD-EVIDENCE.md`](../deploy/evolution/BUILD-EVIDENCE.md);
it records a local image ID, not an authenticated registry manifest digest. An
upgrade changes the human-readable identity and immutable inputs together,
regenerates the hash lock with Python 3.12 (`pip-compile --generate-hashes
--strip-extras --output-file=requirements.lock pyproject.toml`), and repeats the
applicable acceptance tests before Coolify deploys it.

## Evolution connection-leak controls

Use [the connection-budget check](evolution-connection-budget.md) for the safe
local and Coolify commands, repeated sampling, and incident response. For this
single-instance topology, 24 Evolution sessions is a warning. A count at or
above 24, or a count that rises on every reconnect sample, means stop reconnect
attempts, save the budget output and Evolution logs, and restart only
`evolution-go`. Do not restart PostgreSQL or raise its global connection limit.

Use [the reconnect and immutable rollout runbook](evolution-reconnect-rollout.md)
for licensed staging acceptance, evidence capture, maintenance order,
production promotion, digest-qualified rollback, and the eventual return to an
official release. A production rollout is not approved by Compose health alone.

## Required configuration

Copy `.env.example` to `.env` locally. In Coolify, create the same variables
in the resource's environment panel instead. `.env` is gitignored.

| Variable | Purpose |
|---|---|
| `POSTGRES_PASSWORD` | Password for the stack-local Postgres administrator. |
| `BELLA_DB_PASSWORD` | Password for the role restricted to the `bella` database. Use a URL-safe value because it is embedded in Bella's DSN. |
| `EVOLUTION_DB_PASSWORD` | Password for the role restricted to `evogo_auth` and `evogo_users`. Use a URL-safe value because it is embedded in Evolution's DSNs. |
| `EVOLUTION_DB_CONNECTION_LIMIT` | Evolution role connection budget. Defaults to `30`; changing it is a capacity decision requiring the reconnect test. |
| `EVOLUTION_DB_IDLE_SESSION_TIMEOUT` | Evolution role-only idle-session circuit breaker. Defaults to `5min`; changing it requires the timeout-recovery test. |
| `EVOLUTION_GLOBAL_API_KEY` | Evolution administrative/Manager key. Bella never receives it. |
| `EVOLUTION_API_KEY` | Token assigned to Bella's Evolution instance. Bella uses it on instance/send/user routes and validates it on inbound webhook payloads. It is not the global key. |
| `ANTHROPIC_API_KEY` | Claude credential for Bella's Scope Gate and answerer. |
| `ADMIN_CONTACT` | Owner WhatsApp number that receives handoff notifications. |

`EVOLUTION_INSTANCE_ID` can initially keep the documented placeholder. The
patched runtime identifies the instance from `EVOLUTION_API_KEY` and ignores
the `instanceId` header; replace it with the UUID later for operator clarity.

The Compose file owns `EVOLUTION_URL`, `BELLA_INTERNAL_URL`, and
`BELLA_DATABASE_URL`. Do not recreate those in Coolify: their service names
must remain identical locally and on the VPS.

Bella's editable assets (`content/`) are baked into its image. `APOSTILA_PATH`
defaults to `/app/content/apostila.pdf`; replacing the PDF or any YAML asset
means committing the new file and redeploying so Coolify rebuilds the image.
`RATE_LIMIT_MAX_MESSAGES` and `RATE_LIMIT_WINDOW_SECONDS` configure
the per-number sliding window, and the canned cap/media texts remain editable
in `content/canned_replies.yaml`. `SEAT_COUNT_REFRESH_SECONDS` controls how
often Bella refreshes the official SENAI-SP seat count (default: 21600,
six hours), while `SEAT_COUNT_MAX_AGE_SECONDS` controls when the last good
count is omitted as stale (default: 86400, 24 hours).

After deployment, verify the live SENAI-SP availability seam independently
from the scheduled job:

```text
docker compose exec bella python -m bella.scripts.check_seat_count
```

The command prints the current official seat count. A request or
page-structure failure exits unsuccessfully instead of producing a fallback
number.

The best-effort per-chat "available" presence call has not been verified
against a live instance yet; confirm its wire shape against the live
Evolution GO instance on the next redeploy.

When migrating the repository's previous `.env`, keep the existing
`EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE_ID`, `ANTHROPIC_API_KEY`, and display
name. Add the three database passwords and `EVOLUTION_GLOBAL_API_KEY`. Remove
the old URL/DSN variables, `POSTGRES_ADMIN_URL`, and `WEBHOOK_SECRET`; the new
stack derives URLs and authenticates webhooks with the instance token.

Generate each credential independently. These commands print a new value;
paste it only into `.env` or Coolify:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Use the hex form for the three database passwords so their DSNs never need
URL escaping. Use the URL-safe form for new Evolution keys/tokens.

### Rotate database passwords on a retained volume

The official Postgres initializer runs only for an empty data directory.
Changing a `*_DB_PASSWORD` or `POSTGRES_PASSWORD` environment value does not
change the matching role inside an existing cluster. Rotate the database role
first, then change the environment value during the same maintenance window:

```text
docker compose exec postgres psql -U postgres -d postgres
\password postgres
\password bella
\password evolution
\q
```

Each `\password` command prompts without putting the new value in shell or SQL
history. Update only the corresponding Coolify/`.env` values you rotated, then
immediately redeploy (or run `docker compose up -d --force-recreate`). Bella
and Evolution may fail new database connections between the role change and
the redeploy, so announce a short maintenance window. If values were changed
in the environment first and the redeployed stack is already unhealthy, run:

```text
docker compose exec -T postgres sh /docker-entrypoint-initdb.d/10-init-databases.sh
```

The idempotent script uses the new container environment and local socket
authentication to reconcile all three roles, after which the health check can
recover.

### Reconcile Evolution role guardrails on a retained volume

The official Postgres entrypoint does not rerun initialization scripts on a
retained volume. During a maintenance window, stop Evolution before applying
the role policy so old leaked sessions are closed and all new sessions inherit
the timeout:

```text
docker compose stop evolution-go
docker compose exec -T postgres sh /docker-entrypoint-initdb.d/10-init-databases.sh
docker compose exec -T postgres psql -U postgres -d postgres -Atc "SELECT r.rolname, r.rolsuper, r.rolconnlimit, COALESCE(s.setconfig::text, '{}') FROM pg_roles r LEFT JOIN pg_db_role_setting s ON s.setrole = r.oid AND s.setdatabase = 0 WHERE r.rolname = 'evolution'"
docker compose up -d --no-deps evolution-go
```

Expect a non-superuser role, limit `30`, and
`idle_session_timeout=5min`. Then run the connection-budget check and the
state/message checks in the dedicated rollout runbook. Never reconcile a
retained production volume while Evolution is still opening connections.

## Run the VPS topology locally

From the repository root in PowerShell:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
# Fill every required blank, or migrate an existing .env as described above.

docker compose -f docker-compose.yml -f docker-compose.local.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build --wait
docker compose -f docker-compose.yml -f docker-compose.local.yml ps
```

The overlay binds only to loopback:

- Evolution Manager/API: `http://127.0.0.1:8080`
- Bella liveness/readiness: `http://127.0.0.1:8000/health` and `/ready`
- Postgres for integration tests: `127.0.0.1:5432`

Change the three `*_HOST_PORT` variables if a local port is already occupied.
Internal service addresses never change.

Verify both HTTP services and the database split:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/server/ok
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/ready
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T postgres psql -U postgres -d postgres -Atc "SELECT datname FROM pg_database WHERE datname IN ('bella','evogo_auth','evogo_users') ORDER BY datname"
```

`/server/ok` only proves that the Evolution process is healthy. The patched
runtime can return 503 from business endpoints until its online license has
been activated, and health does not prove that a WhatsApp instance is paired
or that PostgreSQL connections are within budget.

Bella's Postgres integration tests delete their own test records. Create a
disposable database; never point `BELLA_TEST_DATABASE_URL` at production:

```powershell
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T postgres dropdb -U postgres --if-exists bella_test
docker compose -f docker-compose.yml -f docker-compose.local.yml exec -T postgres createdb -U postgres -O bella bella_test
$env:BELLA_TEST_DATABASE_URL = "postgresql://bella:PASTE_BELLA_DB_PASSWORD_HERE@127.0.0.1:5432/bella_test"
pytest
Remove-Item Env:BELLA_TEST_DATABASE_URL
```

Stop the stack without deleting state:

```powershell
docker compose -f docker-compose.yml -f docker-compose.local.yml down
```

Do not add `--volumes` unless permanent WhatsApp, Evolution, and Bella data is
intentionally being discarded.

## First-time Evolution setup

For a clean stack:

1. Open `/manager/login` on the local URL or the HTTPS domain routed by
   Coolify.
2. Log in with `EVOLUTION_GLOBAL_API_KEY` and complete Evolution GO's
   license activation flow.
3. Create the Bella instance. Assign it exactly the token stored in
   `EVOLUTION_API_KEY`, then pair the WhatsApp number.
4. If desired, copy the returned UUID into `EVOLUTION_INSTANCE_ID` and
   redeploy. The token, not this UUID header, selects the instance in this
   runtime.
5. From a terminal in the running `bella` container, register the internal
   webhook and set the WhatsApp presentation:

   ```bash
   python -m bella.scripts.register_webhook
   python -m bella.scripts.set_presentation
   ```

`register_webhook` is safe to rerun after ordinary redeploys. It registers the
fixed internal URL `http://bella:8000/webhook`; `set_presentation` makes
Evolution fetch the profile image from Bella over the same Compose network.

The patched Evolution runtime has no webhook signature or custom-header
setting and logs the complete webhook URL on delivery. A secret URL segment
would therefore leak into its logs. Instead, Bella constant-time validates the
top-level `instanceToken` included in every event against
`EVOLUTION_API_KEY`. The fixed webhook path contains no credential and is not
published by this stack.

## Deploy from GitHub in Coolify

1. Create one Docker Compose resource from this repository and branch.
2. Select `docker-compose.yml` as the Compose file. Do not include
   `docker-compose.local.yml`; its only purpose is local loopback access.
3. Add the required and optional values from `.env.example` in Coolify.
4. Route an HTTPS domain to port 8080 of `evolution-go` if the Manager must be
   browser-accessible. Do not add a domain or public port for `postgres` or
   `bella`.
5. Deploy and wait for all three Compose health checks. Then complete the
   activation/pairing steps above and run the two Bella scripts from its
   Coolify terminal.
6. Send a real WhatsApp DM, confirm a reply, redeploy once, and repeat the DM
   to prove the volumes and service DNS survive a normal release.

For the leak-mitigation rollout, those smoke checks are only part of the gate.
Run the licensed reconnect acceptance first, promote the exact resulting image
digest, and follow the maintenance and rollback sequence in
[the dedicated runbook](evolution-reconnect-rollout.md).

No network ID, container name, or manual `docker network connect` command is
part of this design. Coolify may attach its own proxy network in addition to
the project network; communication within the stack continues to use
`bella`, `evolution-go`, and `postgres`.

## Existing VPS data: choose before cutover

The new Compose project creates a new `postgres_data` named volume. It does
not automatically adopt the current Evolution/Postgres resource's volume.

- **Clean cutover (recommended for the first deployment):** deploy an empty
  stack, activate the Evolution license, create the instance with the retained
  token, and pair the number again.
- **State-preserving cutover:** restore logical dumps into a freshly initialized
  new cluster using the procedure below. With `POSTGRES_AUTH_DB` configured,
  the patched Evolution runtime stores the paired WhatsApp session in Postgres
  rather than `/app/dbdata`.

Never copy an old Postgres data directory directly into the new named volume.
The initialization script runs only for an empty cluster, and a raw directory
copy can skip the new roles/ownership or be inconsistent with a running server.

### State-preserving cutover runbook

Run this once against disposable local copies first. Replace the old stack's
service/container names where they differ.

1. Record the old Evolution version, license status, global key, instance UUID,
   instance token, paired number, and webhook. Schedule a maintenance window.
2. Quiesce all writers on the old stack: stop Bella, disconnect inbound traffic,
   and stop Evolution while leaving its Postgres running. Create custom-format,
   owner-free dumps of `evogo_auth`, `evogo_users`, and `bella` when present:

   ```bash
   mkdir -p backups
   docker compose exec -T postgres pg_dump -U postgres -Fc --no-owner --no-acl -f /tmp/evogo_auth.dump evogo_auth
   docker compose exec -T postgres pg_dump -U postgres -Fc --no-owner --no-acl -f /tmp/evogo_users.dump evogo_users
   docker compose exec -T postgres pg_dump -U postgres -Fc --no-owner --no-acl -f /tmp/bella.dump bella
   docker compose cp postgres:/tmp/evogo_auth.dump backups/evogo_auth.dump
   docker compose cp postgres:/tmp/evogo_users.dump backups/evogo_users.dump
   docker compose cp postgres:/tmp/bella.dump backups/bella.dump
   sha256sum backups/*.dump
   ```

   Omit the `bella` dump/copy/restore commands if that database did not exist
   in the old stack.

3. Create the new Coolify Compose resource with **no domain assigned yet** and
   all new database passwords set. Deploy once so the empty volume initializer
   creates the roles/databases, then stop `bella` and `evolution-go` from the
   resource controls while keeping `postgres` running. With direct Compose
   access, the equivalent preparation is `docker compose up -d --wait postgres`.
4. Copy the verified dumps into the new Postgres container and restore them as
   their intended owners. `--clean --if-exists` removes the schemas briefly
   created during the first boot:

   ```bash
   docker compose cp backups/evogo_auth.dump postgres:/tmp/evogo_auth.dump
   docker compose cp backups/evogo_users.dump postgres:/tmp/evogo_users.dump
   docker compose cp backups/bella.dump postgres:/tmp/bella.dump
   docker compose exec -T postgres pg_restore -U postgres --exit-on-error --clean --if-exists --no-owner --no-acl --role=evolution -d evogo_auth /tmp/evogo_auth.dump
   docker compose exec -T postgres pg_restore -U postgres --exit-on-error --clean --if-exists --no-owner --no-acl --role=evolution -d evogo_users /tmp/evogo_users.dump
   docker compose exec -T postgres pg_restore -U postgres --exit-on-error --clean --if-exists --no-owner --no-acl --role=bella -d bella /tmp/bella.dump
   ```

5. Reapply the database `OWNER`, `CONNECT`, and `TEMPORARY` statements from
   `deploy/postgres/init-databases.sh`, then verify owners and access before
   starting either application:

   ```bash
   docker compose exec -T postgres sh /docker-entrypoint-initdb.d/10-init-databases.sh
   docker compose exec -T postgres psql -U postgres -d postgres -Atc "SELECT datname || ':' || pg_get_userbyid(datdba) FROM pg_database WHERE datname IN ('bella','evogo_auth','evogo_users') ORDER BY datname"
   docker compose exec -T postgres psql -U postgres -d postgres -Atc "SELECT has_database_privilege('bella','evogo_auth','CONNECT'), has_database_privilege('evolution','bella','CONNECT')"
   ```

   Expected owners are `bella:bella`, `evogo_auth:evolution`, and
   `evogo_users:evolution`; both privilege checks must be `f`.
6. Start Evolution first. Confirm `/server/ok`, license status, retained
   instance, and pairing before starting Bella. Register the fixed webhook,
   run the presentation script, then assign the Manager domain and send a real
   DM in both directions. With direct Compose access, use
   `docker compose up -d --wait evolution-go` followed by
   `docker compose up -d --wait bella` after those Evolution checks pass.
7. Roll back on any owner, license, pairing, or messaging failure: stop the new
   application containers, restore inbound traffic to the untouched old stack,
   and retain the new volume and dumps for diagnosis.

Do not remove the old Coolify resource or its volumes until the new stack has
passed the message test after a redeploy and a restore drill has succeeded.

## Operational checks

```bash
docker compose ps
docker compose exec -T evolution-go wget -qO- http://127.0.0.1:8080/server/ok
docker compose exec -T bella python -c "import socket; print(socket.gethostbyname('evolution-go')); print(socket.gethostbyname('postgres'))"
docker compose exec -T evolution-go wget -qO- http://bella:8000/ready
docker compose exec -T postgres pg_isready -U postgres -d bella
```

Bella exposes two different signals: `/health` is process liveness, while
`/ready` verifies a real Postgres query and Evolution's `/server/ok`. The
container health check uses `/ready`. Docker's `restart: unless-stopped`
restarts a process that exits; Docker and Coolify do **not** restart a process
merely because its health status becomes `unhealthy`. Enable Coolify alerts for
unhealthy services and investigate/restart them after fixing the dependency.

Neither HTTP signal measures Evolution's database usage. Run the
[connection-budget check](evolution-connection-budget.md) during deployment,
after reconnect activity, and whenever Evolution is unstable.

The upstream runtime can attempt one NATS connection even with an empty
`NATS_URL` and `NATS_GLOBAL_ENABLED=false`, logging `Failed to connect to NATS`.
This stack does not use NATS; that startup line (and possible
`NATS connection is nil` event warnings) does not make `/server/ok` fail. The
license-required banner is also expected until the first activation. Other
startup errors are not normal.

## Backups and restore drills

`postgres_data` contains Evolution's instance and WhatsApp authentication
state, its license runtime state, and Bella's only conversation history. Use
logical Postgres backups rather than copying a live Docker volume:

- dump all three application databases in custom format with `--no-owner`
  and `--no-acl` (the cutover commands above are the reference commands);
- send checksummed, encrypted copies to storage outside the VPS;
- keep a documented retention policy (a reasonable starting point is 7 daily,
  4 weekly, and 12 monthly sets) and monitor the backup job;
- before cutovers/upgrades, stop Bella and Evolution so the three dumps share a
  quiet point in time;
- at least monthly, restore the newest set into a disposable local stack,
  verify owners/ACLs, start all services, and confirm Evolution still sees the
  retained instance before deleting the drill volume.

A normal redeploy recreates containers without recreating `postgres_data`.
Deleting that volume is a data-loss operation, not a routine deployment step.
