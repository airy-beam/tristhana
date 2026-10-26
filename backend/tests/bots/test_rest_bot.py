"""WH-01 part 2 in the bot, through the real webhook (ADR-0023): the "for how many days?"
question with per-kind chips, starting / keeping / ending a pause, covered days on the
pickers, the reminder's insert-if-absent 🧘/😌 (Q26), the paused line in /remind, and the
"hide 🌸" setting. Plus the `a1:` / `r1:p|r` / `s1:h` callback codecs."""

import importlib
import itertools
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from types import ModuleType
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from babel.dates import format_skeleton
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tristhana.bots.telegram import remind_callbacks, settings_callbacks
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.notifications import DEFAULTS
from tristhana.domain.rest_periods import RestPeriod
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
ZONE = "Asia/Almaty"
L, K, T = DayStatus.LADIES, DayStatus.SICK, DayStatus.TRAVEL
_ids = itertools.count(120_000)


@pytest.fixture(autouse=True)
def outbound(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    sent: list[str] = []

    async def record(self: AiohttpSession, bot: object, method: Any, **_: object) -> bool:
        sent.append(method.__api_method__)
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)
    return sent


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


def _data(body: Any) -> list[str]:
    return [
        b.get("callback_data", "") for row in body["reply_markup"]["inline_keyboard"] for b in row
    ]


def _today() -> date:
    return datetime.now(UTC).astimezone(ZoneInfo(ZONE)).date()


def _d(offset: int) -> date:
    return _today() + timedelta(days=offset)


def _ymd(offset: int) -> str:
    return _d(offset).strftime("%Y%m%d")


def _until(offset: int, lang: str = "en") -> str:
    return str(format_skeleton("MMMEd", _d(offset), locale=lang))


def _me(
    client: TestClient,
    storage: InMemoryStorage,
    lang: str = "en",
    reminders: bool = False,
    hide_ladies: bool = False,
) -> Any:
    """Create the account (via /log), give it a zone, optionally turn reminders on."""
    _command(client, "/log", lang)
    [account] = storage.repo.accounts.values()
    account = replace(account, timezone=ZONE)
    if hide_ladies:
        account = replace(account, hide_ladies=True)
    storage.repo.accounts[account.id] = account
    if reminders:
        on = replace(DEFAULTS, practice=replace(DEFAULTS.practice, on=True))
        storage.notifications.stored[account.id] = on
    return account


def _period(storage: InMemoryStorage, me: Any, start: int, end: int, kind: DayStatus) -> None:
    storage.rest_periods.rows[(me.id, _d(start))] = RestPeriod(_d(start), _d(end), kind)


def _log(storage: InMemoryStorage, me: Any, offset: int, status: DayStatus) -> None:
    storage.day_repo.rows[(me.id, _d(offset))] = (DayLog(_d(offset), status), ZONE)


def _periods(storage: InMemoryStorage, me: Any) -> list[RestPeriod]:
    return storage.rest_periods.of(me.id)


# The question after 🌸 / 🤒 / ✈️ (V + question)


def test_ladies_today_asks_for_how_many_days_with_its_own_chips(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage)

    body = _tap(client, f"d1:s:{_ymd(0)}:l")

    text = body["text"]
    assert text.startswith("✓ Today, ")
    assert "Rest is part of the practice 🌿" in text
    assert "Only you see this." in text
    # Reminders never chosen: the fill-only wording.
    assert "How many days should show as 🌸 Ladies' holiday, including today?" in text
    assert "Pause practice reminders" not in text
    texts = _texts(body)
    assert texts[:4] == ["2 days", "3 days", "5 days", "Other…"]
    assert texts[-2:] == ["✏️ Change", "📅 Another day"]
    assert _data(body)[:4] == [
        f"a1:p:{_ymd(0)}:l:2",
        f"a1:p:{_ymd(0)}:l:3",
        f"a1:p:{_ymd(0)}:l:5",
        f"a1:m:{_ymd(0)}:l:0",
    ]
    assert "No" not in texts  # ignoring the question = no pause


@pytest.mark.parametrize("code", ["k", "t"])
def test_sick_and_travel_yesterday_offer_three_four_five(
    client: TestClient, storage: InMemoryStorage, code: str
) -> None:
    _me(client, storage, reminders=True)

    body = _tap(client, f"d1:s:{_ymd(-1)}:{code}")

    assert "⏸ Pause practice reminders for how many days, including yesterday?" in body["text"]
    assert _texts(body)[:4] == ["3 days", "4 days", "5 days", "Other…"]
    assert _data(body)[3] == f"a1:m:{_ymd(-1)}:{code}:1"


