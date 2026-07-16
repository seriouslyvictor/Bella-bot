# 03 — Single-stack deployment to VPS

**What to build:** One Coolify-ready Docker Compose stack, sourced from this GitHub repository and runnable with the local Docker Engine, containing Bella, Evolution GO pinned to the official `evoapicloud/evolution-go:0.7.1` image, and Postgres 15. The stack owns its Docker network and reaches services by stable Compose names (`evolution-go:8080` and `postgres:5432`); it must not depend on a pre-existing or VPS-specific external network. Persist Postgres and Evolution state, initialize Bella's isolated database without touching Evolution GO's databases, and keep Postgres internal-only. Update the operator scripts and `.env.example` to use this stack's service names and environment contract. Deploy the same production Compose file from GitHub through Coolify, expose health endpoints for monitoring, register Bella's webhook, and set her WhatsApp profile picture and display name. Local values come from an ignored `.env`; production secrets come from Coolify.

**Blocked by:** 02 — Walking skeleton: echo bot.

**Status:** ready-for-agent

- [ ] The production Compose file starts locally with Docker Engine and deploys from GitHub as one Coolify stack
- [x] The stack contains Bella, exactly Evolution GO 0.7.1, and Postgres 15; no service uses a floating `latest` tag
- [x] Bella reaches Evolution GO at `evolution-go:8080` and Postgres at `postgres:5432` over a Compose-managed network, with no VPS-specific external network name
- [x] One persistent Postgres volume holds Bella and Evolution state; separate database roles enforce isolation, and the production stack publishes no Postgres host port
- [ ] Stack initialization and operator scripts use the documented `.env.example` contract in local Docker and Coolify
- [x] Bella exposes separate liveness/readiness signals, dependency failures turn readiness red, and restart policies recover exited processes
- [ ] Messaging Bella's real WhatsApp number gets the skeleton reply from the VPS, with the webhook registered
- [ ] Bella's WhatsApp profile shows the configured picture and display name
- [x] No secret appears in the repository or images; local secrets use ignored `.env` and production secrets use Coolify

## Comments

- 2026-07-15: Replaced the Bella-only/external-network deployment with one Compose project for Bella, Evolution GO 0.7.1 (tag plus registry digest), and Postgres 15. Added a loopback-only local overlay, isolated database roles, Compose health ordering, and a Coolify/local runbook. Evolution's full-URL logging made the old webhook-path secret unsafe; the fixed `/webhook` endpoint now validates the 0.7.1 payload's top-level `instanceToken` instead.
- 2026-07-15: Local Docker verification passed from a fresh named volume: all three containers became healthy, liveness/readiness responded, stopping Evolution turned Bella readiness 503 and restarting it recovered, service DNS worked in both directions, the initializer created `bella:bella`, `evogo_auth:evolution`, and `evogo_users:evolution`, cross-database `CONNECT` was denied, and forced recreation retained the test database. The three runtime manifests and Python dependency graph are pinned. Full suite: 50 passed including both real-Postgres integration tests; strict mypy passed. Remaining acceptance work requires Coolify/VPS access, Evolution license activation, instance creation/pairing, webhook/presentation scripts, and a real WhatsApp DM.
