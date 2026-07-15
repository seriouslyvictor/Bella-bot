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
DEFAULT_CANNED_REPLIES_PATH = (
    Path(__file__).resolve().parent.parent / "content" / "canned_replies.yaml"
)


@dataclass(frozen=True)
class Settings:
    # Evolution GO's base URL on the shared Docker network — its container
    # carries the `evolution-go` alias there, so the short name resolves.
    evolution_url: str
    evolution_api_key: str
    evolution_instance_id: str
    webhook_secret: str
    # Where Evolution GO reaches Bella on that same network: the `bella` alias
    # declared in docker-compose.yml (her container name is not stable across
    # redeploys, the alias is). Required rather than defaulted despite the
    # value being predictable — it has to agree with that compose alias, and a
    # mismatch doesn't raise anywhere, it just means webhooks silently never
    # arrive. Never a public address.
    bella_internal_url: str
    anthropic_api_key: str = ""
    bella_display_name: str = "Bella"
    profile_picture_path: Path = DEFAULT_PROFILE_PICTURE_PATH
    canned_replies_path: Path = DEFAULT_CANNED_REPLIES_PATH

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            evolution_url=os.environ["EVOLUTION_URL"],
            evolution_api_key=os.environ["EVOLUTION_API_KEY"],
            evolution_instance_id=os.environ["EVOLUTION_INSTANCE_ID"],
            webhook_secret=os.environ["WEBHOOK_SECRET"],
            bella_internal_url=os.environ["BELLA_INTERNAL_URL"],
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            bella_display_name=os.environ.get("BELLA_DISPLAY_NAME", "Bella"),
            profile_picture_path=Path(
                os.environ.get("PROFILE_PICTURE_PATH", DEFAULT_PROFILE_PICTURE_PATH)
            ),
            canned_replies_path=Path(
                os.environ.get("CANNED_REPLIES_PATH", DEFAULT_CANNED_REPLIES_PATH)
            ),
        )
