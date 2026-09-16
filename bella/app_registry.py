"""Application registry and configuration for Nova."""

from dataclasses import dataclass
from pathlib import Path

DEFAULT_APP_ID = "report_generator9000"
_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_APPS_DIR = _REPO_ROOT / "content" / "apps"


@dataclass(frozen=True)
class AppConfig:
    app_id: str
    name: str
    description: str
    repo: str
    knowledge_base: str


class AppRegistry:
    def __init__(
        self,
        apps: dict[str, AppConfig],
        default_app_id: str = DEFAULT_APP_ID,
    ) -> None:
        self._apps = apps
        self._default_app_id = default_app_id

    def get_app(self, app_id: str | None = None) -> AppConfig:
        target_id = app_id or self._default_app_id
        if target_id not in self._apps:
            raise KeyError(f"Unknown application ID: {target_id}")
        return self._apps[target_id]

    def default_app(self) -> AppConfig:
        return self.get_app(self._default_app_id)

    def list_apps(self) -> list[AppConfig]:
        return list(self._apps.values())

    @classmethod
    def load_from_directory(
        cls, apps_dir: Path = DEFAULT_APPS_DIR
    ) -> "AppRegistry":
        apps: dict[str, AppConfig] = {}
        rg9000_kb_path = apps_dir / f"{DEFAULT_APP_ID}.md"
        kb_text = ""
        if rg9000_kb_path.is_file():
            kb_text = rg9000_kb_path.read_text(encoding="utf-8")

        apps[DEFAULT_APP_ID] = AppConfig(
            app_id=DEFAULT_APP_ID,
            name="Report Generator 9000",
            description="Gerador de Relatórios Técnicos Finais do SEBRAETEC",
            repo="seriouslyvictor/report_generator9000",
            knowledge_base=kb_text,
        )
        return cls(apps, default_app_id=DEFAULT_APP_ID)
