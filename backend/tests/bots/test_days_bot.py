"""Day-status screens through the real webhook (PR-01, PR-04, UI-06): Today (T0), "Other
reason" (T1), the day editor (E0), the saved screen (S), the week picker. Outbound Bot API
calls (the parallel answerCallbackQuery) are recorded instead of sent."""

import itertools
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.bots.statements import Statements
from tests.fakes import InMemoryStorage
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.rest_periods import RestPeriod
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
_ids = itertools.count(50_000)


@pytest.fixture
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
def client(storage: InMemoryStorage, outbound: list[str]) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
    )
    with TestClient(create_app(settings, storage)) as c:
        yield c


def _today(lang: str = "en") -> date:
    """The bot's "today" for a new account (no zone yet → provisional: en UTC, ru Moscow)."""
    zone = ZoneInfo("Europe/Moscow" if lang == "ru" else "UTC")
    return datetime.now(UTC).astimezone(zone).date()


def _ymd(day: date) -> str:
    return day.strftime("%Y%m%d")


def _user(language_code: str) -> dict[str, Any]:
    return {"id": 42, "is_bot": False, "first_name": "Ash", "language_code": language_code}


def _post(client: TestClient, update: dict[str, Any]) -> Any:
    response = client.post(
        "/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}
    )
    assert response.status_code == 200
    return response.json() if response.content else None


def _command(client: TestClient, text: str, language_code: str = "en") -> Any:
    message = {
        "message_id": 7,
        "date": 1_760_000_000,
        "chat": {"id": 42, "type": "private"},
        "from": _user(language_code),
        "text": text,
        "entities": [{"type": "bot_command", "offset": 0, "length": len(text)}],
    }
    return _post(client, {"update_id": next(_ids), "message": message})


def _tap(client: TestClient, data: str, language_code: str = "en", old: bool = False) -> Any:
    message: dict[str, Any] = {"message_id": 9, "chat": {"id": 42, "type": "private"}}
    # date 0 = a message too old to edit (InaccessibleMessage)
    message |= {"date": 0} if old else {"date": 1_760_000_000, "text": "…"}
    callback = {
        "id": f"cb{next(_ids)}",
        "from": _user(language_code),
        "chat_instance": "ci",
        "data": data,
        "message": message,
    }
    return _post(client, {"update_id": next(_ids), "callback_query": callback})


def _buttons(body: Any) -> list[dict[str, str]]:
    return [b for row in body["reply_markup"]["inline_keyboard"] for b in row]


def _rows(body: Any) -> list[list[str]]:
    return [[b["text"] for b in row] for row in body["reply_markup"]["inline_keyboard"]]


def _log(client: TestClient, storage: InMemoryStorage, day: date, status: DayStatus) -> None:
    if not storage.repo.accounts:
        _command(client, "/moon")  # a first contact
    [account] = storage.repo.accounts.values()
    storage.day_repo.rows[(account.id, day)] = (DayLog(day, status), None)


def _zone(storage: InMemoryStorage, zone: str = "UTC") -> None:
    """A known zone: the city question (B7) stays off these screens."""
    [account] = storage.repo.accounts.values()
    storage.repo.accounts[account.id] = replace(account, timezone=zone)


# Today (T0)


def test_log_shows_today_with_its_three_choices_then_another_day_and_the_menu(
    client: TestClient,
) -> None:
    body = _command(client, "/log")
    d = _ymd(_today())

    assert body["method"] == "sendMessage"
    assert body["text"].startswith("Today, ")
    assert body["text"].endswith("Practice or rest? Both go in your log.")
    assert _rows(body) == [
        ["🧘 Practiced"],
        ["😌 Rest day"],
        ["Other…"],
        ["📅 Another day", "☰ Menu"],  # UI-06 stage 6 (C8)
    ]
    assert [b["callback_data"] for b in _buttons(body)] == [
        f"d1:n:{d}:p",  # ADR-0051: Today's own letter
        f"d1:n:{d}:r",
        f"d1:r:{d}:t",
        f"d1:w:{d}",
        "w1:m",
    ]
    assert "🌸" not in str(body)  # off the first screen (it is under "Other reason")


