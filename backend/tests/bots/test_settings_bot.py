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
    assert "🏙 My city: not chosen yet. Reminders start once it's set." in body["text"]
    assert "Pick your city if you like: times will then show its name." in body["text"]  # nudge
    assert "🌙 Moon days: 📍 Mysuru" in body["text"]
    assert "🔕 Quiet hours 22:00–07:00 · at most 3 messages a day" in body["text"]  # noqa: RUF001
    assert _rows(body)[:3] == [
        ["✓ As in Telegram", "English", "Русский"],
        ["🏙 My city", "😌 Day off"],
        ["Not now"],
    ]
    assert "😌 Day off: not chosen" in body["text"]


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


def _all_picker_texts(client: TestClient) -> list[str]:
    """Every button text on all pages of the city picker (34 cities, 12 per page)."""
    texts: list[str] = []
    for page in range(3):
        texts += _texts(_tap(client, f"s1:cp:{page}"))
    return texts


def test_city_picker_lists_every_moon_day_city(
    client: TestClient, storage: InMemoryStorage
) -> None:
    """Users asked for Moscow; Krasnaya Polyana used to stand in for its whole zone."""
    from tristhana.infrastructure.seed.cities_yaml import load_cities

    cities = load_cities(Path(__file__).resolve().parents[3] / "data" / "seed" / "cities.yaml")
    _me(client, storage)

    texts = " | ".join(_all_picker_texts(client))

    for city in cities.all:
        assert city.name_en in texts, city.slug
    assert "📍 My city isn't listed" in texts
    assert "🌐 UTC" in texts


@pytest.mark.parametrize(
    ("slug", "name", "zone"), [("astana", "Astana", ZONE), ("sochi", "Sochi", "Europe/Moscow")]
)
def test_the_picked_city_is_the_marked_one(
    client: TestClient, storage: InMemoryStorage, slug: str, name: str, zone: str
) -> None:
    """The bug: Astana marked Almaty, Sochi marked Moscow (only the zone was stored)."""
    me = _me(client, storage)

    chosen = _tap(client, f"s1:c:{slug}")
    marked = [t for t in _all_picker_texts(client) if t.startswith("✓ ")]

    assert marked == [f"✓ {name}"]
    assert (storage.repo.accounts[me.id].home_city, storage.repo.accounts[me.id].timezone) == (
        slug,
        zone,
    )
    assert f"🏙 My city: {name} (UTC+" in chosen["text"]
    assert "Pick your city" not in chosen["text"]  # the nudge is answered
    assert ["Not now"] not in _rows(chosen)


def test_old_zone_buttons_still_work(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)

    page = _tap(client, "s1:zp:1")
    chosen = _tap(client, "s1:z:moscow")

    assert "Which city do you live in?" in page["text"]
    assert storage.repo.accounts[me.id].home_city == "moscow"
    assert "🏙 My city: Moscow (UTC+3)" in chosen["text"]


