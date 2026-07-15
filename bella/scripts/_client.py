"""Shared HTTP helper for the scripts in this package.

Separate from bella.evolution.EvolutionSender: that class is the runtime
message-sending path (send/text), while these scripts hit Evolution GO's
instance/user endpoints, which the running app never calls. They authenticate
identically, and that is load-bearing rather than incidental:

Every endpoint this repo touches — /instance/connect, /user/profilePicture,
/user/profileName and /send/text — sits behind evolution-go's `Auth`
middleware, which resolves the `apikey` header to an instance by looking its
token up in the database (pkg/routes/routes.go groups them all under
`authMiddleware.Auth`; pkg/middleware/auth_middleware.go:21). So EVOLUTION_API_KEY
must hold the INSTANCE token, not GLOBAL_API_KEY. The global key only opens the
separate `AuthAdmin` group (/instance/create, /instance/all, /instance/info/:id,
...), which we never call — and it is NOT accepted as a fallback on Auth routes.

Note the published webhook docs disagree, telling you to send GLOBAL_API_KEY
plus an instanceId header for /instance/connect. They are wrong on both counts:
evolution-go reads no header other than `apikey` anywhere in its codebase, and
its own in-repo wiki contradicts the hosted page ("Use o `token` que você
definiu ao criar a instância, NÃO a `GLOBAL_API_KEY`" —
docs/wiki/guias-api/api-instances.md).
"""

from typing import Any

import httpx

from bella.config import Settings


def post(
    settings: Settings,
    path: str,
    json: dict[str, Any],
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """POST to the Evolution GO instance and return the decoded JSON body.

    Raises on non-2xx — scripts are meant to fail loud and let the operator
    read the error rather than guess.
    """
    url = f"{settings.evolution_url.rstrip('/')}{path}"
    # instanceId is sent because the published docs specify it; evolution-go
    # ignores it (apikey is the only header it reads) and identifies the
    # instance from the token instead. Harmless, and cheap insurance if a
    # later version starts honouring it.
    headers = {"apikey": settings.evolution_api_key, "instanceId": settings.evolution_instance_id}

    owned = client is None
    http = client or httpx.Client(timeout=30)
    try:
        response = http.post(url, headers=headers, json=json)
    finally:
        if owned:
            http.close()

    if response.status_code == 401:
        # The generic httpx message here would send the reader hunting for a
        # bad URL or a missing header; the cause is almost always the wrong
        # *kind* of key.
        raise RuntimeError(
            f"401 Unauthorized from Evolution GO at {path}. This endpoint "
            "authenticates with the INSTANCE token — the `token` the instance "
            "was created with — not GLOBAL_API_KEY. Check EVOLUTION_API_KEY; "
            "see docs/deploy.md ('Which Evolution GO credential')."
        )
    response.raise_for_status()

    data: dict[str, Any] = response.json()
    return data
