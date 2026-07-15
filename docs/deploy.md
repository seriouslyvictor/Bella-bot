# Deploying Bella to the VPS (Ticket 03)

This is the owner's runbook — an agent prepared everything below but has no
VPS or Coolify access and cannot run any of it. Follow the steps in order.

## Architecture decision: Coolify app, Docker Compose build pack

Bella deploys as her own Coolify **application using the Docker Compose build
pack**, and this repo's `docker-compose.yml` is the deployment artifact. Its
`networks:` block declares the Evolution stack's network as `external: true`,
and that declaration alone is what joins her to it.

**The Dockerfile/Git build pack was tried first and does not work here**, for
two independent reasons found on the real VPS:

- Coolify's "Connect to Predefined Network" option isn't available for
  Git-deployed applications, so there's no mechanism to join the Evolution
  network. Bella landed on the `coolify` network (10.0.1.x) with no route to
  Evolution GO or Postgres on `ohilulk0h2zy70nhcc536np4` (10.0.2.x).
- Git-deployed containers are named `<app-uuid>-<deployment-timestamp>` with
  no stable alias. Since `BELLA_INTERNAL_URL` is baked into Evolution's
  stored webhook registration, that name changing on every redeploy would
  silently break inbound messages every time.

Moving Evolution+Postgres to the `coolify` network was rejected instead: it
wouldn't fix Bella's unstable hostname, and it risks recreating containers
holding a live, paired WhatsApp session. Bella is the disposable side, so
Bella moves.

### The hostname question, settled

Short names work. `EVOLUTION_URL=http://evolution-go:8080` and
`BELLA_INTERNAL_URL=http://bella:8000`. Both are aliases on the shared
network, and neither contains a uuid or a timestamp.

Earlier drafts of this runbook used fully-qualified `<service>-<uuid>` names,
reasoning from Coolify's documented warning that the predefined-network
toggle "makes the internal Docker DNS not work as expected". **That warning
describes a different code path** — the `connect_to_docker_network` setting,
which only exists for Compose *Services* and never runs for us. Verified
against Coolify's source (`bootstrap/helpers/parsers.php`,
`applicationParser` — the parser version 5 that new apps get, per
`app/Models/Application.php`, `private static $parserVersion = '5'`):

- Our top-level `networks:` block is **preserved verbatim**; Coolify only
  *adds* its own `<app-uuid>` network alongside it.
- Our service `aliases:` are **preserved verbatim** (arrays under a service's
  `networks:` key are copied through untouched).
- `container_name` **is** force-overridden to `bella-<app-uuid>-<timestamp>`
  (`generateApplicationContainerName` in `bootstrap/helpers/docker.php`
  appends `now()->format('Hisu')` — exactly the observed `...-172744767759`,
  i.e. 17:27:44.767759). We never use that name; the alias is the point.
- `evolution-go` is an observed alias on the real container:
  `"Aliases":["evolution-go-ohilulk0h2zy70nhcc536np4","evolution-go"]`.

So the durable rule: **address things by network alias, never by container
name.**

## Step 0: what you're setting up

- A Coolify application built from `docker-compose.yml` via the Docker
  Compose build pack, with no public domain and no published ports.
- The compose file joins her to network `ohilulk0h2zy70nhcc536np4`, where
  Evolution GO and Postgres already live.
- Two scripts, run once from inside the deployed container, that register
  Bella's webhook and set her WhatsApp profile picture and display name.

## Step 1: network facts (already confirmed — no discovery needed)

Network **`ohilulk0h2zy70nhcc536np4`**, observed on the VPS. Evolution GO is
at `10.0.2.3` with aliases `evolution-go-ohilulk0h2zy70nhcc536np4` and
`evolution-go`. Postgres is on the same network.

Postgres's hostname is **inferred** to be `postgres:5432` (by the same alias
rule) — that has *not* been read off a real `docker inspect`. Nothing in this
ticket connects to Postgres, so the inference costs nothing now. Ticket 06
must confirm it first:

