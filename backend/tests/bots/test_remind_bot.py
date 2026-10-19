"""Practice-reminder screens through the real webhook (PR-10) and the notifier's rendering."""

import itertools
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.methods import SendMessage
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import (
    FixedClock,
    InMemoryAccounts,
    InMemoryStorage,
    day_use_cases,
    moon_use_cases,
    practice_use_cases,
    remind_use_cases,
)
from tristhana.application.accounts import EnsureAccount
from tristhana.application.ports.notifications import DeliveryStatus, PracticeReminder, Recipient
from tristhana.bots.telegram.notifier import TelegramNotifier
from tristhana.bots.telegram.remind_callbacks import RemindCallback, decode, encode
from tristhana.bots.telegram.runtime import build_runtime
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.notifications import DEFAULTS
from tristhana.domain.practice import Practice, PracticeContext, PracticeLength
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
    """Create the account (via /remind) and give it a zone."""
    _command(client, "/remind", lang)
    [account] = storage.repo.accounts.values()
    storage.repo.accounts[account.id] = replace(account, timezone=ZONE)
    return storage.repo.accounts[account.id]


def test_remind_screen_off_by_default(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage)

    body = _command(client, "/remind")

    assert body["text"].startswith("🔕 Practice reminder is off")
    assert "Not on moon days" in body["text"]
    rows = _rows(body)
    assert rows[0] == ["09:00", "10:00", "12:00"]
    assert rows[1] == ["18:00", "20:00", "21:00"]
    assert rows[2] == ["✓ Day off: Sat", "Day off: Sun"]
    assert rows[3] == ["✓ Mon", "✓ Tue", "✓ Wed", "✓ Thu"]
    assert rows[4] == ["✓ Fri", "Sat", "✓ Sun"]
    assert rows[5] == ["🔔 Turn on"]
    assert rows[6] == ["🌙 Moon reminders"]


def test_turn_on_pick_time_and_days(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage, "ru")

    on = _tap(client, "r1:o:1", "ru")
    evening = _tap(client, "r1:t:2000", "ru")
    sunday_off = _tap(client, "r1:w:123456", "ru")

    assert on["text"].startswith(
        "🔔 Напоминание о практике: каждый день, кроме субботы, в 10:00 Алматы (UTC+5)"  # noqa: RUF001
    )
    assert "✓ 20:00" in _texts(evening)
    assert sunday_off["text"].startswith(
        "🔔 Напоминание о практике: каждый день, кроме воскресенья"  # noqa: RUF001
    )
    assert "✓ Выходной: вс" in _texts(sunday_off)


def test_the_last_weekday_cannot_be_removed(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage)
    _tap(client, "r1:w:3")

    body = _tap(client, "r1:o:1")

    wed = next(
        b for row in body["reply_markup"]["inline_keyboard"] for b in row if b["text"] == "✓ Wed"
    )
    assert wed["callback_data"] == "r1:w:3"  # tapping keeps the set
    assert "Wed, at 10:00" in body["text"]


def test_without_a_zone_the_time_is_local_and_the_zone_is_asked_for(client: TestClient) -> None:
    body = _command(client, "/remind")
    on = _tap(client, "r1:o:1")

    assert "To remind you at the right hour I need your time zone" in body["text"]
    assert "at 10:00 your time" in on["text"]


def test_links_between_moon_and_practice_reminders(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage)

    moon = _tap(client, "m1:r")

    assert "🧘 Practice reminder" in _texts(moon)


def test_offer_under_practice_saved_yes_and_no(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage)
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")
    summary = _tap(client, f"p1:v:{d}")
    assert _texts(summary)[-2:] == ["🔔 Yes, remind me", "No, thanks"]

    no = _tap(client, f"r1:n:{d}")

    assert "Want me to ask" not in no["text"]
    assert "No, thanks" not in _texts(no)
    again = _tap(client, f"p1:v:{d}")
    assert "Want me to ask" not in again["text"]  # offered once
    [settings] = storage.notifications.stored.values()
    assert settings.practice.on is False


def test_offer_yes_turns_it_on_and_shows_the_settings(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage)
    d = _ymd(_today())
    _tap(client, f"d1:s:{d}:p")

    yes = _tap(client, f"r1:y:{d}")

    assert yes["text"].startswith("🔔 Practice reminder: every day except Saturday, at ")
    [settings] = storage.notifications.stored.values()
    assert settings.practice.on is True
    assert settings.practice.at in (time(10), time(20))


def test_no_offer_for_another_day(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage)
    d = _ymd(_today() - timedelta(days=2))
    _tap(client, f"d1:s:{d}:p")

    body = _tap(client, f"p1:v:{d}")

    assert "Want me to ask" not in body["text"]