def test_not_now_ends_the_nudge_and_keeps_the_zone(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    storage.repo.accounts[me.id] = replace(me, timezone=ZONE)

    body = _tap(client, "s1:n")

    assert storage.repo.accounts[me.id].home_city == "-"
    assert storage.repo.accounts[me.id].timezone == ZONE
    assert "🏙 My city: not chosen · 🕐 Almaty (UTC+5)" in body["text"]
    assert "Pick your city" not in body["text"]


def test_a_stale_not_now_keeps_a_city_chosen_since(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    _tap(client, "s1:c:astana")  # e.g. in the app, after the nudge was shown here

    body = _tap(client, "s1:n")  # the old message's button

    assert storage.repo.accounts[me.id].home_city == "astana"
    assert "🏙 My city: Astana (UTC+5)" in body["text"]


def test_the_picker_marks_no_city_outside_its_zone(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    # A stale write left a city with another zone: the status line and the mark agree.
    storage.repo.accounts[me.id] = replace(me, home_city="astana", timezone="Asia/Bangkok")

    marked = [t for t in _all_picker_texts(client) if t.startswith("✓ ")]

    assert not any("Astana" in t for t in marked)


def test_utc_clears_the_city(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _tap(client, "s1:c:astana")

    body = _tap(client, "s1:u")
    marked = [t for t in _texts(_tap(client, "s1:cp:0")) if t.startswith("✓ ")]

    assert (storage.repo.accounts[me.id].home_city, storage.repo.accounts[me.id].timezone) == (
        "-",
        "UTC",
    )
    assert "🕐 UTC" in body["text"]
    assert marked == ["✓ 🌐 UTC"]


def test_not_listed_asks_for_a_location_in_a_new_message(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)

    body = _tap(client, "s1:c:-")

    assert body["method"] == "sendMessage"
    assert body["text"].startswith("Send your location once")
    [[share]] = body["reply_markup"]["keyboard"]
    assert share == {"text": "📍 Send my location", "request_location": True}
    assert body["reply_markup"]["one_time_keyboard"] is True
    assert storage.repo.accounts[me.id].home_city is None  # nothing is written yet


def _location(client: TestClient, **extra: Any) -> Any:
    message = {
        "message_id": 11,
        "date": 1_760_000_000,
        "chat": {"id": 42, "type": "private"},
        "from": _user("en"),
        "location": {"latitude": 13.7563, "longitude": 100.5018} | extra,
    }
    return _post(client, {"update_id": next(_ids), "message": message})


def test_a_shared_location_sets_the_zone_only(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _tap(client, "s1:c:astana")

    body = _location(client)

    account = storage.repo.accounts[me.id]
    assert (account.timezone, account.home_city) == ("Asia/Bangkok", "-")
    assert (
        body["text"]
        == "🕐 Done: your time zone is Bangkok (UTC+7). You can change it in /settings."
    )
    assert body["reply_markup"] == {"remove_keyboard": True}


def test_a_live_location_is_not_an_answer(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)

    body = _location(client, live_period=900)

    assert body is None
    assert storage.repo.accounts[me.id].timezone is None


def test_a_forwarded_location_is_not_an_answer(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)

    message = {
        "message_id": 12,
        "date": 1_760_000_000,
        "chat": {"id": 42, "type": "private"},
        "from": _user("en"),
        "forward_origin": {"type": "hidden_user", "date": 1_760_000_000, "sender_user_name": "X"},
        "location": {"latitude": 13.7563, "longitude": 100.5018},
    }
    body = _post(client, {"update_id": next(_ids), "message": message})

    assert body is None
    assert storage.repo.accounts[me.id].timezone is None


def test_a_venue_is_not_an_answer(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)

    where = {"latitude": 13.7563, "longitude": 100.5018}
    message = {
        "message_id": 13,
        "date": 1_760_000_000,
        "chat": {"id": 42, "type": "private"},
        "from": _user("en"),
        "location": where,
        "venue": {"location": where, "title": "Café", "address": "Sukhumvit"},
    }
    _post(client, {"update_id": next(_ids), "message": message})

    assert storage.repo.accounts[me.id].timezone is None


def test_a_location_at_sea_writes_nothing(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    message = {
        "message_id": 11,
        "date": 1_760_000_000,
        "chat": {"id": 42, "type": "private"},
        "from": _user("en"),
        "location": {"latitude": 0.0, "longitude": -30.0},
    }

    body = _post(client, {"update_id": next(_ids), "message": message})

    assert body["text"].startswith("I couldn't find a time zone there.")
    assert storage.repo.accounts[me.id].timezone is None


def test_the_time_labels_name_the_home_city(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage)
    _tap(client, "s1:c:astana")

    body = _command(client, "/settings")

    assert "Almaty (UTC+5)" not in body["text"]
    assert "Astana (UTC+5)" in body["text"]


def test_links_both_ways(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage)

    settings = _command(client, "/settings")

    assert ["🧘 Practice reminder"] in _rows(settings)
    assert "⚙️ Settings" in _texts(_tap(client, "m1:r"))
    assert "⚙️ Settings" in _texts(_tap(client, "r1:v"))


@pytest.mark.parametrize(
    "data",
    ["s1", "s1:x", "s1:l:de", "s1:zp:x", "s1:cp:99", "s1:z:Bad", "s1:c:Bad", "s1:u:1", "s0:v"],
)
def test_malformed_settings_callbacks(data: str) -> None:
    assert decode(data) is None


def test_every_settings_callback_fits_64_bytes() -> None:
    from tristhana.infrastructure.seed.cities_yaml import load_cities

    cities = load_cities(Path(__file__).resolve().parents[3] / "data" / "seed" / "cities.yaml")
    for cb in [
        SettingsCallback("view"),
        SettingsCallback("language"),
        SettingsCallback("language", locale="ru"),
        SettingsCallback("cities", page=2),
        SettingsCallback("unlisted"),
        SettingsCallback("utc"),
        SettingsCallback("not_now"),
        *(SettingsCallback("city", slug=c.slug) for c in cities.all),
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
