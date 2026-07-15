# Deploying Bella to the VPS (Ticket 03)

This is the owner's runbook — an agent prepared everything below but has no
VPS or Coolify access and cannot run any of it. Follow the steps in order.
Steps 4, 6 and 7 depend on values you read off the VPS in earlier steps, so
the ordering is load-bearing, not stylistic.

## Architecture decision: separate Coolify app + shared network

The spec allows two ways to get Bella onto the Evolution GO stack's Docker
network: deploy her as an extra service inside that stack's own
docker-compose, or deploy her as an independent resource attached via a
shared Docker network.

**This runbook uses the shared-network approach.** Reasons:

- Editing the live Evolution stack's compose file to add a service risks
  disrupting the already-connected WhatsApp number.
- Bella's release cadence (a bot under active development, tickets 04–09
  still to come) is decoupled from Evolution GO's — she can redeploy, crash,
  or roll back without touching the messaging infra.

The cost is real and shows up throughout this runbook: Coolify's "Connect to
Predefined Networks" option, which this approach depends on, **breaks
short-name Docker DNS**. Per Coolify's own docs, it renames stacks to
`<service>-<uuid>` to prevent collisions, and you must address them by that
fully-qualified name. So `evolution-go` is *not* a reliable hostname here
even though the alias exists; `evolution-go-ohilulk0h2zy70nhcc536np4` is.
This is why `EVOLUTION_URL` and `BELLA_INTERNAL_URL` are **required env vars
with no defaults** in `bella/config.py` — a default that's wrong in the only
environment that runs it is worse than no default.

## Step 0: what you're setting up

- A new Coolify application, built from this repo's `Dockerfile`, with no
  public domain and no published ports (spec: Bella is internal-only).
- That application joins the Evolution GO stack's existing Docker network,
  **`ohilulk0h2zy70nhcc536np4`**. Evolution GO and Postgres are both on it,
  so one attachment covers both.
- Two scripts, run once from inside the deployed container, that register
  Bella's webhook with Evolution GO and set her WhatsApp profile picture and
  display name.

## Step 1: the network (already confirmed)

Both services live on network **`ohilulk0h2zy70nhcc536np4`** — confirmed on
the VPS, no discovery needed.

`docker inspect` on the evolution-go container reports IP `10.0.2.3` and DNS
names `evolution-go-ohilulk0h2zy70nhcc536np4`, `evolution-go`. Use the long
form (see the DNS caveat above).

Postgres is confirmed to be on the same network. Its hostname is **inferred**
to be `postgres-ohilulk0h2zy70nhcc536np4:5432` from Coolify's
`<service>-<uuid>` rule — unlike the evolution-go name, that has *not* been
read off a real `docker inspect`. Nothing in this ticket connects to
Postgres, so the inference costs nothing now; when you wire it up in ticket
06, confirm the real hostname first:

```bash
docker ps --format '{{.Names}}' | grep -i postgres
docker inspect <postgres-container> --format '{{json .NetworkSettings.Networks}}'
```

## Step 2: create the Coolify application

1. New Resource → Application → deploy from this Git repo, the branch you
   want live.
2. Build pack: **Dockerfile** (the repo's `Dockerfile` at root).
3. **No domain.** Do not set an FQDN and do not expose a port — leave
   Coolify's port mapping empty. Bella is only ever reached by other
   containers on the internal network, never from outside the VPS.

## Step 3: attach the shared network

Enable **Connect to Predefined Network** on the application and set it to
`ohilulk0h2zy70nhcc536np4`.

If your Coolify version doesn't surface that option, the fallback is
`docker network connect ohilulk0h2zy70nhcc536np4 <bella-container>` after
each deploy — but note it does **not** survive a redeploy (Coolify recreates
the container), so check whether Coolify exposes a post-deployment hook to
automate it.

## Step 4: environment variables (first pass)

Set these in Coolify's environment variables panel (mark them
"secret"/masked if your version offers it). Never put real values in this
repo. `.env.example` lists the same names as a copy-paste template.

`BELLA_INTERNAL_URL` is deliberately **not** finalized yet — you can't know
its value until the container exists. Step 6 fills it in.

| Variable | Value | Notes |
|---|---|---|
| `EVOLUTION_API_KEY` | Owner's existing local `.env` | The Evolution GO instance token — same value already used for the walking skeleton |
| `EVOLUTION_INSTANCE_ID` | Owner's existing local `.env` | — |
| `WEBHOOK_SECRET` | Generate fresh: `python -c "import secrets; print(secrets.token_urlsafe(32))"` | Lives in the webhook URL path (`/webhook/<secret>`), not a header — see `bella/app.py` |
| `EVOLUTION_URL` | `http://evolution-go-ohilulk0h2zy70nhcc536np4:8080` | **Set this explicitly.** The short `evolution-go` alias exists but isn't reliable under Coolify's predefined-network mode. Required — the app won't boot without it |
| `BELLA_DISPLAY_NAME` | e.g. `Bella` | What `set_presentation.py` sets as the WhatsApp display name |
| `BELLA_INTERNAL_URL` | *(Step 6)* | Required — the app won't boot without it |

To get the app to boot for Step 5, set `BELLA_INTERNAL_URL` to a placeholder
(`http://placeholder:8000`) for now. Nothing reads it until Step 7, and Step
6 replaces it with the real value.

## Step 5: health check, restart policy, and first deploy

Set the HTTP health check to `GET /health` on port 8000 (internal — Coolify
talks to the container directly, no public port needed). Set the restart
policy to restart on failure. The image also ships a container-level
`HEALTHCHECK` (see `Dockerfile`) as a redundant signal for `docker inspect`.