```bash
docker ps --format '{{.Names}}' | grep -i postgres
docker inspect <postgres-container> --format '{{json .NetworkSettings.Networks}}'
```

## Step 2: create the Coolify application

1. New Resource → Application → deploy from this Git repo, the branch you
   want live.
2. Build pack: **Docker Compose**. Compose file location: `docker-compose.yml`.
3. **No domain**, no ports exposed. Bella is only reached by other containers
   on the internal network.
4. Leave **Raw Compose Deployment** OFF. It makes Coolify use the file
   verbatim and skip the `env_file: [.env]` injection that delivers your
   environment variables into the container.

There is no network toggle to set — the compose file's `external: true`
network does that job. If you go looking for "Connect to Predefined Network",
you won't find it on an application; that's expected, not a mistake.

## Step 3: environment variables

Set these in Coolify's environment variables panel (mark them
"secret"/masked if your version offers it). Never put real values in this
repo. `.env.example` lists the same names as a copy-paste template.

Coolify writes these into a `.env` on the server and auto-injects
`env_file: [.env]` into the compose file — which is why `docker-compose.yml`
declares no `env_file` of its own.

| Variable | Value | Notes |
|---|---|---|
| `EVOLUTION_API_KEY` | Owner's existing local `.env` | The Evolution GO instance token — same value already used for the walking skeleton |
| `EVOLUTION_INSTANCE_ID` | Owner's existing local `.env` | — |
| `WEBHOOK_SECRET` | Generate fresh: `python -c "import secrets; print(secrets.token_urlsafe(32))"` | Lives in the webhook URL path (`/webhook/<secret>`), not a header — see `bella/app.py` |
| `EVOLUTION_URL` | `http://evolution-go:8080` | Observed alias on the shared network. Required — the app won't boot without it |
| `BELLA_INTERNAL_URL` | `http://bella:8000` | The alias declared in `docker-compose.yml`. Required. **Never** Bella's container name — that changes every redeploy |
| `BELLA_DISPLAY_NAME` | e.g. `Bella` | What `set_presentation.py` sets as the WhatsApp display name |

Unlike the previous Dockerfile-based plan, every value is known up front — no
placeholder-then-fix-it dance, because the hostname comes from our own
compose file rather than from whatever Coolify names the container.

## Step 4: health check, restart policy, deploy

Set the HTTP health check to `GET /health` on port 8000 (internal — Coolify
talks to the container directly). Set the restart policy to restart on
failure. `docker-compose.yml` also declares a compose-level `healthcheck`,
and the image ships a `HEALTHCHECK` too, as redundant signals for
`docker inspect`.

Deploy. Confirm it comes up healthy in Coolify's dashboard.

## Step 5: verify the network path — before touching the live number

This is the check that caught the failed Dockerfile deploy, and it's cheap.
The Evolution-GO→Bella direction is the one that fails silently.

```bash
# Bella is actually on the Evolution network (expect an entry for
# ohilulk0h2zy70nhcc536np4, alias `bella`, on a 10.0.2.x address)
docker inspect $(docker ps -qf name=bella) --format '{{json .NetworkSettings.Networks}}'

# Bella -> Evolution GO
docker exec $(docker ps -qf name=bella) python -c "import socket; print(socket.gethostbyname('evolution-go'))"

# Bella -> Postgres (acceptance criterion 2; hostname per Step 1)
docker exec $(docker ps -qf name=bella) python -c "import socket; print(socket.gethostbyname('postgres'))"

# Evolution GO -> Bella. THE one that silently breaks.
docker exec <evolution-go-container> wget -qO- http://bella:8000/health
```

That last command must print `{"status":"ok"}`. If it doesn't, stop — Step 6
will report success regardless, and you'll be debugging silence on a live
WhatsApp number.

If you want to prove the path works without a redeploy,
`docker network connect ohilulk0h2zy70nhcc536np4 <bella-container>` attaches
a running container by hand. That is a **diagnostic, not the deploy** — it's
lost on the next redeploy, and it gets you the container name, not the
`bella` alias. The compose file is what makes it durable.

## Step 6: register the webhook

