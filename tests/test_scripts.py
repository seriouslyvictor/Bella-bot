"""Unit tests for the deploy-time scripts (see bella/scripts/).

These never touch the network: bella.scripts._client.post is monkeypatched
to a recorder, so the assertions are about URL/payload construction — in
particular that registration matches bella/app.py's fixed `/webhook` route.

The _client tests at the bottom are the exception: they drive the real post()
through a mock transport, because the header it builds is the thing that
actually broke in production (a 401 from sending the wrong kind of key).
"""

from typing import Any

import httpx
import pytest

from bella.config import Settings
from bella.scripts import register_webhook, set_presentation
from bella.scripts._client import post


class RecordingPost:
    """Stands in for bella.scripts._client.post, echoing back the shape
    Evolution GO really returns (it reflects webhookUrl straight back)."""

    def __init__(self) -> None:
        self.calls: list[tuple[Settings, str, dict[str, Any]]] = []

    def __call__(self, settings: Settings, path: str, json: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((settings, path, json))
        echoed = {"eventString": "MESSAGE", "jid": "5511999999999@s.whatsapp.net"}
        if "webhookUrl" in json:
            echoed["webhookUrl"] = json["webhookUrl"]
        return {"message": "success", "data": echoed}


def make_settings() -> Settings:
    return Settings(
        evolution_url="http://evolution-go:8080",
        # Named for the distinction that matters: Evolution GO's Auth
        # middleware resolves this to an instance by token lookup, so the
        # global key would 401 here.
        evolution_api_key="the-instance-token",
        evolution_instance_id="unused-in-tests",
        bella_internal_url="http://bella:8000",
        bella_display_name="Bella",
    )


def test_register_webhook_uses_fixed_webhook_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = RecordingPost()
    monkeypatch.setattr(register_webhook, "post", recorder)
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: make_settings()))

    register_webhook.main()

    assert len(recorder.calls) == 1
    _, path, body = recorder.calls[0]
    assert path == "/instance/connect"
    assert body["webhookUrl"] == "http://bella:8000/webhook"


def test_register_webhook_prints_fixed_webhook_url(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(register_webhook, "post", RecordingPost())
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: make_settings()))

    register_webhook.main()

    assert "Registering webhook: http://bella:8000/webhook" in capsys.readouterr().out


def test_register_webhook_fails_loudly_when_evolution_disagrees(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def wrong_url(settings: Settings, path: str, json: dict[str, Any]) -> dict[str, Any]:
        return {"data": {"webhookUrl": "http://somewhere-else:8000/webhook/other"}}

    monkeypatch.setattr(register_webhook, "post", wrong_url)
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: make_settings()))

    with pytest.raises(SystemExit):
        register_webhook.main()

    assert "MISMATCH" in capsys.readouterr().out


def test_set_presentation_sets_picture_then_name(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = RecordingPost()
    monkeypatch.setattr(set_presentation, "post", recorder)
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: make_settings()))

    set_presentation.main()

    assert len(recorder.calls) == 2
    _, picture_path, picture_body = recorder.calls[0]
    assert picture_path == "/user/profilePicture"
    assert picture_body == {"image": "http://bella:8000/assets/whatsapp-profile-picture.jpg"}

    _, name_path, name_body = recorder.calls[1]
    assert name_path == "/user/profileName"
    assert name_body == {"name": "Bella"}


def _mock_client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_post_authenticates_with_the_instance_token_in_the_apikey_header() -> None:
    # /instance/connect and /user/* are Auth-middleware routes: the apikey
    # header must carry the instance token, never GLOBAL_API_KEY.
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"message": "success"})

    post(make_settings(), "/instance/connect", {"webhookUrl": "x"}, client=_mock_client(handler))

    assert seen[0].headers["apikey"] == "the-instance-token"
    assert str(seen[0].url) == "http://evolution-go:8080/instance/connect"


def test_post_explains_a_401_instead_of_leaving_a_bare_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "not authorized"})

    with pytest.raises(RuntimeError, match="INSTANCE token"):
        post(make_settings(), "/instance/connect", {}, client=_mock_client(handler))


def test_post_still_raises_on_other_http_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with pytest.raises(httpx.HTTPStatusError):
        post(make_settings(), "/instance/connect", {}, client=_mock_client(handler))
