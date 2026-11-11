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
        "asanas",
        "remind",
        "moon",
        "teachers",
        "schedule",
        "classes",
        "settings",
        "help",
        "start",
    ]
    assert "language_code" not in default
    assert ru["language_code"] == "ru"
    assert all(c["description"] for c in default["commands"] + ru["commands"])
    assert default["commands"][0]["description"] != ru["commands"][0]["description"]


def test_profile_texts_come_from_the_bot_ftl_in_both_languages() -> None:
    # UI-05: English is the default; Russian is set for clients whose Telegram is in Russian.
    payloads = _tool().profile_payloads()

    assert [(method, body.get("language_code")) for method, body in payloads] == [
        ("setMyDescription", None),
        ("setMyShortDescription", None),
        ("setMyDescription", "ru"),
        ("setMyShortDescription", "ru"),
    ]
    en, en_about, ru, ru_about = (body for _, body in payloads)
    assert en["description"].startswith(
        "Tristhana is a companion for your Ashtanga practice.\n\n🧘"
    )
    assert en["description"].endswith("Guide: tristhana.app")
    assert ru["description"].startswith("Тристхана — спутник")
    assert ru["description"].endswith("tristhana.app/ru/")
    assert "\n\nЖурнал — твой." in ru["description"]  # noqa: RUF001 - blank lines inside the text survive
    assert en_about["short_description"].startswith("Your Ashtanga companion")
    assert "\n" not in ru_about["short_description"]


def test_profile_texts_fit_telegrams_limits_and_stay_public() -> None:
    for _, body in _tool().profile_payloads():
        assert len(body.get("description", "")) <= 512
        assert len(body.get("short_description", "")) <= 120
        text = (body.get("description") or body["short_description"]).lower()
        for word in ("🌸", "streak", "missed", "skipped", "серия", "пропус"):
            assert word not in text


def test_a_missing_profile_text_is_an_error_not_an_empty_profile(tmp_path: Path) -> None:
    for locale in ("en", "ru"):
        (tmp_path / locale).mkdir()
        (tmp_path / locale / "bot.ftl").write_text("bot-about = Hi\n", encoding="utf-8")

    with pytest.raises(KeyError, match="bot-description"):
        _tool().profile_payloads(tmp_path)
