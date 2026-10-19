import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

TOOL = Path(__file__).resolve().parents[3] / "tools" / "telegram" / "set_webhook.py"


def _tool() -> ModuleType:
    spec = importlib.util.spec_from_file_location("set_webhook", TOOL)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_payload_points_at_the_webhook_route_without_the_token() -> None:
    payload = _tool().webhook_payload("https://svc.run.app/", "s3cret")

    assert payload["url"] == "https://svc.run.app/telegram/webhook"
    assert payload["secret_token"] == "s3cret"
    assert payload["allowed_updates"] == ["message", "callback_query"]
    assert payload["drop_pending_updates"] is True


def test_http_errors_never_echo_the_token(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import io
    import urllib.error

    tool = _tool()
    token = "999:super-secret-token"

    def fail(request: object, timeout: float) -> object:
        url = f"https://api.telegram.org/bot{token}/setWebhook"
        raise urllib.error.HTTPError(url, 502, "Bad Gateway", {}, io.BytesIO(b"<html>"))  # type: ignore[arg-type]

    def fake_secret(name: str) -> str:
        return token if name == "telegram-bot-token" else "s"

    def fake_gcloud(*args: str) -> str:
        return "https://svc.run.app"

    monkeypatch.setattr(tool.urllib.request, "urlopen", fail)
    monkeypatch.setattr(tool, "secret", fake_secret)
    monkeypatch.setattr(tool, "gcloud", fake_gcloud)
    monkeypatch.setattr("sys.argv", ["set_webhook.py"])

    assert tool.main() == 1
    out = capsys.readouterr()
    assert token not in out.out + out.err
    assert "HTTP 502" in out.out


def test_menu_button_opens_the_mini_app() -> None:
    payload = _tool().menu_button_payload("https://tristhana.web.app")

    assert payload["menu_button"]["type"] == "web_app"
    assert payload["menu_button"]["web_app"] == {"url": "https://tristhana.web.app"}


def test_command_menu_is_localized_from_the_bot_ftl() -> None:
    default, ru = _tool().commands_payloads()

    assert [c["command"] for c in default["commands"]] == [
        "log",
        "remind",
        "moon",
        "settings",
        "help",
        "start",
    ]
    assert "language_code" not in default
    assert ru["language_code"] == "ru"
    assert all(c["description"] for c in default["commands"] + ru["commands"])
    assert default["commands"][0]["description"] != ru["commands"][0]["description"]
