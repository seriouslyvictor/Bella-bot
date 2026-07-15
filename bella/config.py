import os
from dataclasses import dataclass
from pathlib import Path

# Only the fallbacks for a source checkout — the image pins every one of these
# explicitly (see Dockerfile), because inferring the root from __file__ silently
# resolves into site-packages when the package is imported from an install
# rather than from /app. That caveat applies to all four paths below; this is
# its one home.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_CONTENT_DIR = _REPO_ROOT / "content"

DEFAULT_PROFILE_PICTURE_PATH = _REPO_ROOT / "whatsapp_profile_picture.png"
DEFAULT_CANNED_REPLIES_PATH = _CONTENT_DIR / "canned_replies.yaml"
DEFAULT_KNOWLEDGE_BASE_PATH = _CONTENT_DIR / "knowledge_base.md"
DEFAULT_ENROLLMENT_CARD_PATH = _CONTENT_DIR / "enrollment_card.yaml"


def _path_from_env(var: str, default: Path) -> Path:
    return Path(os.environ.get(var, default))


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
    database_url: str = ""
    bella_display_name: str = "Bella"
    profile_picture_path: Path = DEFAULT_PROFILE_PICTURE_PATH
    canned_replies_path: Path = DEFAULT_CANNED_REPLIES_PATH
    knowledge_base_path: Path = DEFAULT_KNOWLEDGE_BASE_PATH
    enrollment_card_path: Path = DEFAULT_ENROLLMENT_CARD_PATH

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            evolution_url=os.environ["EVOLUTION_URL"],
            evolution_api_key=os.environ["EVOLUTION_API_KEY"],
            evolution_instance_id=os.environ["EVOLUTION_INSTANCE_ID"],
            webhook_secret=os.environ["WEBHOOK_SECRET"],
            bella_internal_url=os.environ["BELLA_INTERNAL_URL"],
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            database_url=os.environ["BELLA_DATABASE_URL"],
            bella_display_name=os.environ.get("BELLA_DISPLAY_NAME", "Bella"),
            profile_picture_path=_path_from_env(
                "PROFILE_PICTURE_PATH", DEFAULT_PROFILE_PICTURE_PATH
            ),
            canned_replies_path=_path_from_env(
                "CANNED_REPLIES_PATH", DEFAULT_CANNED_REPLIES_PATH
            ),
            knowledge_base_path=_path_from_env(
                "KNOWLEDGE_BASE_PATH", DEFAULT_KNOWLEDGE_BASE_PATH
            ),
            enrollment_card_path=_path_from_env(
                "ENROLLMENT_CARD_PATH", DEFAULT_ENROLLMENT_CARD_PATH
            ),
        )
