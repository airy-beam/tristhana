"""The weekly day off in the bot (PR-09): /settings and /remind pickers, the one-time
question, auto-rest notes on day screens and /start, and the callback codecs."""

import itertools
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tristhana.application.ports.notifications import PracticeReminder
from tristhana.bots.telegram import remind_callbacks as rcb
from tristhana.bots.telegram import settings_callbacks as scb
from tristhana.bots.telegram.remind import reminder_screen
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.notifications import DEFAULTS
from tristhana.domain.rest_days import DayOff
from tristhana.infrastructure.i18n.fluent import FluentTranslator
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
ZONE = "Asia/Almaty"
_ids = itertools.count(95_000)


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


def _today() -> date:
    return datetime.now(UTC).astimezone(ZoneInfo(ZONE)).date()


def _ymd(day: date) -> str:
    return day.strftime("%Y%m%d")


def _me(client: TestClient, storage: InMemoryStorage, lang: str = "en") -> Any:
    _command(client, "/settings", lang)
    [account] = storage.repo.accounts.values()
    storage.repo.accounts[account.id] = replace(account, timezone=ZONE)
    return storage.repo.accounts[account.id]


def _set_off(storage: InMemoryStorage, days: frozenset[int] | None) -> None:
    [account] = storage.repo.accounts.values()
    storage.repo.accounts[account.id] = replace(account, day_off=DayOff(days))


@pytest.mark.parametrize(
    ("days", "line"),
    [
        (None, "😌 Day off: not chosen"),
        (frozenset[int](), "😌 No fixed day off"),
        (frozenset({6}), "😌 Day off: Saturday"),
    ],
)
def test_settings_line_for_each_state(
    client: TestClient, storage: InMemoryStorage, days: frozenset[int] | None, line: str
) -> None:
    _me(client, storage)
    _set_off(storage, days)
    assert line in _command(client, "/settings")["text"]


def test_russian_weekday_is_lowercase_mid_line(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage, "ru")
    _set_off(storage, frozenset({6}))
    assert "😌 Выходной: суббота" in _command(client, "/settings", "ru")["text"]


def test_settings_picker_sets_the_day_off_and_returns(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage)
    picker = _tap(client, "s1:o")
    assert picker["text"].startswith("😌 Which day is your weekly day off?")
    assert "Past weeks show it too." in picker["text"]
    assert _rows(picker) == [
        ["Saturday", "Sunday"],
        ["Monday", "Tuesday", "Wednesday"],
        ["Thursday", "Friday"],
        ["No fixed day off"],
        ["⚙️ Settings"],
    ]
    saved = _tap(client, "s1:o:7")
    assert "😌 Day off: Sunday" in saved["text"]
    [account] = storage.repo.accounts.values()
    assert account.day_off.days == frozenset({7})
    assert account.day_off.before is None  # the first choice: all history
    again = _tap(client, "s1:o")
    assert "✓ Sunday" in _texts(again)
    assert "A change applies from today" in again["text"]


def test_custom_reminder_days_reset_shows_the_follow_note(
    client: TestClient, storage: InMemoryStorage
) -> None:
    account = _me(client, storage)
    storage.notifications.stored[account.id] = replace(
        DEFAULTS, practice=replace(DEFAULTS.practice, days=frozenset({1, 3, 5}))
    )
    saved = _tap(client, "s1:o:6")
    assert saved["text"].startswith("Reminder days now follow your day off.")
    assert _rows(saved)[0] == ["✏️ Reminder days"]


def test_question_yes_sets_the_day_off_and_hides_it(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage)
    answered = _tap(client, "r1:d:6")
    assert "weekly day off?" not in answered["text"]
    assert "✓ Day off: Sat" in _texts(answered)


def test_question_names_the_skipped_day_when_reminders_are_on(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage)
    on = _tap(client, "r1:o:1")
    asked = "😌 Practice reminders don't come on Saturdays. Is that your weekly day off?"
    assert asked in on["text"]


def test_question_for_a_weekday_has_no_weekend_alternative(
    client: TestClient, storage: InMemoryStorage
) -> None:
    account = _me(client, storage)
    storage.notifications.stored[account.id] = replace(
        DEFAULTS, practice=replace(DEFAULTS.practice, days=frozenset({1, 2, 3, 4, 6, 7}))
    )
    body = _command(client, "/remind")
    assert "Is Friday your weekly day off?" in body["text"]
    assert _rows(body)[:2] == [["Yes"], ["Other…", "Not now"]]


def test_not_now_hides_the_question_for_good(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage)
    later = _tap(client, "r1:dn")
    assert "weekly day off?" not in later["text"]
    assert "weekly day off?" not in _command(client, "/remind")["text"]
    [account] = storage.repo.accounts.values()
    assert account.day_off == DayOff()


def test_other_opens_the_picker_with_a_way_back_to_remind(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage)
    picker = _tap(client, "r1:dp")
    buttons = [b for row in picker["reply_markup"]["inline_keyboard"] for b in row]
    assert buttons[0]["callback_data"] == "r1:d:6"
    assert buttons[-1]["callback_data"] == "r1:v"


def test_the_question_never_goes_into_the_reminder_message() -> None:
    screen = reminder_screen(FluentTranslator(), "en", PracticeReminder(date(2026, 10, 24)))
    assert "day off" not in screen.text


def test_unlogged_day_off_today_shows_the_auto_note_without_a_check(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage)
    _set_off(storage, frozenset({_today().isoweekday()}))
    body = _command(client, "/log")
    assert "😌 Your weekly day off, shown as rest." in body["text"]
    assert not any(t.startswith("✓") for t in _texts(body))


def test_moon_day_on_the_day_off_names_the_city_and_both(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage)
    _set_off(storage, frozenset({_today().isoweekday()}))
    storage.moon_repo.days_by_location["mysuru"] = [MoonDay(_today(), MoonDayKind.PURNIMA)]
    body = _command(client, "/start")
    expected = "🌙 Moon day (📍 Mysuru), a traditional rest day and your weekly day off too."
    assert expected in body["text"]


def test_clearing_a_log_brings_the_auto_note_back(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage)
    _set_off(storage, frozenset({_today().isoweekday()}))
    _tap(client, f"d1:s:{_ymd(_today())}:p")
    cleared = _tap(client, f"d1:x:{_ymd(_today())}")
    assert "😌 Your weekly day off, shown as rest." in cleared["text"]


def test_week_picker_shows_auto_days(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage)
    _set_off(storage, frozenset({_today().isoweekday()}))
    week = _tap(client, f"d1:w:{_ymd(_today())}")
    assert _texts(week)[0].startswith("😌 ")


def test_callback_codecs_round_trip_and_reject_forged_codes() -> None:
    for data in ("s1:o", "s1:o:0", "s1:o:6"):
        cb = scb.decode(data)
        assert cb is not None
        assert scb.encode(cb) == data
        assert len(data.encode()) <= 64
    for data in ("r1:d:0", "r1:d:7", "r1:dp", "r1:dn"):
        cb = rcb.decode(data)
        assert cb is not None
        assert rcb.encode(cb) == data
    for forged in ("s1:o:67", "s1:o:8", "r1:d:9", "r1:d:67", "r1:d:"):
        assert (scb.decode(forged) if forged.startswith("s1") else rcb.decode(forged)) is None
