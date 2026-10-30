"""Moon screens through the real webhook (MD-03) and the Telegram notifier."""

import itertools
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods import SendMessage
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tristhana.application.ports.notifications import DeliveryStatus, MoonReminder, Recipient
from tristhana.bots.telegram.moon_callbacks import MoonCallback, decode, encode
from tristhana.bots.telegram.notifier import TelegramNotifier
from tristhana.bots.telegram.runtime import build_runtime
from tristhana.domain.moon import MoonDay, MoonDayKind, MoonPhase
from tristhana.infrastructure.i18n.fluent import FluentTranslator
from tristhana.infrastructure.seed.cities_yaml import load_cities
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
CITIES = load_cities(Path(__file__).resolve().parents[3] / "data" / "seed" / "cities.yaml")
_ids = itertools.count(90_000)
INFO = "\N{INFORMATION SOURCE}"  # the MD-04 line's lead
_METHOD = SendMessage(chat_id=1, text="x")  # what aiogram errors carry


@pytest.fixture(autouse=True)
def outbound(monkeypatch: pytest.MonkeyPatch) -> None:
    async def record(self: AiohttpSession, bot: object, method: Any, **_: object) -> bool:
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)


@pytest.fixture
def storage() -> InMemoryStorage:
    s = InMemoryStorage()
    soon = datetime.now(UTC).date() + timedelta(days=3)
    s.moon_repo.days_by_location["mysuru"] = [MoonDay(soon, MoonDayKind.PURNIMA)]
    return s


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


def _moon(client: TestClient, lang: str = "en") -> Any:
    message = {
        "message_id": 7,
        "date": 1_760_000_000,
        "chat": {"id": 42, "type": "private"},
        "from": _user(lang),
        "text": "/moon",
        "entities": [{"type": "bot_command", "offset": 0, "length": 5}],
    }
    return _post(client, {"update_id": next(_ids), "message": message})


def _tap(client: TestClient, data: str, lang: str = "en") -> Any:
    message = {
        "message_id": 9,
        "date": 1_760_000_000,
        "chat": {"id": 42, "type": "private"},
        "text": "…",
    }
    callback = {
        "id": f"cb{next(_ids)}",
        "from": _user(lang),
        "chat_instance": "ci",
        "data": data,
        "message": message,
    }
    return _post(client, {"update_id": next(_ids), "callback_query": callback})


def _texts(body: Any) -> list[str]:
    return [b["text"] for row in body["reply_markup"]["inline_keyboard"] for b in row]


def _set_zone(storage: InMemoryStorage, zone: str) -> None:
    [account] = storage.repo.accounts.values()
    storage.repo.accounts[account.id] = replace(account, timezone=zone)


def test_moon_screen_lists_days_names_the_calendar_and_asks_for_a_zone(client: TestClient) -> None:
    body = _moon(client)

    assert body["text"].startswith("🌙 Moon days · 📍 Mysuru")
    assert "🌕 Full moon (Purnima)" in body["text"]
    assert "in 3 days" in body["text"]
    assert "follow your teacher" in body["text"]
    assert "I need your time zone" in body["text"]  # no zone yet: no reminders
    assert _texts(body) == ["📍 Change city", "🔔 Reminders"]


