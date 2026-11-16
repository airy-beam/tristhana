"""`/settings` through the real webhook (ID-06, UI-06 §2 G0-G3): five rows, each label
carrying its value, rendered from the loaded account; the language picker, Reminders and More
behind them; and the old screen's buttons, which still write and land on a living screen."""

import itertools
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.bots.statements import Statements
from tests.fakes import InMemoryStorage
from tristhana.bots.telegram.settings_callbacks import SettingsCallback, decode, encode
from tristhana.main import create_app
from tristhana.settings import Settings

MENU = ["☰ Menu"]
BACK = ["‹ Back"]  # noqa: RUF001
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


@pytest.fixture
def statements(monkeypatch: pytest.MonkeyPatch, storage: InMemoryStorage) -> Statements:
    return Statements(monkeypatch, storage)


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


def _where(body: Any) -> dict[str, str]:
    """Label → where the button leads: callback data or a Mini App URL."""
    return {
        b["text"]: b.get("callback_data") or b["web_app"]["url"]
        for row in body["reply_markup"]["inline_keyboard"]
        for b in row
    }


def _me(client: TestClient, storage: InMemoryStorage, lang: str = "en") -> Any:
    _command(client, "/settings", lang)
    [account] = storage.repo.accounts.values()
    return account


def test_settings_is_five_rows_each_with_its_value(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage)

    body = _command(client, "/settings")

    assert body["text"] == "⚙️ Settings"
    assert _rows(body) == [
        ["🗣 Language: As in Telegram"],
        ["🏙 My city? 🕐 not known yet"],  # Q314: the row says the zone is missing
        ["😌 Day off: not chosen"],
        ["🔔 Reminders"],
        ["More…"],
        MENU,
    ]
    assert list(_where(body).values()) == ["s1:lp", "s1:cp:0", "s1:o", "s1:r", "s1:m", "w1:m"]
    assert _tap(client, "s1:v")["text"] == body["text"]


def test_settings_in_russian(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage, "ru")
    storage.repo.accounts[me.id] = replace(me, home_city="astana", timezone=ZONE)

    body = _command(client, "/settings", "ru")

    assert body["text"] == "⚙️ Настройки"
    assert _rows(body) == [
        ["🗣 Язык: Как в Telegram"],
        ["🏙 Мой город: Астана"],  # ADR-0044: my own city carries no offset
        ["😌 Выходной: не выбран"],
        ["🔔 Напоминания"],
        ["Ещё…"],
        ["☰ Меню"],
    ]


def test_settings_and_more_read_nothing_and_reminders_reads_once(
    client: TestClient, storage: InMemoryStorage, statements: Statements
) -> None:
    """UI-06 §2, the "After" column: G0 0 (it cost one), G1 0, G2 1, G3 0."""
    _me(client, storage)
    cost: dict[str, int] = {}

    for name, send in {
        "/settings": lambda: _command(client, "/settings"),
        "s1:v": lambda: _tap(client, "s1:v"),
        "s1:lp": lambda: _tap(client, "s1:lp"),
        "s1:r": lambda: _tap(client, "s1:r"),
        "s1:m": lambda: _tap(client, "s1:m"),
    }.items():
        statements.clear()
        send()
        cost[name] = statements.count

    assert cost == {"/settings": 0, "s1:v": 0, "s1:lp": 0, "s1:r": 1, "s1:m": 0}


def test_the_language_picker_marks_the_choice(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage)

    auto = _tap(client, "s1:lp")
    _tap(client, "s1:l:ru")
    chosen = _tap(client, "s1:lp")

    assert auto["text"] == "🗣 Which language shall I use?"
    assert _rows(auto) == [["✓ As in Telegram"], ["English"], ["Русский"], BACK]
    assert list(_where(auto).values()) == ["s1:l:a", "s1:l:en", "s1:l:ru", "s1:v"]
    assert _rows(chosen)[:3] == [["Как в Telegram"], ["English"], ["✓ Русский"]]


def test_language_tap_switches_at_once_and_sticks(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)

    ru = _tap(client, "s1:l:ru")
    again = _command(client, "/settings", "en")  # Telegram still says English
    auto = _tap(client, "s1:l:a")

    assert ru["text"] == "⚙️ Настройки"  # the five rows again, in the new language
    assert _rows(ru)[0] == ["🗣 Язык: Русский"]
    assert again["text"] == "⚙️ Настройки"  # the choice sticks
    assert auto["text"] == "⚙️ Settings"
    assert _rows(auto)[0] == ["🗣 Language: As in Telegram"]
    assert storage.repo.accounts[me.id].locale_custom is False


def test_reminders_shows_both_and_the_quiet_hours(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    storage.repo.accounts[me.id] = replace(me, home_city="astana", timezone=ZONE)

    body = _tap(client, "s1:r")

    lines = body["text"].split("\n")
    assert lines[0] == "🔔 Reminders"
    assert len(lines) == 4  # the title, the practice reminder, moon reminders, quiet hours
    assert lines[3] == "🔕 Quiet hours 22:00–07:00 · at most 3 messages a day"  # noqa: RUF001
    assert _rows(body) == [["🧘 Practice reminder"], ["🌙 Moon reminders"], BACK]
    assert list(_where(body).values()) == ["r1:v", "m1:r", "s1:v"]


def test_more_holds_what_is_set_once(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage)

    body = _tap(client, "s1:m")

    assert body["text"] == "⚙️ More settings\n🌙 Moon days: 📍 Mysuru"
    assert _where(body) == {
        "🌙 Moon days": "m1:v",
        "🌸 Hide “Ladies' holiday”": "s1:h:1",
        "✨ Hide “How do you feel?”": "s1:k:0",
        "📦 My data": "x1:o",
        "‹ Back": "s1:v",  # noqa: RUF001
    }


def test_more_links_to_the_app_when_there_is_one(storage: InMemoryStorage) -> None:
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
        miniapp_url="https://tristhana.web.app",
    )
    with TestClient(create_app(settings, storage)) as client:
        body = _tap(client, "s1:m")
        first = _command(client, "/settings")

    assert _where(body)["⚙️ More in the app"] == "https://tristhana.web.app"
    assert _rows(body)[-1] == BACK
    assert "⚙️ More in the app" not in _texts(first)  # it left the first screen


