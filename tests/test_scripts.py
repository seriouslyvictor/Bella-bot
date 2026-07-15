"""Unit tests for the deploy-time scripts (see bella/scripts/).

These never touch the network: bella.scripts._client.post is monkeypatched
to a recorder, so the assertions are about URL/payload construction — in
particular that the webhook secret lands in the path, not the body or a
header, matching bella/app.py's `/webhook/{secret}` contract.
"""

from typing import Any

import pytest

from bella.config import Settings
from bella.scripts import register_webhook, set_presentation


class RecordingPost:
    def __init__(self) -> None:
        self.calls: list[tuple[Settings, str, dict[str, Any]]] = []

    def __call__(self, settings: Settings, path: str, json: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((settings, path, json))
        return {"message": "success"}


def make_settings() -> Settings:
    return Settings(
        evolution_url="http://evolution-go:8080",
        evolution_api_key="unused-in-tests",
        evolution_instance_id="unused-in-tests",
        webhook_secret="s3cr3t",
        bella_internal_url="http://bella:8000",
        bella_display_name="Bella",
    )


def test_register_webhook_puts_secret_in_the_path_not_the_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = RecordingPost()
    monkeypatch.setattr(register_webhook, "post", recorder)
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: make_settings()))

    register_webhook.main()

    assert len(recorder.calls) == 1
    _, path, body = recorder.calls[0]
    assert path == "/instance/connect"
    assert body["webhookUrl"] == "http://bella:8000/webhook/s3cr3t"
    assert "s3cr3t" not in str({k: v for k, v in body.items() if k != "webhookUrl"})


def test_set_presentation_sets_picture_then_name(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = RecordingPost()
    monkeypatch.setattr(set_presentation, "post", recorder)
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: make_settings()))

    set_presentation.main()

    assert len(recorder.calls) == 2
    _, picture_path, picture_body = recorder.calls[0]
    assert picture_path == "/user/profilePicture"
    assert picture_body == {"image": "http://bella:8000/assets/whatsapp-profile-picture.png"}

    _, name_path, name_body = recorder.calls[1]
    assert name_path == "/user/profileName"
    assert name_body == {"name": "Bella"}