def test_moon_screen_shows_reminders_with_a_time_label(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _moon(client)
    _set_zone(storage, "Asia/Almaty")

    body = _moon(client, "ru")

    assert "🔔 Напоминания: за неделю и за день в 19:00 Алматы (UTC+5)" in body["text"]


def test_city_picker_and_city_zone(client: TestClient, storage: InMemoryStorage) -> None:
    _moon(client)
    picker = _tap(client, "m1:c:0")
    assert _texts(picker)[0] == "✓ Mysuru"  # the default, first

    chosen = _tap(client, "m1:s:almaty")
    assert chosen["text"].startswith("🌙 Moon days · 📍 Almaty")
    assert "🕐 Time zone: 📍 Almaty" in _texts(chosen)

    zoned = _tap(client, "m1:z:almaty")
    [account] = storage.repo.accounts.values()
    assert account.timezone == "Asia/Almaty"
    assert "🔔 Reminders: 7 and 1 day before at 19:00 Almaty (UTC+5)" in zoned["text"]


def _set_home(storage: InMemoryStorage, slug: str, zone: str) -> None:
    [account] = storage.repo.accounts.values()
    storage.repo.accounts[account.id] = replace(account, home_city=slug, timezone=zone)


def test_the_home_citys_other_date_shows_under_the_day(
    client: TestClient, storage: InMemoryStorage
) -> None:
    """MD-04: a gentle info line, only where the same phase falls on another day."""
    [full] = storage.moon_repo.days_by_location["mysuru"]
    storage.moon_repo.days_by_location["astana"] = [
        MoonDay(full.date - timedelta(days=1), full.kind)
    ]
    _moon(client)
    _set_home(storage, "astana", "Asia/Almaty")

    en = _moon(client)
    ru = _moon(client, "ru")

    assert f"\n{INFO} In 📍 Astana it falls on " in en["text"]
    assert f"\n{INFO} 📍 Астана: " in ru["text"]
    assert "19:00 Astana (UTC+5)" in en["text"]  # the reminder label names the home city


def test_no_fyi_when_the_dates_match_or_no_city(
    client: TestClient, storage: InMemoryStorage
) -> None:
    [full] = storage.moon_repo.days_by_location["mysuru"]
    storage.moon_repo.days_by_location["astana"] = [full]
    _moon(client)
    without = _moon(client)
    _set_home(storage, "astana", "Asia/Almaty")

    same = _moon(client)

    assert INFO not in without["text"]
    assert INFO not in same["text"]


def test_same_as_my_city_comes_first_and_stores_the_slug(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _moon(client)
    _set_home(storage, "astana", "Asia/Almaty")

    picker = _tap(client, "m1:c:0")
    chosen = _tap(client, "m1:s:astana")
    again = _tap(client, "m1:c:0")

    assert _texts(picker)[0] == "📍 Same as my city (Astana)"
    [account] = storage.repo.accounts.values()
    assert account.moon_location == "astana"  # a snapshot, not a link
    assert chosen["text"].startswith("🌙 Moon days · 📍 Astana")
    assert "📍 Same as my city (Astana)" not in _texts(again)  # already followed


def test_reminder_settings_toggles(client: TestClient, storage: InMemoryStorage) -> None:
    _moon(client)
    _set_zone(storage, "Asia/Almaty")

    screen = _tap(client, "m1:r")
    assert _texts(screen)[:3] == ["✓ 7 days", "3 days", "✓ 1 day"]
    three = _tap(client, "m1:o:731")
    assert "7, 3 and 1 day before" in three["text"]
    morning = _tap(client, "m1:t:0700")
    assert "✓ 07:00" in _texts(morning)
    off = _tap(client, "m1:o:0")
    assert off["text"] == "🔕 Reminders are off"


def test_quick_actions_on_a_reminder(client: TestClient, storage: InMemoryStorage) -> None:
    _moon(client)
    d = (datetime.now(UTC).date() + timedelta(days=3)).strftime("%Y%m%d")

    only1 = _tap(client, f"m1:q:{d}:p:7:1")
    off = _tap(client, f"m1:q:{d}:p:7:0")

    assert only1["text"].endswith("✓ I'll only remind you the day before.")
    assert "🌕 Full moon in a week" in only1["text"]
    assert off["text"].endswith("You can turn them back on in /moon.")
    assert _texts(off)[0] == "🔔 Turn back on"
    [settings] = storage.notifications.stored.values()
    assert not settings.moon.on


@pytest.mark.parametrize(
    "data",
    [
        "m1",
        "m1:x",
        "m1:c:x",
        "m1:s:Bad Slug",
        "m1:o:2",
        "m1:o:77",
        "m1:t:2561",
        "m1:q:20261399:p:1:0",
        "m1:q:20261105:z:1:0",
        "m0:v",
    ],
)
def test_malformed_moon_callbacks(data: str) -> None:
    assert decode(data) is None


def test_every_city_callback_fits_64_bytes() -> None:
    for city in CITIES.all:
        for action in ("city", "zone"):
            data = encode(MoonCallback(action, slug=city.slug))  # type: ignore[arg-type]
            assert len(data.encode()) <= 64
            assert decode(data) == MoonCallback(action, slug=city.slug)  # type: ignore[arg-type]
    quick = MoonCallback(
        "quick", moon_date=date(2026, 11, 5), phase=MoonPhase.AMAVASYA, days_before=7, quick="off"
    )
    assert decode(encode(quick)) == quick


def _notifier(
    monkeypatch: pytest.MonkeyPatch, error: Exception | None
) -> tuple[TelegramNotifier, list[Any]]:
    from tests.fakes import (
        FixedClock,
        InMemoryAccounts,
        day_use_cases,
        moon_use_cases,
        practice_use_cases,
        remind_use_cases,
        settings_use_cases,
    )
    from tristhana.application.accounts import EnsureAccount

    runtime = build_runtime(
        TOKEN,
        EnsureAccount(InMemoryAccounts(), FixedClock()),
        day_use_cases(),
        practice_use_cases(),
        moon_use_cases(),
        remind_use_cases(),
        settings_use_cases(),
        FluentTranslator(),
    )
    sent: list[Any] = []

    async def send(self: AiohttpSession, bot: object, method: Any, **_: object) -> Any:
        sent.append(method)
        if error is not None:
            raise error
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", send)
    return TelegramNotifier(lambda: runtime, FluentTranslator()), sent


async def test_notifier_renders_the_intro_and_buttons(monkeypatch: pytest.MonkeyPatch) -> None:
    notifier, sent = _notifier(monkeypatch, None)
    reminder = MoonReminder(
        MoonDay(date(2026, 11, 5), MoonDayKind.PURNIMA),
        1,
        CITIES.default,
        intro=True,
        offsets=frozenset({7, 1}),
        today=date(2026, 11, 4),
    )

    result = await notifier.deliver(Recipient("42", "ru"), reminder)

    assert result.status is DeliveryStatus.SENT
    [method] = sent
    assert isinstance(method, SendMessage)
    assert method.chat_id == 42
    t = FluentTranslator()
    offsets = t.t("ru", "moon-offsets", code=71)  # the recipient's own offsets
    assert method.text.startswith(t.t("ru", "moon-reminder-intro", offsets=offsets))
    assert "Завтра 🌕 полнолуние" in method.text
    assert "📍 Майсур" in method.text


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (
            TelegramForbiddenError(
                method=_METHOD, message="Forbidden: bot was blocked by the user"
            ),
            DeliveryStatus.BLOCKED,
        ),  # type: ignore[arg-type]
        (
            TelegramBadRequest(method=_METHOD, message="Bad Request: chat not found"),
            DeliveryStatus.BLOCKED,
        ),  # type: ignore[arg-type]
        (
            TelegramRetryAfter(method=_METHOD, message="Too Many Requests", retry_after=7),
            DeliveryStatus.RETRY_AFTER,
        ),  # type: ignore[arg-type]
        (
            TelegramBadRequest(method=_METHOD, message="Bad Request: message is too long"),
            DeliveryStatus.FAILED,
        ),  # type: ignore[arg-type]
        (TimeoutError(), DeliveryStatus.FAILED),
    ],
)
async def test_notifier_maps_telegram_errors(
    monkeypatch: pytest.MonkeyPatch, error: Exception, status: DeliveryStatus
) -> None:
    notifier, _ = _notifier(monkeypatch, error)
    reminder = MoonReminder(
        MoonDay(date(2026, 11, 5), MoonDayKind.PURNIMA),
        7,
        CITIES.default,
        intro=False,
        offsets=frozenset({7, 1}),
        today=date(2026, 10, 29),
    )

    result = await notifier.deliver(Recipient("42", "en"), reminder)

    assert result.status is status