def test_the_cheer_follows_the_kind(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage)

    sick = _tap(client, f"d1:s:{_ymd(0)}:k")["text"]
    travel = _tap(client, f"d1:s:{_ymd(-1)}:t")["text"]

    assert "Get well soon 🌿" in sick
    assert "Safe travels ✈️" in travel


def test_russian_plurals_on_the_chips(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage, lang="ru")

    first = _tap(client, f"d1:s:{_ymd(0)}:k", "ru")
    other = _tap(client, f"a1:m:{_ymd(0)}:k:0", "ru")

    assert _texts(first)[:4] == ["3 дня", "4 дня", "5 дней", "Другое…"]
    assert _texts(other)[:6] == ["2 дня", "6 дней", "7 дней", "10 дней", "14 дней", "‹ Назад"]  # noqa: RUF001
    assert "„🤒 Болезнь / травма“" in first["text"]


def test_other_and_back_are_a_pure_render(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    _me(client, storage)
    _tap(client, f"d1:s:{_ymd(0)}:l")
    touched: list[str] = []
    for name in ("range_with_moon", "list_range", "upsert", "history"):
        real = getattr(storage.day_repo, name)

        async def spy(*args: object, _real: Any = real, _name: str = name) -> object:
            touched.append(_name)
            return await _real(*args)

        monkeypatch.setattr(storage.day_repo, name, spy)

    other = _tap(client, f"a1:m:{_ymd(0)}:l:0")
    back = _tap(client, f"a1:b:{_ymd(0)}:l:0")

    assert touched == []
    assert _texts(other)[:4] == ["4 days", "6 days", "7 days", "‹ Back"]  # noqa: RUF001
    assert "How many days should show as 🌸 Ladies' holiday" in other["text"]
    assert _texts(back)[:4] == ["2 days", "3 days", "5 days", "Other…"]


@pytest.mark.parametrize(("offset", "code"), [(-2, "l"), (-9, "k"), (0, "r"), (0, "s")])
def test_no_question_for_backfill_or_other_statuses(
    client: TestClient, storage: InMemoryStorage, offset: int, code: str
) -> None:
    _me(client, storage)

    body = _tap(client, f"d1:s:{_ymd(offset)}:{code}")

    assert "How many days" not in body["text"]
    assert not any(d.startswith("a1:") for d in _data(body))


def test_no_question_for_a_continuation(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _log(storage, me, -1, L)

    body = _tap(client, f"d1:s:{_ymd(0)}:l")

    assert "How many days" not in body["text"]


# P: a number chosen


def test_choosing_a_number_starts_the_pause(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _tap(client, f"d1:s:{_ymd(0)}:l")

    body = _tap(client, f"a1:p:{_ymd(0)}:l:5")

    assert _periods(storage, me) == [RestPeriod(_d(0), _d(4), L)]
    text = body["text"]
    assert text.startswith("✓ Today, ")
    assert f"⏸ Set through {_until(4)}." in text
    assert "Those days show as 🌸 Ladies' holiday; you can log any day differently." in text
    assert "Only you see this." in text
    assert "⏹ End early" in _texts(body)
    assert f"a1:e:{_ymd(0)}:0" in _data(body)


def test_with_reminders_on_the_pause_names_them(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage, reminders=True)

    body = _tap(client, f"a1:p:{_ymd(-1)}:k:4")

    assert _periods(storage, me) == [RestPeriod(_d(-1), _d(2), K)]
    assert f"⏸ Practice reminders are paused through {_until(2)}." in body["text"]
    assert "⏹ End the pause" in _texts(body)
    assert f"a1:e:{_ymd(-1)}:1" in _data(body)


def test_fourteen_days_is_a_sick_choice(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)

    _tap(client, f"a1:p:{_ymd(0)}:k:14")

    assert _periods(storage, me) == [RestPeriod(_d(0), _d(13), K)]


@pytest.mark.parametrize("tail", ["l:10", "l:14", "l:8", "k:15", "r:3", "s:3", "l:1"])
def test_counts_outside_the_kinds_set_are_ignored(
    client: TestClient, storage: InMemoryStorage, outbound: list[str], tail: str
) -> None:
    me = _me(client, storage)
    outbound.clear()

    body = _tap(client, f"a1:p:{_ymd(0)}:{tail}")

    assert body is None or body["method"] == "answerCallbackQuery"
    assert outbound in ([], ["answerCallbackQuery"])
    assert _periods(storage, me) == []


def test_a_stale_start_for_two_days_ago_changes_nothing(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)

    _tap(client, f"a1:p:{_ymd(-2)}:k:3")

    assert _periods(storage, me) == []


# 🧘 inside a period, "keep the pause"


def test_practiced_inside_a_pause_offers_to_keep_it(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    _log(storage, me, -1, K)
    _period(storage, me, -1, 2, K)

    details = _tap(client, f"d1:s:{_ymd(0)}:p")

    assert (
        f"⏸ Practice logged for today, so the following days, through {_until(2)}, "
        "no longer show as 🤒 Sick / injury. Keep them as they were?"
    ) in details["text"]
    assert "Add details?" in details["text"]  # still PR-02's details screen
    keep = f"a1:k:{_ymd(-1)}:{_ymd(2)}:k:{_ymd(0)}"  # + the 🧘 day whose details return
    assert "⏸ Keep the pause" in _texts(details)
    assert keep in _data(details)
    assert _periods(storage, me) == []  # cut: only its start day was left

    kept = _tap(client, keep)

    assert _periods(storage, me) == [RestPeriod(_d(-1), _d(2), K)]
    assert f"⏸ Pause kept: 🤒 Sick / injury through {_until(2)}." in kept["text"]
    assert "⏸ Keep the pause" not in _texts(kept)
    assert storage.day_repo.rows[(me.id, _d(0))][0].status is DayStatus.PRACTICED


def test_no_keep_when_nothing_is_left_after_the_practiced_day(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    _period(storage, me, -3, 0, L)

    details = _tap(client, f"d1:s:{_ymd(0)}:p")

    assert "⏸ Keep the pause" not in _texts(details)


def test_a_stale_keep_is_a_quiet_no_op(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)

    body = _tap(client, f"a1:k:{_ymd(-6)}:{_ymd(-2)}:k:{_ymd(-3)}")

    assert _periods(storage, me) == []
    assert body is None or "Pause kept" not in body.get("text", "")


@pytest.mark.parametrize(
    "data",
    [
        "a1:k:{s}:{e8}:l:{s}",  # 8 days of 🌸: forged
        "a1:k:{s}:{s}:k:{s}",  # end = start
        "a1:k:{s}:{e3}:r:{s}",  # not a pausable kind
        "a1:k:{s}:{e3}:k:{s}",  # well-formed, but no 🧘 day inside: no backfill
    ],
)
def test_forged_keeps_are_ignored(client: TestClient, storage: InMemoryStorage, data: str) -> None:
    me = _me(client, storage)
    s, e3, e8 = _ymd(-1), _ymd(2), _ymd(6)

    _tap(client, data.format(s=s, e3=e3, e8=e8))

    assert _periods(storage, me) == []


def test_no_practice_inside_a_pause_changes_only_that_day(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    _period(storage, me, -1, 3, T)

    body = _tap(client, f"d1:s:{_ymd(0)}:s")

    assert "⏸ Keep the pause" not in _texts(body)
    assert _periods(storage, me) == [RestPeriod(_d(-1), _d(3), T)]


# End early / end the pause


def test_end_early_with_reminders_off(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _period(storage, me, -2, 3, K)

    body = _tap(client, f"a1:e:{_ymd(-2)}:0")

    assert _periods(storage, me) == [RestPeriod(_d(-2), _d(-1), K)]
    assert "⏹ Done: from today on, days no longer show as 🤒 Sick / injury." in body["text"]
    assert "reminders are back" not in body["text"]
    assert "🧘 Practiced" in _texts(body)  # today's grid, so today can be logged right here


def test_end_the_pause_with_reminders_on(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage, reminders=True)
    _period(storage, me, 0, 3, T)

    body = _tap(client, f"a1:e:{_ymd(0)}:1")

    assert _periods(storage, me) == []
    assert "▶️ Practice reminders are back from today." in body["text"]


def test_end_from_remind_shows_remind(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage, reminders=True)
    _period(storage, me, -1, 3, L)

    body = _tap(client, f"a1:er:{_ymd(-1)}")

    assert _periods(storage, me) == []  # only yesterday was left
    assert body["text"].startswith("🔔 Practice reminder")
    assert "⏸ Paused through" not in body["text"]


def test_end_twice_is_harmless(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _period(storage, me, -3, 3, K)

    _tap(client, f"a1:e:{_ymd(-3)}:0")
    _tap(client, f"a1:e:{_ymd(-3)}:0")

    assert _periods(storage, me) == [RestPeriod(_d(-3), _d(-1), K)]


# Covered days on the pickers


def test_a_covered_day_shows_the_period_line_without_a_check_mark(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    _log(storage, me, -1, K)
    _period(storage, me, -1, 2, K)

    body = _tap(client, f"d1:o:{_ymd(0)}")

    assert (
        f"🤒 Sick / injury through {_until(2)}. If the day went differently, log it below."
    ) in body["text"]
    assert not any(t.startswith("✓") for t in _texts(body))
    assert "⏹ End early" in _texts(body)
    assert f"a1:e:{_ymd(-1)}:0" in _data(body)


def test_saving_the_same_kind_on_a_covered_day_shows_the_pause(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage, reminders=True)
    _log(storage, me, -1, L)
    _period(storage, me, -1, 2, L)

    body = _tap(client, f"d1:s:{_ymd(0)}:l")

    assert "How many days" not in body["text"]  # inside the pause: no new question
    assert f"⏸ Practice reminders are paused through {_until(2)}." in body["text"]
    assert "⏹ End the pause" in _texts(body)
    assert f"a1:e:{_ymd(-1)}:1" in _data(body)


@pytest.mark.parametrize(("kind", "emoji"), [(L, "😌"), (K, "🤒"), (T, "✈️")])
def test_week_picker_shows_covered_days_privately(
    client: TestClient, storage: InMemoryStorage, kind: DayStatus, emoji: str
) -> None:
    me = _me(client, storage)
    _period(storage, me, -1, 2, kind)

    week = _tap(client, f"d1:w:{_ymd(0)}")

    first, second = _texts(week)[:2]
    assert first.startswith(f"{emoji} Today")
    assert second.startswith(f"{emoji} Yesterday")
    assert all("🌸" not in t for t in _texts(week))


# Hide 🌸


def test_grid_without_the_ladies_button(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage, hide_ladies=True)

    body = _command(client, "/log")

    assert _rows(body)[:4] == [
        ["🧘 Practiced"],
        ["😌 Rest day", "🌙 Moon day"],
        ["🤒 Sick / injury", "✈️ Travel"],
        ["🌱 No practice"],
    ]


def test_a_ladies_day_keeps_its_button_while_hidden(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage, hide_ladies=True)
    _log(storage, me, 0, L)

    body = _command(client, "/log")

    assert "✓ 🌸 Ladies' holiday" in _texts(body)


def test_start_honours_hide(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage, hide_ladies=True)

    body = _command(client, "/start")

    assert all("🌸" not in t for t in _texts(body))


def test_old_ladies_keyboards_still_work_while_hidden(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage, hide_ladies=True)

    _tap(client, f"d1:s:{_ymd(0)}:l")

    assert storage.day_repo.rows[(me.id, _d(0))][0].status is L


def test_settings_hide_and_show_the_button(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)

    shown = _command(client, "/settings")
    hidden = _tap(client, "s1:h:1")
    back = _tap(client, "s1:h:0")

    assert "🌸 Ladies' holiday button: shown" in shown["text"]
    assert "🌸 Hide the button" in _texts(shown)
    assert "s1:h:1" in _data(shown)
    assert "🌸 Ladies' holiday button: hidden" in hidden["text"]
    assert "🌸 Show the button" in _texts(hidden)
    assert "🌸 Ladies' holiday button: shown" in back["text"]
    assert storage.repo.accounts[me.id].hide_ladies is False


def test_settings_in_russian_quote_the_label(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage, lang="ru")

    body = _command(client, "/settings", "ru")

    assert "🌸 Кнопка „Женские дни“: показана" in body["text"]
    assert "🌸 Скрыть кнопку" in _texts(body)


# /remind during a pause


def test_remind_shows_the_pause_and_resume(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage, reminders=True)
    _period(storage, me, -1, 3, T)

    body = _command(client, "/remind")

    assert f"⏸ Paused through {_until(3)}" in body["text"]
    assert "▶️ Resume now" in _texts(body)
    assert f"a1:er:{_ymd(-1)}" in _data(body)


def test_remind_without_a_pause_has_no_resume(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage, reminders=True)

    body = _command(client, "/remind")

    assert "▶️ Resume now" not in _texts(body)


# The reminder's 🧘 / 😌 (Q26): insert-if-absent


def test_reminder_practiced_logs_an_empty_day_and_opens_the_details(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)

    body = _tap(client, f"r1:p:{_ymd(0)}")

    assert storage.day_repo.rows[(me.id, _d(0))][0].status is DayStatus.PRACTICED
    assert "Add details?" in body["text"]


def test_reminder_rest_logs_an_empty_day(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)

    body = _tap(client, f"r1:r:{_ymd(0)}")

    assert storage.day_repo.rows[(me.id, _d(0))][0].status is DayStatus.REST
    assert body["text"].startswith("✓ Today, ")


@pytest.mark.parametrize("code", ["p", "r"])
def test_reminder_buttons_never_overwrite_a_logged_day(
    client: TestClient, storage: InMemoryStorage, code: str
) -> None:
    me = _me(client, storage)
    _log(storage, me, 0, L)

    body = _tap(client, f"r1:{code}:{_ymd(0)}")

    assert storage.day_repo.rows[(me.id, _d(0))][0].status is L
    assert "🌸 Ladies' holiday" in body["text"]
    assert _texts(body)[0] == "✏️ Change"


def test_reminder_practiced_inside_a_pause_offers_to_keep_it(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage, reminders=True)
    _period(storage, me, -2, 2, K)

    body = _tap(client, f"r1:p:{_ymd(0)}")

    assert _periods(storage, me) == [RestPeriod(_d(-2), _d(-1), K)]
    assert f"a1:k:{_ymd(-2)}:{_ymd(2)}:k:{_ymd(0)}" in _data(body)


# Callback codecs (≤ 64 bytes, stateless, absolute values)


def _a1() -> ModuleType:
    """The `a1:` codec (imported per test, so a missing module fails the test, not setup)."""
    return importlib.import_module("tristhana.bots.telegram.rest_callbacks")


@pytest.mark.parametrize(
    "data",
    [
        "a1:p:20261026:l:5",
        "a1:p:20261026:l:2",
        "a1:p:20261026:k:14",
        "a1:p:20261026:t:10",
        "a1:m:20261026:l:1",
        "a1:b:20261026:t:0",
        "a1:k:20261024:20261028:l:20261026",
        "a1:k:20261013:20261026:k:20261013",  # 14 days of sick, cut on its first day
        "a1:e:20261024:1",
        "a1:e:20261024:0",
        "a1:er:20261024",
    ],
)
def test_rest_callbacks_round_trip_and_stay_small(data: str) -> None:
    a1 = _a1()
    cb = a1.decode(data)

    assert cb is not None
    assert a1.encode(cb) == data
    assert len(data.encode()) <= 34  # keep carries the 🧘 day too (≤ 64 for Telegram)


def test_rest_callbacks_decode_absolute_values() -> None:
    a1 = _a1()
    start = a1.decode("a1:p:20261026:k:14")
    keep = a1.decode("a1:k:20261024:20261028:l:20261026")

    assert (start.day, start.kind, start.days) == (date(2026, 10, 26), K, 14)
    assert (keep.day, keep.end, keep.kind) == (date(2026, 10, 24), date(2026, 10, 28), L)
    assert keep.practiced == date(2026, 10, 26)


@pytest.mark.parametrize(
    "data",
    [
        None,
        "",
        "a1",
        "a0:p:20261026:l:5",
        "a1:p:20261026:l:10",  # 🌸 has no 10 or 14
        "a1:p:20261026:l:14",
        "a1:p:20261026:l:1",
        "a1:p:20261026:k:8",
        "a1:p:20261026:k:15",
        "a1:p:20261026:r:3",  # plain rest has no period
        "a1:p:20261026:p:3",
        "a1:p:20261399:l:3",
        "a1:p:19991231:k:3",
        "a1:m:20261026:l:2",
        "a1:k:20261024:20261024:l:20261024",  # end = start
        "a1:k:20261028:20261024:k:20261026",  # end before start
        "a1:k:20261024:20261101:l:20261026",  # 9 days of 🌸
        "a1:k:20261001:20261015:k:20261005",  # 15 days
        "a1:k:20261024:20261028:r:20261026",
        "a1:k:20261024:20261028:l",  # the 🧘 day is missing
        "a1:k:20261024:20261028:l:20261028",  # the 🧘 day must be before the end
        "a1:k:20261024:20261028:l:20261023",  # … and inside the period
        "a1:e:20261024:2",
        "a1:er:2026102",
        "a1:x:20261024",
    ],
)
def test_rest_callbacks_reject_anything_else(data: str | None) -> None:
    assert _a1().decode(data) is None


@pytest.mark.parametrize("data", ["r1:p:20261026", "r1:r:20261026"])
def test_reminder_status_callbacks_round_trip(data: str) -> None:
    cb = remind_callbacks.decode(data)

    assert cb is not None
    assert cb.day == date(2026, 10, 26)
    assert remind_callbacks.encode(cb) == data
    assert len(data.encode()) <= 64


@pytest.mark.parametrize("data", ["r1:p:20261399", "r1:r", "r1:p:20261026:1"])
def test_reminder_status_callbacks_reject_malformed(data: str) -> None:
    assert remind_callbacks.decode(data) is None


@pytest.mark.parametrize("data", ["s1:h:1", "s1:h:0"])
def test_hide_ladies_callbacks_round_trip(data: str) -> None:
    cb = settings_callbacks.decode(data)

    assert cb is not None
    assert settings_callbacks.encode(cb) == data


@pytest.mark.parametrize("data", ["s1:h", "s1:h:2", "s1:h:yes"])
def test_hide_ladies_callbacks_reject_malformed(data: str) -> None:
    assert settings_callbacks.decode(data) is None


# Review fixes


def test_choosing_a_number_reads_the_reminder_flag_in_the_same_statement(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    me = _me(client, storage, reminders=True)
    reads: list[str] = []
    for name in ("settings", "settings_with_pause", "stored_row"):
        real = getattr(storage.notifications, name)

        async def spy(*args: object, _real: Any = real, _name: str = name) -> object:
            reads.append(_name)
            return await _real(*args)

        monkeypatch.setattr(storage.notifications, name, spy)

    body = _tap(client, f"a1:p:{_ymd(0)}:k:3")

    assert reads == []  # no second read: `place` says whether reminders are on
    assert _periods(storage, me) == [RestPeriod(_d(0), _d(2), K)]
    assert f"⏸ Practice reminders are paused through {_until(2)}." in body["text"]


def test_keep_brings_back_the_details_of_the_day_that_cut_it(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    _period(storage, me, -2, 3, T)
    _tap(client, f"d1:s:{_ymd(-1)}:p")  # practised yesterday: cut to [-2, -2] → removed

    kept = _tap(client, f"a1:k:{_ymd(-2)}:{_ymd(3)}:t:{_ymd(-1)}")

    assert _periods(storage, me) == [RestPeriod(_d(-2), _d(3), T)]
    assert kept["text"].startswith(f"⏸ Pause kept: ✈️ Travel through {_until(3)}.")
    assert "✓ Yesterday, " in kept["text"]  # yesterday's details, not today's


def test_end_early_names_a_removed_pause_without_reading_it_first(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    me = _me(client, storage)
    _period(storage, me, -1, 3, K)
    reads: list[object] = []
    real = storage.day_repo.range_with_moon

    async def spy(*args: object) -> object:
        reads.append(args)
        return await real(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(storage.day_repo, "range_with_moon", spy)

    body = _tap(client, f"a1:e:{_ymd(-1)}:0")

    assert _periods(storage, me) == []
    assert "days no longer show as 🤒 Sick / injury" in body["text"]
    assert len(reads) == 1  # only today's picker after it


@pytest.mark.parametrize("data", ["r1:t:1200", "r1:o:1"])
def test_the_pause_stays_on_remind_after_a_tap(
    client: TestClient, storage: InMemoryStorage, data: str
) -> None:
    me = _me(client, storage, reminders=True)
    _period(storage, me, -1, 3, T)

    body = _tap(client, data)

    assert f"⏸ Paused through {_until(3)}" in body["text"]
    assert f"a1:er:{_ymd(-1)}" in _data(body)