def test_same_as_last_time_logs_and_shows_what_was_copied(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    today = _today()
    old = today - timedelta(days=20)
    storage.day_repo.rows[(me.id, old)] = (DayLog(old, DayStatus.PRACTICED), ZONE)
    storage.day_repo.practice_rows[(me.id, old)] = Practice(
        PracticeContext.MYSORE, length=PracticeLength(("primary",), "navasana")
    )

    body = _tap(client, f"r1:s:{_ymd(today)}")

    assert body["text"].startswith("✓ Today")
    assert "Mysore · Primary → Navasana" in body["text"]
    assert "Copied from" in body["text"]  # more than two weeks ago
    assert _texts(body)[:2] == ["📝 Details", "✏️ Change"]
    assert storage.day_repo.rows[(me.id, today)][0].status is DayStatus.PRACTICED


def test_same_as_last_time_without_history_opens_the_details(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)

    body = _tap(client, f"r1:s:{_ymd(_today())}")

    assert "Add details?" in body["text"]
    assert storage.day_repo.rows[(me.id, _today())][0].status is DayStatus.PRACTICED


def test_same_as_last_time_never_overwrites_a_logged_day(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    today = _today()
    storage.day_repo.rows[(me.id, today)] = (DayLog(today, DayStatus.LADIES), ZONE)

    body = _tap(client, f"r1:s:{_ymd(today)}")

    assert "🌸 Ladies' holiday" in body["text"]
    assert _texts(body)[0] == "✏️ Change"
    assert storage.day_repo.rows[(me.id, today)][0].status is DayStatus.LADIES


def test_same_as_last_time_for_a_future_day_shows_the_week(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage)

    body = _tap(client, f"r1:s:{_ymd(_today() + timedelta(days=3))}")

    assert body["text"].startswith("That day hasn't come yet")


def test_turn_off_from_a_reminder_and_back(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage)
    d = _ymd(_today())
    _tap(client, "r1:o:1")

    off = _tap(client, f"r1:q:{d}:0")
    back = _tap(client, f"r1:q:{d}:1")

    assert off["text"].endswith("You can turn them on any time in /remind.")
    assert _texts(off) == ["🔔 Turn back on"]
    assert back["text"].endswith("🔔 Practice reminders are on again.")
    assert _texts(back)[0] == "✅ Practiced, same as last time"
    [settings] = storage.notifications.stored.values()
    assert settings.practice.on is True


@pytest.mark.parametrize(
    "data",
    [
        "r1",
        "r1:x",
        "r1:o:2",
        "r1:t:2561",
        "r1:w:",
        "r1:w:8",
        "r1:w:11",
        "r1:s:20261399",
        "r1:q:20261019:2",
        "r0:v",
    ],
)
def test_malformed_remind_callbacks(data: str) -> None:
    assert decode(data) is None


def test_every_remind_callback_fits_64_bytes() -> None:
    day = date(2026, 10, 19)
    for cb in (
        RemindCallback("view"),
        RemindCallback("switch", on=True),
        RemindCallback("time", at=time(21)),
        RemindCallback("days", days=frozenset(range(1, 8))),
        RemindCallback("yes", day=day),
        RemindCallback("no", day=day),
        RemindCallback("same", day=day),
        RemindCallback("quick", on=False, day=day),
    ):
        data = encode(cb)
        assert len(data.encode()) <= 64
        assert decode(data) == cb


def _notifier(monkeypatch: pytest.MonkeyPatch) -> tuple[TelegramNotifier, list[Any]]:
    runtime = build_runtime(
        TOKEN,
        EnsureAccount(InMemoryAccounts(), FixedClock()),
        day_use_cases(),
        practice_use_cases(),
        moon_use_cases(),
        remind_use_cases(),
        FluentTranslator(),
    )
    sent: list[Any] = []

    async def send(self: AiohttpSession, bot: object, method: Any, **_: object) -> Any:
        sent.append(method)
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", send)
    return TelegramNotifier(lambda: runtime, FluentTranslator()), sent


async def test_notifier_renders_the_practice_reminder(monkeypatch: pytest.MonkeyPatch) -> None:
    notifier, sent = _notifier(monkeypatch)

    result = await notifier.deliver(Recipient("42", "ru"), PracticeReminder(date(2026, 10, 19)))

    assert result.status is DeliveryStatus.SENT
    [method] = sent
    assert isinstance(method, SendMessage)
    assert method.text == "🌿 пн, 19 окт.: практика или отдых? Отметить можно одним нажатием."
    markup = method.reply_markup
    assert markup is not None
    rows = [[b.callback_data for b in row] for row in markup.inline_keyboard]  # type: ignore[union-attr]
    assert rows == [
        ["r1:s:20261019"],
        ["d1:s:20261019:p", "d1:s:20261019:r"],
        ["d1:o:20261019", "r1:q:20261019:0"],
    ]
    # No 🌸 on the reminder itself: it stays in chat history.
    assert all("🌸" not in b.text for row in markup.inline_keyboard for b in row)  # type: ignore[union-attr]


async def test_notifier_renders_the_pause_note(monkeypatch: pytest.MonkeyPatch) -> None:
    notifier, sent = _notifier(monkeypatch)

    await notifier.deliver(Recipient("42", "en"), PracticeReminder(date(2026, 10, 19), pause=True))

    [method] = sent
    assert method.text.startswith("🌿 I'll stop asking for now.")
    assert "/remind" in method.text
    assert DEFAULTS.practice.on is None  # opt-in stays the default
