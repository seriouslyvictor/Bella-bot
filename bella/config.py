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
_ARCHIVE_SENAI_DIR = _REPO_ROOT / "archive" / "senai"

# WhatsApp only accepts JPEG profile pictures (whatsmeow rejects PNG uploads
# with a server error), so the asset is a square 640x640 JPEG.
DEFAULT_PROFILE_PICTURE_PATH = _CONTENT_DIR / "whatsapp_profile_picture.jpg"
DEFAULT_CANNED_REPLIES_PATH = _CONTENT_DIR / "canned_replies.yaml"
DEFAULT_KNOWLEDGE_BASE_PATH = _CONTENT_DIR / "knowledge_base.md"
DEFAULT_ENROLLMENT_CARD_PATH = (
    _CONTENT_DIR / "enrollment_card.yaml"
    if (_CONTENT_DIR / "enrollment_card.yaml").is_file()
    else _ARCHIVE_SENAI_DIR / "enrollment_card.yaml"
)
DEFAULT_APOSTILA_PATH = (
    _CONTENT_DIR / "apostila.pdf"
    if (_CONTENT_DIR / "apostila.pdf").is_file()
    else _ARCHIVE_SENAI_DIR / "apostila.pdf"
)
DEFAULT_INBOX_PATH = Path("inbox.md")
DEFAULT_APPS_DIR = _CONTENT_DIR / "apps"


def _path_from_env(var: str, default: Path) -> Path:
    return Path(os.environ.get(var, default))


# The dataclass owns the numbers; the env vars only override them.
_RATE_LIMIT_DEFAULTS = RateLimitPolicy()


def _int_from_env(var: str, default: int) -> int:
    return int(os.environ.get(var, default))


def _urls_from_env(var: str) -> tuple[str, ...]:
    """Comma-separated allowlist for URLs a generated reply may contain.

    Empty means the strictest reading of ADR-0002: a model-authored reply may
    name no URL at all. Deployments that legitimately hand out a link (the
    app's address, a docs page) list it here instead of having it silently
    deleted from every answer.
    """
    raw = os.environ.get(var, "")
    return tuple(part.strip() for part in raw.split(",") if part.strip())


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
    gemini_api_key: str = ""
    gemini_router_model: str = "gemini-3.8-flash"
    gemini_agent_model: str = "gemini-3.8-flash"
    database_url: str = ""
    admin_contact: str = ""
    bella_display_name: str = "Nova"
    # What a user is given when they ask for a person. Empty means nobody is
    # published; the handoff still notifies the admin contact.
    human_contact_reply: str = ""
    allowed_reply_urls: tuple[str, ...] = ()
    profile_picture_path: Path = DEFAULT_PROFILE_PICTURE_PATH
    canned_replies_path: Path = DEFAULT_CANNED_REPLIES_PATH
    knowledge_base_path: Path = DEFAULT_KNOWLEDGE_BASE_PATH
    enrollment_card_path: Path = DEFAULT_ENROLLMENT_CARD_PATH
    apostila_path: Path = DEFAULT_APOSTILA_PATH
    rate_limit_policy: RateLimitPolicy = RateLimitPolicy()
    github_token: str = ""
    inbox_path: Path = DEFAULT_INBOX_PATH
    apps_dir: Path = DEFAULT_APPS_DIR
    # Sliding Takeover Pause window (ADR 0003), reset by every human message.
    takeover_pause_seconds: int = 3600
    seat_count_refresh_seconds: int = 6 * 60 * 60
    seat_count_max_age_seconds: int = 24 * 60 * 60

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            evolution_url=os.environ["EVOLUTION_URL"],
            evolution_api_key=os.environ["EVOLUTION_API_KEY"],
            evolution_instance_id=os.environ.get(
                "EVOLUTION_INSTANCE_ID", "bella"
            ),
            bella_internal_url=os.environ["BELLA_INTERNAL_URL"],
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
            gemini_router_model=os.environ.get(
                "GEMINI_ROUTER_MODEL", cls.gemini_router_model
            ),
            gemini_agent_model=os.environ.get(
                "GEMINI_AGENT_MODEL", cls.gemini_agent_model
            ),
            database_url=os.environ["BELLA_DATABASE_URL"],
            admin_contact=os.environ["ADMIN_CONTACT"],
            bella_display_name=os.environ.get("BELLA_DISPLAY_NAME", "Nova"),
            human_contact_reply=os.environ.get("HUMAN_CONTACT_REPLY", ""),
            allowed_reply_urls=_urls_from_env("ALLOWED_REPLY_URLS"),
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
            github_token=os.environ.get("GITHUB_TOKEN", ""),
            inbox_path=_path_from_env("INBOX_PATH", DEFAULT_INBOX_PATH),
            apps_dir=_path_from_env("APPS_DIR", DEFAULT_APPS_DIR),
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
