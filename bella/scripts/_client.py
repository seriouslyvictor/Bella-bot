"""Shared HTTP helper for the scripts in this package.

Separate from bella.evolution.EvolutionSender: that class is the runtime
message-sending path (send/text), authenticated the same way, but these
scripts hit Evolution GO's instance/user admin endpoints instead, which the
running app never calls.
"""

from typing import Any

import httpx

from bella.config import Settings


def post(settings: Settings, path: str, json: dict[str, Any]) -> dict[str, Any]:
    """POST to the Evolution GO instance and return the decoded JSON body.

    Raises httpx.HTTPStatusError on non-2xx — scripts are meant to fail loud
    and let the operator read the response instead of guessing.
    """
    url = f"{settings.evolution_url.rstrip('/')}{path}"
    headers = {"apikey": settings.evolution_api_key, "instanceId": settings.evolution_instance_id}
    with httpx.Client(timeout=30) as client:
        response = client.post(url, headers=headers, json=json)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data
