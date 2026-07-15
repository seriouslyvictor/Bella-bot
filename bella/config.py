import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    evolution_url: str
    evolution_api_key: str
    evolution_instance_id: str
    webhook_secret: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            evolution_url=os.environ.get("EVOLUTION_URL", "http://evolution-go:8080"),
            evolution_api_key=os.environ["EVOLUTION_API_KEY"],
            evolution_instance_id=os.environ["EVOLUTION_INSTANCE_ID"],
            webhook_secret=os.environ["WEBHOOK_SECRET"],
        )
