"""Day-status screens through the real webhook (PR-01, PR-04). Outbound Bot API calls (the
parallel answerCallbackQuery) are recorded instead of sent."""

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

from tests.fakes import InMemoryStorage
from tristhana.domain.days import DayStatus
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


def test_log_shows_todays_status_picker(client: TestClient) -> None:
    body = _command(client, "/log")

    assert body["method"] == "sendMessage"
    assert body["text"].startswith("Today, ")
    texts = [b["text"] for b in _buttons(body)]
    assert texts == [
        "🧘 Practiced",
        "😌 Rest day",
        "🌙 Moon day",
        "🌸 Ladies' holiday",
        "🤒 Sick / injury",
        "✈️ Travel",
        "🌱 No practice",
        "📅 Another day",
    ]
    assert all(len(b["callback_data"].encode()) <= 64 for b in _buttons(body))


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

    texts = [b["text"] for b in _buttons(body)]
    assert body["text"].startswith("Yesterday, ")
    assert "✓ 🌙 Moon day" in texts
    assert "Clear" in texts


def test_clear(client: TestClient, storage: InMemoryStorage) -> None:
    today = _today()
    _tap(client, f"d1:s:{_ymd(today)}:r")

    body = _tap(client, f"d1:x:{_ymd(today)}")

    assert storage.day_repo.rows == {}
    assert body["text"].startswith("Cleared: Today, ")


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

    assert body["text"].startswith("That day hasn't come yet in your time zone.")
    assert _buttons(body)[0]["text"].startswith("🌙 Today")  # the real week, not blanks
    assert len(storage.day_repo.rows) == 1


def test_week_never_pages_before_2000(client: TestClient) -> None:
    body = _tap(client, "d1:w:20000103")

    data = [b["callback_data"] for b in _buttons(body)]
    days = [b for b in _buttons(body) if b["callback_data"].startswith("d1:o:")]
    assert [b["callback_data"] for b in days] == ["d1:o:20000103", "d1:o:20000102", "d1:o:20000101"]
    assert data[3:] == ["d1:w:20000110"]  # "Later" only, no "Earlier"
    assert all(" 2000" in b["text"] for b in days)  # another year: shown with the year


def test_clear_does_not_read_the_day_back(
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

    assert reads == []
    assert "Clear" not in [b["text"] for b in _buttons(body)]


def test_zone_hint_only_while_the_zone_is_unknown(
    client: TestClient, storage: InMemoryStorage
) -> None:
    unknown = _tap(client, f"d1:s:{_ymd(_today())}:p")
    [account] = storage.repo.accounts.values()
    storage.repo.accounts[account.id] = replace(account, timezone="UTC")

    known = _tap(client, f"d1:s:{_ymd(_today())}:p")

    assert "open the app once" in unknown["text"]
    assert "open the app once" not in known["text"]


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
