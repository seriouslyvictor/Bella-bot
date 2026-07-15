import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    evolution_url: str
    evolution_api_key: str
    evolution_instance_id: str
    webhook_secret: str
    # Where Evolution GO can reach Bella on the internal Docker network — used
    # to build the webhook URL and the profile-picture URL registered against
    # the Evolution GO instance (see bella/scripts/). Never a public address.
    bella_internal_url: str = "http://bella:8000"
    bella_display_name: str = "Bella"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            evolution_url=os.environ.get("EVOLUTION_URL", "http://evolution-go:8080"),
            evolution_api_key=os.environ["EVOLUTION_API_KEY"],
            evolution_instance_id=os.environ["EVOLUTION_INSTANCE_ID"],
            webhook_secret=os.environ["WEBHOOK_SECRET"],
            bella_internal_url=os.environ.get("BELLA_INTERNAL_URL", "http://bella:8000"),
            bella_display_name=os.environ.get("BELLA_DISPLAY_NAME", "Bella"),
        )
