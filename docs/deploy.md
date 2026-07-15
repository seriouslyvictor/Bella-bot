# Deploying Bella to the VPS (Ticket 03)

This is the owner's runbook — an agent prepared everything below but has no
VPS or Coolify access and cannot run any of it. Follow the steps in order.

## Architecture decision: separate Coolify app + shared network

The spec allows two ways to get Bella onto the Evolution GO stack's Docker
network: deploy her as an extra service inside that stack's own
docker-compose, or deploy her as an independent resource attached via a
shared Docker network.

**This runbook uses the shared-network approach.** Reasons:

- Editing the live Evolution stack's compose file to add a service risks
  disrupting the already-connected WhatsApp number, and there's no way to
  dry-run or roll that back without VPS access to inspect the stack first.
- Bella's release cadence (a bot under active development, tickets 04–09
  still to come) is decoupled from Evolution GO's — she can redeploy, crash,
  or roll back without touching the messaging infra.
- Coolify supports attaching a resource to an existing Docker network
  independently of how that resource was deployed.

The cost: one extra piece of Coolify config (the network attachment below)
that has to be set correctly and re-verified after major Coolify upgrades.

## Step 0: what you're setting up

- A new Coolify application, built from this repo's `Dockerfile`, with no
  public domain and no published ports (spec: Bella is internal-only).
- That application joins the same Docker network the Evolution GO stack
  (and its Postgres) already runs on, so she can reach both by service name.
- Two scripts, run once from inside the deployed container, that register
  Bella's webhook with Evolution GO and set her WhatsApp profile picture and
  display name.

## Step 1: find the Evolution network name

SSH into the VPS and identify the Docker network the Evolution GO stack's
containers are on:

```bash
docker ps --format '{{.Names}}'          # find the evolution-go / postgres container names
docker inspect <evolution-go-container> --format '{{json .NetworkSettings.Networks}}'
```

The key(s) in that JSON output are the network name(s). If there's more than
one, pick the one Postgres is also on (`docker inspect <postgres-container>`
should show the same name). Write it down — every `REPLACE_WITH_EVOLUTION_STACK_NETWORK_NAME`
placeholder in this repo (`docker-compose.yml`) means this value.

## Step 2: create the Coolify application

1. New Resource → Application → deploy from this Git repo, the branch you
   want live.
2. Build pack: **Dockerfile** (the repo's `Dockerfile` at root).
3. **No domain.** Do not set an FQDN and do not expose a port — leave
   Coolify's port mapping empty. Bella is only ever reached by other
   containers on the internal network, never from outside the VPS (spec:
   "Bella is internal-only — no public domain").

## Step 3: attach the shared network

Coolify normally puts each application on its own isolated network. You
need Bella on the Evolution network you found in Step 1, too.

- If your Coolify version has a **"Connect to Predefined Network"** field
  under the application's Advanced/General settings, put the network name
  from Step 1 there.
- If you don't see that option (Coolify's UI has moved this around across
  versions), the durable fallback is `docker network connect
  <network-from-step-1> <bella-container-name>` after each deploy — check
  whether Coolify exposes a post-deployment hook to automate this, since a
  manual `docker network connect` does not survive a redeploy (Coolify
  recreates the container).

Verify it worked after deploying (Step 5):

```bash
docker exec <bella-container> python -c "import socket; print(socket.gethostbyname('evolution-go')); print(socket.gethostbyname('postgres'))"
```

Both must resolve. If either fails, the network attachment didn't take —
recheck the network name and the attachment step before moving on.

## Step 4: environment variables

Set these in Coolify's environment variables panel for the Bella
application (mark them "secret"/masked if your Coolify version offers that).
Never put real values in this repo.

| Variable | Value comes from | Notes |
|---|---|---|
| `EVOLUTION_API_KEY` | Owner's existing local `.env` | The Evolution GO instance token — same value already used for the walking skeleton |
| `EVOLUTION_INSTANCE_ID` | Owner's existing local `.env` | — |
| `WEBHOOK_SECRET` | Generate fresh: `python -c "import secrets; print(secrets.token_urlsafe(32))"` | Lives in the webhook URL path (`/webhook/<secret>`), not a header — see `bella/app.py` |
| `EVOLUTION_URL` | Usually leave unset | Defaults to `http://evolution-go:8080`; only set it if the Evolution stack's service is named differently — check with `docker inspect` from Step 1 |
| `BELLA_INTERNAL_URL` | Depends on Coolify's container naming | Defaults to `http://bella:8000`. After first deploy, check what hostname Bella's container actually resolves to on the shared network (`docker inspect <bella-container> --format '{{json .NetworkSettings.Networks}}'` from another container on that network, or set a custom container name/network alias to `bella` in Coolify if it offers one, so the default just works) |
| `BELLA_DISPLAY_NAME` | Your choice | What `bella/scripts/set_presentation.py` sets as the WhatsApp display name, e.g. `Bella` |