Deploy. Confirm the app comes up healthy in Coolify's dashboard.

## Step 6: read Bella's real hostname and set `BELLA_INTERNAL_URL`

This is the highest-risk value in the whole deploy. Evolution GO posts
webhooks to it; if it's wrong, **nothing errors** — Bella just never
receives anything, on a live WhatsApp number.

Get Bella's actual container name:

```bash
docker ps --format '{{.Names}}' | grep -i bella
```

By Coolify's naming rule it'll be `bella-<some-uuid>` — her own uuid, *not*
the Evolution stack's, and *not* the bare `bella`. Confirm what she answers
to on the shared network:

```bash
docker inspect <bella-container> --format '{{json .NetworkSettings.Networks}}'
```

Then set `BELLA_INTERNAL_URL` to `http://<that-name>:8000` in Coolify's env
panel (replacing the Step 4 placeholder) and redeploy.

Now verify the links that actually matter, in both directions:

```bash
# Bella -> Evolution GO
docker exec <bella-container> python -c "import socket; print(socket.gethostbyname('evolution-go-ohilulk0h2zy70nhcc536np4'))"

# Bella -> Postgres (acceptance criterion 2; use the real hostname per Step 1)
docker exec <bella-container> python -c "import socket; print(socket.gethostbyname('postgres-ohilulk0h2zy70nhcc536np4'))"

# Evolution GO -> Bella. This is the one that silently breaks; check it
# BEFORE touching the WhatsApp number.
docker exec <evolution-go-container> wget -qO- http://<bella-container>:8000/health
```

That last command must print `{"status":"ok"}`. If it doesn't, stop and fix
the networking — Step 7 will appear to succeed regardless, and you'll be
debugging silence on a live number instead.

## Step 7: register the webhook

From Coolify's terminal (or `docker exec -it <bella-container> sh`):

```bash
python -m bella.scripts.register_webhook
```

This calls Evolution GO's `POST /instance/connect` with `webhookUrl` set to
`<BELLA_INTERNAL_URL>/webhook/<WEBHOOK_SECRET>`. **Safe against the
already-connected, already-paired instance** — it does not re-pair or log
out the live session. That's not obvious from Evolution GO's hosted docs,
which describe `/instance/connect` only as the initial pairing call; it was
confirmed by reading the source (`pkg/instance/service/instance_service.go`,
`Connect`): when a client is already running, it only updates the stored
webhook URL/subscriptions and syncs them onto the live session, and starts a
fresh client (the QR/pairing path) only when nothing was running yet.

The script checks Evolution GO's echoed `webhookUrl` against what it sent
and prints a pass/fail — it deliberately does **not** print the URL itself,
since the secret is in the path and this output lands in your terminal
scrollback. Expect `OK: Evolution GO has the expected webhook URL on file.`
A `MISMATCH` line exits non-zero.

Re-run this any time `WEBHOOK_SECRET` or `BELLA_INTERNAL_URL` changes.

## Step 8: set the WhatsApp presentation

```bash
python -m bella.scripts.set_presentation
```

Sets the profile picture — Evolution GO fetches it itself, over plain HTTP,
from `<BELLA_INTERNAL_URL>/assets/whatsapp-profile-picture.png`, a route
`bella/app.py` serves unauthenticated on purpose because Evolution GO's
fetch can't carry a header — and the display name from `BELLA_DISPLAY_NAME`.
Depends on Step 6's Evolution-GO-can-reach-Bella check having passed.

## Step 9: verify every acceptance criterion

1. **A text DM to Bella's real number gets the skeleton reply, served from
   the VPS.** Message the connected number from any phone; expect the
   ticket-02 echo reply within a few seconds.
2. **The container reaches Postgres and Evolution GO over the internal
   network; no new published ports for Postgres.** Reachability is covered
   by Step 6's two `gethostbyname` checks. The no-published-port half is a
   separate question — being on the shared network says nothing about
   whether a host port got exposed — so confirm explicitly: `docker port
   <postgres-container>` should print nothing.
3. **Health endpoint reports healthy; Coolify restarts on failure.** Coolify
   shows the app healthy. To actually exercise the restart policy rather
   than just trust it's configured, temporarily point the health check at a
   bogus path, watch it flip unhealthy and restart, then restore it.
4. **Bella's WhatsApp profile shows the picture and display name.** Open a
   chat with her number on a phone and check the contact info.
5. **No secret appears in the repo or image.** True by construction: the
   Dockerfile never `COPY`s `.env` (it's `.dockerignore`d), and every secret
   is read from the environment at runtime via `Settings.from_env()`. To
   check the image directly: `docker run --rm <image> env | grep -iE
   'key|secret|token'` should print nothing — the variables exist only
   because Coolify injects them into the running container.

## Known unverified assumptions

- **Postgres's hostname** — the network is confirmed, but
  `postgres-ohilulk0h2zy70nhcc536np4` is inferred from Coolify's naming rule
  rather than observed. Costs nothing here (nothing connects to Postgres in
  this ticket); ticket 06 must use the name it actually observes.
- **Bella's container name** (Step 6) — depends on the uuid Coolify assigns
  her app, which doesn't exist until you create it.
- **Coolify's exact UI labels** for the predefined-network option and the
  health check, which have moved between Coolify versions.

## What's deliberately not here

- No Postgres schema or connection-string wiring — that's ticket 06. This
  ticket only needs the network path to exist.
- No volume-mount story for `content/*.yaml`; it's baked into the image at
  build time. Revisit if editing the Enrollment Card without a rebuild
  becomes a real need — out of scope here, since no code reads those files
  yet.