def test_today_in_russian(client: TestClient) -> None:
    body = _command(client, "/log", "ru")

    assert _rows(body) == [
        ["🧘 Практика"],
        ["😌 День отдыха"],
        ["Другое…"],
        ["📅 Другой день", "☰ Меню"],
    ]
    assert "Практика или отдых?" in body["text"]


@pytest.mark.parametrize(
    ("status", "marked", "line"),
    [
        (DayStatus.PRACTICED, "✓ 🧘 Practiced", "✓ In your log: 🧘 Practiced"),
        (DayStatus.REST, "✓ 😌 Rest day", "✓ In your log: 😌 Rest day"),
        (DayStatus.SICK, "✓ Other…", "✓ In your log: 🤒 Sick / injury"),
        (DayStatus.MOON, "✓ Other…", "✓ In your log: 🌙 Moon day"),
        (DayStatus.SKIPPED, "✓ Other…", "✓ In your log: 🌱 No practice"),
    ],
)
def test_today_marks_the_logged_choice_and_says_what_it_is(
    client: TestClient, storage: InMemoryStorage, status: DayStatus, marked: str, line: str
) -> None:
    _log(client, storage, _today(), status)

    body = _command(client, "/log")

    texts = [b["text"] for b in _buttons(body)]
    assert [t for t in texts if t.startswith("✓")] == [marked]
    assert len(texts) == 5
    # The date, then what is logged: the question is answered, so it isn't asked again.
    date_line, logged = body["text"].split("\n")
    assert date_line.startswith("Today, ")
    assert logged == line
    assert "Practice or rest?" not in body["text"]


def test_today_shows_the_auto_rest_line_on_a_moon_day(
    client: TestClient, storage: InMemoryStorage
) -> None:
    storage.moon_repo.days_by_location["mysuru"] = [MoonDay(_today(), MoonDayKind.PURNIMA)]

    body = _command(client, "/log")

    # The date opens the message (and a chat-list preview); the line that already says why
    # the day is rest follows, and "Practice or rest?" is not asked after it.
    date_line, auto = body["text"].split("\n")
    assert date_line.startswith("Today, ")
    assert (
        auto == "🌙 Moon day (📍 Mysuru), a traditional rest day. If you practiced, log it below."
    )
    assert "In your log" not in body["text"]  # shown as rest, not logged
    assert not [b for b in _buttons(body) if b["text"].startswith("✓")]
    assert len(_buttons(body)) == 5