`.env.example` at the repo root lists these same names as a copy-paste
template (no values).

## Step 5: health check and restart policy

In Coolify's application settings, set the HTTP health check to `GET
/health` on port 8000 (internal — no public port needed for Coolify to reach
it, it talks to the container directly). Set the restart policy to restart
on failure. The image also ships a container-level `HEALTHCHECK` (see
`Dockerfile`) as a second, redundant signal for `docker inspect`.

## Step 6: deploy

Trigger the deploy. Once it's up, re-run the Step 3 verification
(`docker exec ... socket.gethostbyname(...)`) and confirm `GET /health`
returns `{"status": "ok"}`.

## Step 7: register the webhook

From Coolify's terminal/exec-into-container feature (or `docker exec -it
<bella-container> sh`), run:

```bash
python -m bella.scripts.register_webhook
```

This calls Evolution GO's `POST /instance/connect` with `webhookUrl` set to
`<BELLA_INTERNAL_URL>/webhook/<WEBHOOK_SECRET>`. **This is safe to run
against the already-connected, already-paired instance** — it does not
re-pair or log out the live WhatsApp session. That's not obvious from
Evolution GO's hosted docs, which describe `/instance/connect` only as the
initial pairing call; it was confirmed by reading the actual source
(`pkg/instance/service/instance_service.go`, function `Connect`): when a
client is already running for the instance, it just updates the stored
webhook URL/event subscriptions and syncs them onto the live session — it
only starts a fresh client (which is what triggers QR/pairing) when nothing
was running yet. Re-run this script any time `WEBHOOK_SECRET` or
`BELLA_INTERNAL_URL` changes.

The script prints Evolution GO's response, including the `webhookUrl` and
`eventString` it now has on file — confirm `webhookUrl` matches what you
expect before moving on.

## Step 8: set the WhatsApp presentation

```bash
python -m bella.scripts.set_presentation
```

This sets the profile picture (Evolution GO fetches it itself, over HTTP,
from `<BELLA_INTERNAL_URL>/assets/whatsapp-profile-picture.png` — a route
`bella/app.py` serves unauthenticated on purpose, since Evolution GO's fetch
call can't carry the webhook secret or any header) and the display name
(`BELLA_DISPLAY_NAME`).

## Step 9: verify every acceptance criterion

1. **A text DM to Bella's real number gets the skeleton reply, served from
   the VPS.** From any phone, message the connected WhatsApp number. Expect
   the ticket-02 skeleton echo reply within a few seconds.
2. **The container reaches Postgres and Evolution GO over the internal
   network; no new published ports for Postgres.** Re-run the Step 3
   verification. Separately confirm in Coolify (or `docker port
   <postgres-container>`) that Postgres still has no port published to the
   host/internet — this deploy must not have added one.
3. **Health endpoint reports healthy; Coolify restarts on failure.** Check
   Coolify's dashboard shows the app healthy. To actually exercise the
   restart policy, you can temporarily break the health check path in
   Coolify's config, watch it flip unhealthy, then restore it — optional,
   but the only way to be sure the restart policy is really wired up rather
   than just configured.
4. **Bella's WhatsApp profile shows the picture and display name.** Open a
   chat with Bella's number on a phone and check her contact info.
5. **No secret appears in the repo or image.** True by construction — the
   Dockerfile never `COPY`s `.env` (it's `.dockerignore`d), and every secret
   above is read from the environment at runtime via `bella/config.py`'s
   `Settings.from_env()`. If you want to double check the built image
   directly: `docker run --rm <image> env | grep -iE 'key|secret|token'`
   should print nothing (the variables only exist because Coolify injects
   them into the running container, not the image).

## What's deliberately not here

- No Postgres schema or connection string wiring — that's ticket 06. This
  ticket only needs the network path to exist.
- No content-mounting story for `content/*.yaml` beyond baking it into the
  image at build time. If editing the Enrollment Card without a rebuild
  becomes a real workflow need, revisit with a volume mount — out of scope
  here since no code reads those files yet.
