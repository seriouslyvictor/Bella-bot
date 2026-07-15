# 03 — Deploy to VPS

**What to build:** The skeleton running in production on the existing VPS. Containerize the service and deploy via Coolify, joined to the Evolution compose stack's Docker network so it can reach Postgres (`postgres:5432`, internal-only) and Evolution GO (`evolution-go:8080`) by service name. Expose a health endpoint for Coolify monitoring. Register Bella's webhook (with the shared secret) on the Evolution GO instance. Set Bella's WhatsApp presentation via the Evolution API: profile picture (asset already in the repo) and display name. All secrets come from environment variables configured in Coolify.

**Blocked by:** 02 — Walking skeleton: echo bot.

**Status:** ready-for-agent

- [ ] Messaging Bella's real WhatsApp number from any phone gets the skeleton reply, served from the VPS
- [ ] The container reaches Postgres and Evolution GO over the internal stack network (no new published ports for Postgres)
- [ ] Health endpoint reports healthy; Coolify restarts the service on failure
- [ ] Bella's WhatsApp profile shows the profile picture and a proper display name
- [ ] No secret appears in the repo or image; all supplied via Coolify environment
