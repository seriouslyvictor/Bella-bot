"""Registers Bella's webhook URL on the Evolution GO instance.

Run once after deploy, from inside the Bella container (`python -m
bella.scripts.register_webhook`) — see docs/deploy.md. Re-run whenever
BELLA_INTERNAL_URL changes.

Safe to run against the already-connected, already-paired instance: Evolution
GO's POST /instance/connect only starts a fresh QR/pairing flow when no
client is running yet for the instance. When one is already running (our
case — the WhatsApp number is already connected), it just updates the stored
webhook URL/subscriptions and syncs them onto the live session in place, with
no disconnect or re-pair. Verified by reading evolution-go's source
(pkg/instance/service/instance_service.go: Connect() calls
UpdateInstanceSettings() first and only falls through to StartClient() when
that fails because nothing is running yet) — the hosted docs don't spell this
out, so don't take it on faith without checking that file again if evolution-
go is ever upgraded.
"""

from bella.config import Settings
from bella.scripts._client import post


def main() -> None:
    settings = Settings.from_env()
    webhook_url = f"{settings.bella_internal_url.rstrip('/')}/webhook"

    print(f"Registering webhook: {webhook_url}")
    response = post(
        settings,
        "/instance/connect",
        {"webhookUrl": webhook_url, "subscribe": ["MESSAGE"], "immediate": True},
    )

    # Evolution GO echoes the registered webhookUrl straight back, so verify
    # the value instead of relying on an operator to notice a mismatch.
    body = response.get("data") or {}
    registered = body.get("webhookUrl")
    if registered != webhook_url:
        print(f"MISMATCH: Evolution GO reports {registered}")
        raise SystemExit(1)

    print("OK: Evolution GO has the expected webhook URL on file.")
    print("Subscribed events:", body.get("eventString"))


if __name__ == "__main__":
    main()
