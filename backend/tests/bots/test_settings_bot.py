"""`/settings` through the real webhook (ID-06)."""

import itertools
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tristhana.bots.telegram.settings_callbacks import SettingsCallback, decode, encode
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
ZONE = "Asia/Almaty"
_ids = itertools.count(97_000)


@pytest.fixture(autouse=True)
def outbound(monkeypatch: pytest.MonkeyPatch) -> None:
    async def record(self: AiohttpSession, bot: object, method: Any, **_: object) -> bool:
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def client(storage: InMemoryStorage) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
    )
    with TestClient(create_app(settings, storage)) as c:
        yield c


def _post(client: TestClient, update: dict[str, Any]) -> Any:
    response = client.post(
        "/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}
    )
    assert response.status_code == 200
    return response.json() if response.content else None


def _user(lang: str) -> dict[str, Any]:
    return {"id": 42, "is_bot": False, "first_name": "Ash", "language_code": lang}


def _command(client: TestClient, text: str, lang: str = "en") -> Any:
    message = {
        "message_id": 7,
        "date": 1_760_000_000,
        "chat": {"id": 42, "type": "private"},
        "from": _user(lang),
        "text": text,
        "entities": [{"type": "bot_command", "offset": 0, "length": len(text)}],
    }
    return _post(client, {"update_id": next(_ids), "message": message})


def _tap(client: TestClient, data: str, lang: str = "en") -> Any:
    message = {"message_id": 9, "date": 1_760_000_000, "chat": {"id": 42, "type": "private"}}
    callback = {
        "id": f"cb{next(_ids)}",
        "from": _user(lang),
        "chat_instance": "ci",
        "data": data,
        "message": message | {"text": "…"},
    }
    return _post(client, {"update_id": next(_ids), "callback_query": callback})


def _texts(body: Any) -> list[str]:
    return [b["text"] for row in body["reply_markup"]["inline_keyboard"] for b in row]


def _rows(body: Any) -> list[list[str]]:
    return [[b["text"] for b in row] for row in body["reply_markup"]["inline_keyboard"]]


def _me(client: TestClient, storage: InMemoryStorage, lang: str = "en") -> Any:
    _command(client, "/settings", lang)
    [account] = storage.repo.accounts.values()
    return account


def test_settings_screen_without_a_zone(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage)

    body = _command(client, "/settings")

    assert body["text"].startswith("⚙️ Settings\n🗣 Language: As in Telegram")
    assert "🕐 Time zone: not set yet" in body["text"]
    assert "🌙 Moon days: 📍 Mysuru" in body["text"]
    assert "🔕 Quiet hours 22:00–07:00 · at most 3 messages a day" in body["text"]  # noqa: RUF001
    assert _rows(body)[:2] == [["✓ As in Telegram", "English", "Русский"], ["🕐 Time zone"]]


def test_language_tap_switches_at_once_and_sticks(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)

    ru = _tap(client, "s1:l:ru")
    again = _command(client, "/settings", "en")  # Telegram still says English
    auto = _tap(client, "s1:l:a")

    assert ru["text"].startswith("⚙️ Настройки\n🗣 Язык: Русский")
    assert again["text"].startswith("⚙️ Настройки")  # the choice sticks
    assert auto["text"].startswith("⚙️ Settings\n🗣 Language: As in Telegram")
    assert storage.repo.accounts[me.id].locale_custom is False


def test_zone_picker_marks_and_sets_a_zone(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    storage.repo.accounts[me.id] = replace(me, timezone="Asia/Almaty")

    picker = _tap(client, "s1:zp:0")
    chosen = _tap(client, "s1:z:bangkok")

    assert "✓ Almaty" in _texts(picker)
    assert "Kazan" not in _texts(picker) + _texts(_tap(client, "s1:zp:1"))  # Moscow stands for it
    assert storage.repo.accounts[me.id].timezone == "Asia/Bangkok"
    assert "🕐 Time zone: Bangkok (UTC+7)" in chosen["text"]


def test_links_both_ways(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage)

    settings = _command(client, "/settings")

    assert ["🧘 Practice reminder"] in _rows(settings)
    assert "⚙️ Settings" in _texts(_tap(client, "m1:r"))
    assert "⚙️ Settings" in _texts(_tap(client, "r1:v"))


@pytest.mark.parametrize("data", ["s1", "s1:x", "s1:l:de", "s1:zp:x", "s1:z:Bad", "s0:v"])
def test_malformed_settings_callbacks(data: str) -> None:
    assert decode(data) is None


def test_every_settings_callback_fits_64_bytes() -> None:
    from tristhana.infrastructure.seed.cities_yaml import load_cities

    cities = load_cities(Path(__file__).resolve().parents[3] / "data" / "seed" / "cities.yaml")
    for cb in [
        SettingsCallback("view"),
        SettingsCallback("language"),
        SettingsCallback("language", locale="ru"),
        SettingsCallback("zones", page=2),
        *(SettingsCallback("zone", slug=c.slug) for c in cities.all),
    ]:
        data = encode(cb)
        assert len(data.encode()) <= 64
        assert decode(data) == cb


def test_no_quiet_hours_reads_as_such(client: TestClient, storage: InMemoryStorage) -> None:
    from datetime import time

    from tristhana.domain.notifications import DEFAULTS, QuietHours

    me = _me(client, storage)
    storage.notifications.stored[me.id] = replace(DEFAULTS, quiet=QuietHours(time(0), time(0)))

    body = _command(client, "/settings")

    assert "🔕 No quiet hours · at most 3 messages a day" in body["text"]
