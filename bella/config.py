import os
from dataclasses import dataclass
from pathlib import Path

from bella.rate_limit import RateLimitPolicy

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
DEFAULT_APOSTILA_PATH = _CONTENT_DIR / "apostila.pdf"


def _path_from_env(var: str, default: Path) -> Path:
    return Path(os.environ.get(var, default))


# The dataclass owns the numbers; the env vars only override them.
_RATE_LIMIT_DEFAULTS = RateLimitPolicy()


def _int_from_env(var: str, default: int) -> int:
    return int(os.environ.get(var, default))


@dataclass(frozen=True)
class Settings:
    # Evolution GO's service URL on the unified Compose network.
    evolution_url: str
    evolution_api_key: str
    evolution_instance_id: str
    # Where Evolution GO reaches Bella on that same network. This must agree
    # with the `bella` Compose service name; a mismatch makes webhooks silently
    # disappear. It is never a public address.
    bella_internal_url: str
    anthropic_api_key: str = ""
    database_url: str = ""
    admin_contact: str = ""
    bella_display_name: str = "Bella"
    profile_picture_path: Path = DEFAULT_PROFILE_PICTURE_PATH
    canned_replies_path: Path = DEFAULT_CANNED_REPLIES_PATH
    knowledge_base_path: Path = DEFAULT_KNOWLEDGE_BASE_PATH
    enrollment_card_path: Path = DEFAULT_ENROLLMENT_CARD_PATH
    apostila_path: Path = DEFAULT_APOSTILA_PATH
    rate_limit_policy: RateLimitPolicy = RateLimitPolicy()
    # Sliding Takeover Pause window (ADR 0003), reset by every human message.
    takeover_pause_seconds: int = 3600
    seat_count_refresh_seconds: int = 6 * 60 * 60
    seat_count_max_age_seconds: int = 24 * 60 * 60

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            evolution_url=os.environ["EVOLUTION_URL"],
            evolution_api_key=os.environ["EVOLUTION_API_KEY"],
            evolution_instance_id=os.environ["EVOLUTION_INSTANCE_ID"],
            bella_internal_url=os.environ["BELLA_INTERNAL_URL"],
            anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
            database_url=os.environ["BELLA_DATABASE_URL"],
            admin_contact=os.environ["ADMIN_CONTACT"],
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
            apostila_path=_path_from_env("APOSTILA_PATH", DEFAULT_APOSTILA_PATH),
            rate_limit_policy=RateLimitPolicy(
                max_messages=_int_from_env(
                    "RATE_LIMIT_MAX_MESSAGES", _RATE_LIMIT_DEFAULTS.max_messages
                ),
                window_seconds=_int_from_env(
                    "RATE_LIMIT_WINDOW_SECONDS", _RATE_LIMIT_DEFAULTS.window_seconds
                ),
            ),
            takeover_pause_seconds=_int_from_env(
                "TAKEOVER_PAUSE_SECONDS", cls.takeover_pause_seconds
            ),
            seat_count_refresh_seconds=_int_from_env(
                "SEAT_COUNT_REFRESH_SECONDS", cls.seat_count_refresh_seconds
            ),
            seat_count_max_age_seconds=_int_from_env(
                "SEAT_COUNT_MAX_AGE_SECONDS", cls.seat_count_max_age_seconds
            ),
        )