From Coolify's terminal (or `docker exec -it <bella-container> sh`):

```bash
python -m bella.scripts.register_webhook
```

This calls Evolution GO's `POST /instance/connect` with `webhookUrl` set to
`<BELLA_INTERNAL_URL>/webhook/<WEBHOOK_SECRET>`. **Safe against the
already-connected, already-paired instance** — it does not re-pair or log out
the live session. That's not obvious from Evolution GO's hosted docs, which
describe `/instance/connect` only as the initial pairing call; it was
confirmed by reading the source (`pkg/instance/service/instance_service.go`,
`Connect`): when a client is already running it only updates the stored
webhook URL/subscriptions and syncs them onto the live session, and starts a
fresh client (the QR/pairing path) only when nothing was running yet.

The script checks Evolution GO's echoed `webhookUrl` against what it sent and
prints a pass/fail — it deliberately does **not** print the URL, since the
secret is in the path and this output lands in your terminal scrollback.
Expect `OK: Evolution GO has the expected webhook URL on file.` A `MISMATCH`
line exits non-zero.

Re-run any time `WEBHOOK_SECRET` or `BELLA_INTERNAL_URL` changes. You do
**not** need to re-run it after an ordinary redeploy — that's the entire
point of the alias.

## Step 7: set the WhatsApp presentation

```bash
python -m bella.scripts.set_presentation
```

Sets the profile picture — Evolution GO fetches it itself, over plain HTTP,
from `<BELLA_INTERNAL_URL>/assets/whatsapp-profile-picture.png`, a route
`bella/app.py` serves unauthenticated on purpose because Evolution GO's fetch
can't carry a header — and the display name from `BELLA_DISPLAY_NAME`.
Depends on Step 5's Evolution-GO→Bella check having passed.

## Step 8: verify every acceptance criterion

1. **A text DM to Bella's real number gets the skeleton reply, served from
   the VPS.** Message the connected number from any phone; expect the
   ticket-02 echo reply within a few seconds.
2. **The container reaches Postgres and Evolution GO over the internal
   network; no new published ports for Postgres.** Reachability is Step 5.
   The no-published-port half is a separate question — being on a shared
   network says nothing about host port exposure — so confirm explicitly:
   `docker port <postgres-container>` should print nothing.
3. **Health endpoint reports healthy; Coolify restarts on failure.** Coolify
   shows the app healthy. To actually exercise the restart policy rather than
   trust it's configured, temporarily point the health check at a bogus path,
   watch it flip unhealthy and restart, then restore it.
4. **Bella's WhatsApp profile shows the picture and display name.** Open a
   chat with her number on a phone and check the contact info.
5. **No secret appears in the repo or image.** True by construction: the
   Dockerfile never `COPY`s `.env` (it's `.dockerignore`d), and every secret
   is read from the environment at runtime via `Settings.from_env()`. To
   check the image: `docker run --rm <image> env | grep -iE 'key|secret|token'`
   should print nothing.

**Then redeploy once and re-run Step 5 and criterion 1.** The whole design
rests on Bella staying reachable at `bella` across redeploys, and that's
precisely what the Dockerfile route got wrong. The failure is invisible until
someone messages her, so prove it once, deliberately.

## Known unverified assumptions

- **Postgres's hostname** — network confirmed, `postgres` alias inferred from
  the alias rule rather than observed. Costs nothing here; ticket 06 must
  confirm.
- **Coolify's exact UI labels** for the build pack, health check, and Raw
  Compose Deployment, which move between versions.
- Everything about the compose transformation is read from Coolify's source
  at a point in time. If Coolify is upgraded and Bella stops receiving
  messages after a redeploy, suspect the alias handling first and re-check
  `applicationParser` in `bootstrap/helpers/parsers.php`.

## What's deliberately not here

- No Postgres schema or connection-string wiring — that's ticket 06. This
  ticket only needs the network path to exist.
- No volume-mount story for `content/*.yaml`; it's baked into the image at
  build time. Revisit if editing the Enrollment Card without a rebuild
  becomes a real need — out of scope, since no code reads those files yet.
