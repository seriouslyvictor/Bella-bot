import os
from dataclasses import dataclass
from pathlib import Path

# Repo root / whatsapp_profile_picture.png. Only the fallback for a source
# checkout — the image sets PROFILE_PICTURE_PATH explicitly (see Dockerfile),
# because inferring it from __file__ silently resolves into site-packages when
# the package is imported from an install rather than from /app.
DEFAULT_PROFILE_PICTURE_PATH = (
    Path(__file__).resolve().parent.parent / "whatsapp_profile_picture.png"
)


@dataclass(frozen=True)
class Settings:
    # Evolution GO's base URL on the shared Docker network. Coolify's
    # "Connect to Predefined Networks" breaks short-name DNS, so in the real
    # deployment this is the fully-qualified `evolution-go-<stack-uuid>:8080`
    # — no default here, because the obvious one is wrong where it counts.
    evolution_url: str
    evolution_api_key: str
    evolution_instance_id: str
    webhook_secret: str
    # Where Evolution GO can reach Bella on that same network — the address
    # her webhook and profile picture are registered under (see
    # bella/scripts/). Same fully-qualified naming rule, same no-default
    # reasoning, and doubly so: a wrong value here doesn't raise anywhere, it
    # just means webhooks silently never arrive. Never a public address.
    bella_internal_url: str
    bella_display_name: str = "Bella"
    profile_picture_path: Path = DEFAULT_PROFILE_PICTURE_PATH

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            evolution_url=os.environ["EVOLUTION_URL"],
            evolution_api_key=os.environ["EVOLUTION_API_KEY"],
            evolution_instance_id=os.environ["EVOLUTION_INSTANCE_ID"],
            webhook_secret=os.environ["WEBHOOK_SECRET"],
            bella_internal_url=os.environ["BELLA_INTERNAL_URL"],
            bella_display_name=os.environ.get("BELLA_DISPLAY_NAME", "Bella"),
            profile_picture_path=Path(
                os.environ.get("PROFILE_PICTURE_PATH", DEFAULT_PROFILE_PICTURE_PATH)
            ),
        )