@pytest.mark.parametrize(
    ("data", "field", "value", "label"),
    [
        ("s1:h:1", "hide_ladies", True, "🌸 Show “Ladies' holiday”"),
        ("s1:h:0", "hide_ladies", False, "🌸 Hide “Ladies' holiday”"),
        ("s1:k:0", "offer_check_in", False, "✨ Show “How do you feel?”"),
        ("s1:k:1", "offer_check_in", True, "✨ Hide “How do you feel?”"),
    ],
)
def test_an_old_switch_button_writes_and_shows_more(
    client: TestClient, storage: InMemoryStorage, data: str, field: str, value: bool, label: str
) -> None:
    """UI-06 §5: these rows sat on the old /settings screen; they now live under More."""
    me = _me(client, storage)

    body = _tap(client, data)

    assert getattr(storage.repo.accounts[me.id], field) is value
    assert body["text"].startswith("⚙️ More settings")
    assert label in _texts(body)


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
    assert chosen["text"] == "⚙️ Settings"
    assert _rows(chosen)[1] == [f"🏙 My city: {name}"]  # ADR-0044: my own city, no offset


def test_old_zone_buttons_still_work(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)

    page = _tap(client, "s1:zp:1")
    chosen = _tap(client, "s1:z:moscow")

    assert "Which city do you live in?" in page["text"]
    assert storage.repo.accounts[me.id].home_city == "moscow"
    assert ["🏙 My city: Moscow"] in _rows(chosen)


def test_the_city_nudge_is_gone(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    storage.repo.accounts[me.id] = replace(me, timezone=ZONE)

    body = _command(client, "/settings")

    assert "Not now" not in _texts(body)
    assert ["🏙 My city? 🕐 Almaty (UTC+5)"] in _rows(body)
    assert not [data for data in _where(body).values() if data == "s1:n"]


def test_an_old_not_now_button_writes_and_shows_settings(
    client: TestClient, storage: InMemoryStorage
) -> None:
    """UI-06 §5: the nudge's button, still under an old message."""
    me = _me(client, storage)
    storage.repo.accounts[me.id] = replace(me, timezone=ZONE)

    body = _tap(client, "s1:n")

    assert storage.repo.accounts[me.id].home_city == "-"
    assert storage.repo.accounts[me.id].timezone == ZONE
    assert body["text"] == "⚙️ Settings"
    assert ["🕐 My time: Almaty (UTC+5)"] in _rows(body)


def test_a_stale_not_now_keeps_a_city_chosen_since(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    _tap(client, "s1:c:astana")  # e.g. in the app, after the nudge was shown here

    body = _tap(client, "s1:n")  # the old message's button

    assert storage.repo.accounts[me.id].home_city == "astana"
    assert ["🏙 My city: Astana"] in _rows(body)


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
    assert ["🕐 My time: UTC"] in _rows(body)
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

    first = _command(client, "/settings")
    reminders = _tap(client, "s1:r")

    assert ["🏙 My city: Astana"] in _rows(first)
    assert "19:00 Astana" in reminders["text"]  # the reader's own zone: no offset (ADR-0044)
    assert "Almaty" not in f"{_texts(first)} {reminders['text']}"


def test_links_both_ways(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage)

    reminders = _tap(client, "s1:r")

    assert ["🧘 Practice reminder"] in _rows(reminders)
    assert "⚙️ Settings" in _texts(_tap(client, "m1:r"))
    assert "⚙️ Settings" in _texts(_tap(client, "r1:v"))


@pytest.mark.parametrize(
    "data",
    [
        *("s1", "s1:x", "s1:l:de", "s1:zp:x", "s1:cp:99", "s1:z:Bad", "s1:c:Bad", "s1:u:1"),
        *("s0:v", "s1:lp:1", "s1:r:1", "s1:m:x", "s1:l"),
    ],
)
def test_malformed_settings_callbacks(data: str) -> None:
    assert decode(data) is None


def test_every_settings_callback_fits_64_bytes() -> None:
    from tristhana.infrastructure.seed.cities_yaml import load_cities

    cities = load_cities(Path(__file__).resolve().parents[3] / "data" / "seed" / "cities.yaml")
    for cb in [
        SettingsCallback("view"),
        SettingsCallback("language_pick"),
        SettingsCallback("reminders"),
        SettingsCallback("more"),
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
    for new in ("language_pick", "reminders", "more"):  # UI-06 §2: at most 22 bytes
        assert len(encode(SettingsCallback(new)).encode()) <= 22  # type: ignore[arg-type]


def test_no_quiet_hours_reads_as_such(client: TestClient, storage: InMemoryStorage) -> None:
    from datetime import time

    from tristhana.domain.notifications import DEFAULTS, QuietHours

    me = _me(client, storage)
    storage.notifications.stored[me.id] = replace(DEFAULTS, quiet=QuietHours(time(0), time(0)))

    body = _tap(client, "s1:r")

    assert "🔕 No quiet hours · at most 3 messages a day" in body["text"]