def test_today_during_a_pause_opens_with_the_date_not_the_pause(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _command(client, "/moon")  # a first contact
    [account] = storage.repo.accounts.values()
    start, end = _today() - timedelta(days=1), _today() + timedelta(days=2)
    storage.day_repo.periods.rows[(account.id, start)] = RestPeriod(start, end, DayStatus.LADIES)

    body = _command(client, "/log")

    date_line, pause = body["text"].split("\n")
    assert date_line.startswith("Today, ")  # never 🌸 first: a chat-list preview shows this
    assert pause.startswith("🌸 Ladies' holiday through ")
    assert "Practice or rest?" not in body["text"]
    assert [row[0] for row in _rows(body)[:3]] == ["🧘 Practiced", "😌 Rest day", "Other…"]
    assert _rows(body)[-1] == ["📅 Another day", "☰ Menu"]


def test_the_menu_hint_and_a_lead_stay_above_the_date(
    client: TestClient, storage: InMemoryStorage
) -> None:
    storage.moon_repo.days_by_location["mysuru"] = [MoonDay(_today(), MoonDayKind.PURNIMA)]
    _log(client, storage, _today() - timedelta(days=1), DayStatus.REST)  # active: no front door

    body = _command(client, "/start")

    hint, day = body["text"].split("\n\n")
    assert hint == "Everything else is now under ☰ Menu."
    assert day.startswith("Today, ")
    assert day.split("\n")[1].startswith("🌙 Moon day")


def test_today_is_one_read(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    _command(client, "/log")
    statements = Statements(monkeypatch, storage)

    _command(client, "/log")
    _tap(client, "w1:n")

    assert statements.names == ["InMemoryDays.range_with_moon"] * 2


def test_today_from_the_menu_edits_in_place(client: TestClient) -> None:
    body = _tap(client, "w1:n")

    assert body["method"] == "editMessageText"
    assert body["text"].startswith("Today, ")


# "Other reason" (T1)


@pytest.mark.parametrize(("origin", "back"), [("t", "w1:n"), ("e", "d1:o:{d}")])
def test_other_reason_lists_the_rest_and_goes_back_where_it_came_from(
    client: TestClient, origin: str, back: str
) -> None:
    d = _ymd(_today() - timedelta(days=1))

    body = _tap(client, f"d1:r:{d}:{origin}")

    assert body["method"] == "editMessageText"
    assert body["text"].startswith("Yesterday, ")
    letter = "n" if origin == "t" else "s"  # from Today: ask which day if tapped later
    assert [(b["text"], b["callback_data"]) for b in _buttons(body)] == [
        ("🌙 Moon day", f"d1:{letter}:{d}:m"),
        ("🌸 Ladies' holiday", f"d1:{letter}:{d}:l"),
        ("🤒 Sick / injury", f"d1:{letter}:{d}:k"),
        ("✈️ Travel", f"d1:{letter}:{d}:t"),
        ("🌱 No practice", f"d1:{letter}:{d}:s"),
        ("‹ Back", back.format(d=d)),  # noqa: RUF001
    ]


def test_other_reason_costs_no_statement(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    _command(client, "/log")
    statements = Statements(monkeypatch, storage)

    _tap(client, f"d1:r:{_ymd(_today())}:t")

    assert statements.names == []


def test_a_reason_saves_like_any_status(client: TestClient, storage: InMemoryStorage) -> None:
    today = _today()
    _command(client, "/log")
    _zone(storage)
    reasons = _tap(client, f"d1:r:{_ymd(today)}:t")

    saved = _tap(client, reasons["reply_markup"]["inline_keyboard"][4][0]["callback_data"])

    assert saved["text"].startswith("✓ Today, ")
    [(day, _)] = storage.day_repo.rows.values()
    assert (day.local_date, day.status) == (today, DayStatus.SKIPPED)
    assert _rows(saved) == [["✏️ Change", "📅 Another day"], ["📓 Note"], ["☰ Menu"]]


@pytest.mark.parametrize("data", ["d1:r:20261018", "d1:r:20261018:x", "d1:r:20261399:t", "d1:r"])
def test_forged_other_reason_data_only_answers(
    client: TestClient, outbound: list[str], data: str
) -> None:
    assert _tap(client, data) is None
    assert outbound == ["answerCallbackQuery"]


# The day editor (E0)


def test_the_day_editor_has_the_same_three_choices_then_its_own_rows(
    client: TestClient, storage: InMemoryStorage
) -> None:
    day = _today() - timedelta(days=1)
    d = _ymd(day)

    body = _tap(client, f"d1:o:{d}")

    assert body["text"].startswith("Yesterday, ")
    assert _rows(body) == [
        ["🧘 Practiced"],
        ["😌 Rest day"],
        ["Other…"],
        ["📓 Note"],  # PR-07
        ["📅 Another day"],
        ["‹ Today"],  # noqa: RUF001
    ]
    data = [b["callback_data"] for b in _buttons(body)]
    assert data[:3] == [f"d1:s:{d}:p", f"d1:s:{d}:r", f"d1:r:{d}:e"]
    assert data[-2:] == [f"d1:w:{_ymd(_today())}", "w1:n"]
    assert all(len(value.encode()) <= 64 for value in data)


def test_tap_saves_answers_and_edits_in_place(
    client: TestClient, storage: InMemoryStorage, outbound: list[str]
) -> None:
    today = _today()

    body = _tap(client, f"d1:s:{_ymd(today)}:p")

    assert outbound == ["answerCallbackQuery"]
    assert body["method"] == "editMessageText"
    assert body["text"].startswith("✓ Today, ")
    assert "🧘 Practiced" in body["text"]
    assert "Practice done 🙏" in body["text"]
    [(day, _)] = storage.day_repo.rows.values()
    assert (day.local_date, day.status) == (today, DayStatus.PRACTICED)


def test_ladies_holiday_is_private_and_hidden_in_the_week_view(client: TestClient) -> None:
    today = _today("ru")

    saved = _tap(client, f"d1:s:{_ymd(today)}:l", language_code="ru")
    week = _tap(client, f"d1:w:{_ymd(today)}", language_code="ru")

    assert "Это видишь только ты" in saved["text"]
    first = _buttons(week)[0]["text"]
    assert first.startswith("😌 Сегодня")
    assert "🌸" not in first


def test_reopening_a_day_marks_the_current_status_and_offers_clear(client: TestClient) -> None:
    day = _today() - timedelta(days=1)
    _tap(client, f"d1:s:{_ymd(day)}:m")

    body = _tap(client, f"d1:o:{_ymd(day)}")

    date_line, logged = body["text"].split("\n")
    assert date_line.startswith("Yesterday, ")
    assert logged == "✓ In your log: 🌙 Moon day"
    assert _rows(body)[2:] == [
        ["✓ Other…"],
        ["📓 Note"],
        ["Clear", "📅 Another day"],
        ["‹ Today"],  # noqa: RUF001
    ]


def test_clear(client: TestClient, storage: InMemoryStorage) -> None:
    today = _today()
    _tap(client, f"d1:s:{_ymd(today)}:r")

    body = _tap(client, f"d1:x:{_ymd(today)}")

    assert storage.day_repo.rows == {}
    assert body["text"].startswith("Cleared.\n\nToday, ")


def test_week_picker_pages_back_and_never_past_today(client: TestClient) -> None:
    today = _today()

    week = _tap(client, f"d1:w:{_ymd(today + timedelta(days=30))}")  # stale/forged: capped
    days = [b for b in _buttons(week) if b["callback_data"].startswith("d1:o:")]
    paging = [b["callback_data"] for b in _buttons(week) if b["callback_data"].startswith("d1:w:")]

    assert days[0]["callback_data"] == f"d1:o:{_ymd(today)}"
    assert len(days) == 7
    assert paging == [f"d1:w:{_ymd(today - timedelta(days=7))}"]  # earlier only, no "later"


def test_future_date_is_refused_gently(client: TestClient, storage: InMemoryStorage) -> None:
    _tap(client, f"d1:s:{_ymd(_today())}:m")

    body = _tap(client, f"d1:s:{_ymd(_today() + timedelta(days=3))}:p")

    assert body["text"].startswith("In your city this day hasn't come yet.")
    assert _buttons(body)[0]["text"].startswith("🌙 Today")  # the real week, not blanks
    assert len(storage.day_repo.rows) == 1


def test_week_never_pages_before_2000(client: TestClient) -> None:
    body = _tap(client, "d1:w:20000103")

    data = [b["callback_data"] for b in _buttons(body)]
    days = [b for b in _buttons(body) if b["callback_data"].startswith("d1:o:")]
    assert [b["callback_data"] for b in days] == ["d1:o:20000103", "d1:o:20000102", "d1:o:20000101"]
    assert data[3:] == ["d1:w:20000110", "w1:m"]  # "Later" only, no "Earlier"; then the Menu
    assert all(" 2000" in b["text"] for b in days)  # another year: shown with the year


def test_clear_reads_the_day_back_once(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    today = _today()
    _tap(client, f"d1:s:{_ymd(today)}:r")
    reads: list[object] = []
    real = storage.day_repo.list_range

    async def counting(*args: object) -> object:
        reads.append(args)
        return await real(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(storage.day_repo, "list_range", counting)
    body = _tap(client, f"d1:x:{_ymd(today)}")

    assert len(reads) == 1  # one read: the day may now show as auto-rest (PR-09)
    assert "Clear" not in [b["text"] for b in _buttons(body)]


@pytest.mark.parametrize("code", ["p", "r", "l", "k"])
def test_no_time_zone_tip_on_any_saved_screen(
    client: TestClient, storage: InMemoryStorage, code: str
) -> None:
    # UI-06 Q314: the tip left the saved screens, with the zone unknown or known.
    unknown = _tap(client, f"d1:s:{_ymd(_today())}:{code}")
    [account] = storage.repo.accounts.values()
    storage.repo.accounts[account.id] = replace(account, timezone="UTC")

    known = _tap(client, f"d1:s:{_ymd(_today())}:{code}")

    for saved in (unknown, known):
        assert saved["text"].startswith("✓ Today, ")
        assert "time zone" not in saved["text"]
        assert "open the app" not in saved["text"].lower()


def test_a_saved_rest_day_is_one_write_and_ends_with_the_menu(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    _command(client, "/log")
    _zone(storage)
    statements = Statements(monkeypatch, storage)

    saved = _tap(client, f"d1:s:{_ymd(_today())}:r")

    assert statements.names == ["InMemoryDays.upsert"]
    assert _rows(saved) == [["✏️ Change", "📅 Another day"], ["📓 Note"], ["☰ Menu"]]
    assert [b["callback_data"] for b in _buttons(saved)][-1] == "w1:m"


def test_a_saved_ladies_day_keeps_its_private_note(client: TestClient) -> None:
    saved = _tap(client, f"d1:s:{_ymd(_today())}:l")

    assert "Only you see this." in saved["text"]


def test_log_today_opens_a_new_message_and_keeps_the_greeting(client: TestClient) -> None:
    body = _tap(client, "d1:t")

    assert body["method"] == "sendMessage"  # the /start greeting keeps its "Open the app"
    assert body["text"].startswith("Today, ")


@pytest.mark.parametrize("data", ["d1:zz", "d1:s:20261399:p", "d1:s:20261018:?", "d1:o"])
def test_malformed_callbacks_are_only_answered(
    client: TestClient, outbound: list[str], data: str
) -> None:
    assert _tap(client, data) is None
    assert outbound == ["answerCallbackQuery"]


def test_unknown_keyboards_are_answered_silently(client: TestClient) -> None:
    body = _tap(client, "d0:t")

    assert body["method"] == "answerCallbackQuery"
    assert "text" not in body


def test_old_messages_get_a_new_message(client: TestClient) -> None:
    body = _tap(client, f"d1:o:{_ymd(_today())}", old=True)

    assert body["method"] == "sendMessage"
    assert body["chat_id"] == 42


def test_database_down_gets_a_toast(client: TestClient, storage: InMemoryStorage) -> None:
    storage.repo.down = True

    body = _tap(client, "d1:t")

    assert body["method"] == "answerCallbackQuery"


# UI-06 stage 6 (B6, ADR-0051): a tap on an old Today asks which day.


def test_todays_choices_and_its_other_screen_carry_their_own_letter(client: TestClient) -> None:
    d = _ymd(_today())

    today = _command(client, "/log")
    reasons = _tap(client, f"d1:r:{d}:t")
    editor = _tap(client, f"d1:o:{d}")
    editor_reasons = _tap(client, f"d1:r:{d}:e")

    assert [b["callback_data"] for b in _buttons(today)][:2] == [f"d1:n:{d}:p", f"d1:n:{d}:r"]
    assert {b["callback_data"][:5] for b in _buttons(reasons)[:-1]} == {"d1:n:"}
    assert [b["callback_data"] for b in _buttons(editor)][:2] == [f"d1:s:{d}:p", f"d1:s:{d}:r"]
    assert {b["callback_data"][:5] for b in _buttons(editor_reasons)[:-1]} == {"d1:s:"}


def test_a_tap_from_todays_today_saves_at_once(
    client: TestClient, storage: InMemoryStorage
) -> None:
    today = _today()

    body = _tap(client, f"d1:n:{_ymd(today)}:p")

    assert body["text"].startswith("✓ Today, ")
    [(day, _)] = storage.day_repo.rows.values()
    assert (day.local_date, day.status) == (today, DayStatus.PRACTICED)


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_a_tap_from_yesterdays_today_asks_which_day_and_saves_nothing(
    client: TestClient, storage: InMemoryStorage, outbound: list[str], lang: str
) -> None:
    today = _today(lang)
    yesterday = today - timedelta(days=1)

    body = _tap(client, f"d1:n:{_ymd(yesterday)}:r", language_code=lang)

    assert outbound == ["answerCallbackQuery"]
    assert body["method"] == "editMessageText"
    expected = {
        "en": "This message is from an earlier day. Which day is it for: 😌 Rest day?",
        "ru": "Это сообщение с прошлого дня. На какой день записать: 😌 День отдыха?",  # noqa: RUF001
    }
    assert body["text"] == expected[lang]
    rows = body["reply_markup"]["inline_keyboard"]
    assert [len(row) for row in rows] == [1, 1, 1]  # one date per full-width row, then Back
    assert [row[0]["callback_data"] for row in rows] == [
        f"d1:s:{_ymd(today)}:r",
        f"d1:s:{_ymd(yesterday)}:r",
        "w1:n",
    ]
    assert rows[0][0]["text"].startswith(("Today, ", "Сегодня, "))
    assert rows[1][0]["text"].startswith(("Yesterday, ", "Вчера, "))
    assert rows[2][0]["text"] in ("‹ Back", "‹ Назад")  # noqa: RUF001
    assert storage.day_repo.rows == {}


def test_the_question_costs_no_statement(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    _command(client, "/log")
    statements = Statements(monkeypatch, storage)

    _tap(client, f"d1:n:{_ymd(_today() - timedelta(days=3))}:p")

    assert statements.names == []


def test_the_answer_saves_the_date_it_names(client: TestClient, storage: InMemoryStorage) -> None:
    yesterday = _today() - timedelta(days=1)
    asked = _tap(client, f"d1:n:{_ymd(yesterday)}:k")

    saved = _tap(client, asked["reply_markup"]["inline_keyboard"][1][0]["callback_data"])

    assert saved["text"].startswith("✓ Yesterday, ")
    [(day, _)] = storage.day_repo.rows.values()
    assert (day.local_date, day.status) == (yesterday, DayStatus.SICK)


def test_a_tap_from_a_today_in_the_future_is_refused_gently(
    client: TestClient, storage: InMemoryStorage
) -> None:
    body = _tap(client, f"d1:n:{_ymd(_today() + timedelta(days=2))}:p")

    assert body["text"].startswith("In your city this day hasn't come yet.")
    assert storage.day_repo.rows == {}


# UI-06 stage 6 (C8): another day, one tap from Today.


def test_today_ends_with_another_day_beside_the_menu(client: TestClient) -> None:
    body = _command(client, "/log")

    assert _rows(body)[-1] == ["📅 Another day", "☰ Menu"]
    assert [b["callback_data"] for b in body["reply_markup"]["inline_keyboard"][-1]] == [
        f"d1:w:{_ymd(_today())}",
        "w1:m",
    ]


# UI-06 stage 6 (C7): a rest day's note, one tap away.


def test_a_saved_rest_day_offers_its_note(client: TestClient, storage: InMemoryStorage) -> None:
    _command(client, "/log")
    _zone(storage)
    d = _ymd(_today())

    saved = _tap(client, f"d1:s:{d}:r")
    note = _tap(client, f"n1:o:{d}:d")
    back = _tap(client, f"n1:b:{d}:d")

    assert _rows(saved) == [["✏️ Change", "📅 Another day"], ["📓 Note"], ["☰ Menu"]]
    assert _buttons(saved)[2]["callback_data"] == f"n1:o:{d}:d"
    assert note["text"].startswith("📓 ")
    assert back["text"].startswith("Today, ")  # Back: the day's editor
    assert _rows(back)[-1] == ["‹ Today"]  # noqa: RUF001


# UI-06 stage 6 (B7): the city question after a save.

CITY_ASK = "📍 Which city do you live in? Your days and reminders follow its clock."
CITY_ROW = [("🏙 Choose my city", "s1:cp:0"), ("Not now", "s1:n")]


def _city_row(body: Any) -> list[tuple[str, str]] | None:
    for row in body["reply_markup"]["inline_keyboard"]:
        pairs = [(b["text"], b.get("callback_data", "")) for b in row]
        if pairs and pairs[0][1] == "s1:cp:0":
            return pairs
    return None


@pytest.mark.parametrize("code", ["r", "k", "l", "m", "s"])
def test_a_saved_day_asks_for_the_city_while_none_is_known(
    client: TestClient, storage: InMemoryStorage, code: str
) -> None:
    saved = _tap(client, f"d1:s:{_ymd(_today())}:{code}")

    assert saved["text"].endswith(CITY_ASK)
    assert "moon" not in CITY_ASK.lower()  # the home city is not the moon city (MD-02)
    assert _city_row(saved) == CITY_ROW
    assert _rows(saved)[-1] == ["☰ Menu"]


def test_the_practiced_screen_asks_for_the_city_too(client: TestClient) -> None:
    saved = _tap(client, f"d1:s:{_ymd(_today())}:p")

    assert CITY_ASK in saved["text"]
    assert _city_row(saved) == CITY_ROW


def test_a_pause_screen_asks_for_the_city_and_offers_no_app(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _command(client, "/log")
    d = _ymd(_today())

    question = _tap(client, f"d1:s:{d}:k")  # sick: "for how many days?"
    paused = _tap(client, f"a1:p:{d}:k:3")

    for body in (question, paused):
        assert CITY_ASK in body["text"]
        assert _city_row(body) == CITY_ROW
        assert not [b for b in _buttons(body) if "web_app" in b]


def test_today_never_asks_for_the_city(client: TestClient) -> None:
    body = _command(client, "/log")

    assert CITY_ASK not in body["text"]
    assert _city_row(body) is None


@pytest.mark.parametrize(
    ("timezone", "home_city"),
    [("Asia/Almaty", None), (None, "-"), ("Asia/Almaty", "almaty")],
    ids=["zone", "not-now", "city"],
)
def test_a_zone_or_a_city_answer_ends_the_question(
    client: TestClient, storage: InMemoryStorage, timezone: str | None, home_city: str | None
) -> None:
    _command(client, "/log")
    [account] = storage.repo.accounts.values()
    storage.repo.accounts[account.id] = replace(account, timezone=timezone, home_city=home_city)

    saved = _tap(client, f"d1:s:{_ymd(_today())}:r")

    assert CITY_ASK not in saved["text"]
    assert _city_row(saved) is None


def test_not_now_lands_on_settings_and_never_asks_again(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _tap(client, f"d1:s:{_ymd(_today())}:r")

    settings = _tap(client, "s1:n")
    again = _tap(client, f"d1:s:{_ymd(_today())}:k")

    assert settings["text"] == "Pick your city here any time.\n\n⚙️ Settings"
    [account] = storage.repo.accounts.values()
    assert account.home_city == "-"
    assert CITY_ASK not in again["text"]


def test_settings_opened_any_other_way_has_no_lead(client: TestClient) -> None:
    body = _tap(client, "s1:v")

    assert body["text"] == "⚙️ Settings"
