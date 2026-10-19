"""`/start` through the real webhook (UI-01): one message, today's grid, in-place edits."""

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
from tristhana.bots.telegram.start import decode
from tristhana.domain.days import DayLog, DayStatus
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
ZONE = "Asia/Almaty"
_ids = itertools.count(98_000)


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
        miniapp_url="https://tristhana.web.app",
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


def _today(lang: str = "en") -> date:
    """The provisional "today" (no zone yet): en UTC, ru Moscow."""
    zone = ZoneInfo("Europe/Moscow" if lang == "ru" else "UTC")
    return datetime.now(UTC).astimezone(zone).date()


def test_start_greets_and_asks_about_today_in_one_message(client: TestClient) -> None:
    body = _command(client, "/start")

    assert body["text"].startswith("Namaste 🙏")
    assert "How was today? Practice or rest, both go in your log." in body["text"]
    rows = _rows(body)
    assert rows[0] == ["🧘 Practiced"]
    assert rows[-2] == ["📅 Another day"]
    assert rows[-1] == ["🗣 Русский", "Open the app"]
    data = body["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
    assert data == f"d1:s:{_today():%Y%m%d}:p"  # an absolute date


def test_first_log_is_two_taps_and_edits_in_place(client: TestClient) -> None:
    _command(client, "/start")

    saved = _tap(client, f"d1:s:{_today():%Y%m%d}:r")

    assert saved["method"] == "editMessageText"
    assert saved["text"].startswith("✓ Today")
    assert ["Open the app"] in _rows(saved)  # zone unknown: opening the app records it


def test_returning_start_marks_today(client: TestClient, storage: InMemoryStorage) -> None:
    _command(client, "/start")
    [account] = storage.repo.accounts.values()
    storage.day_repo.rows[(account.id, _today())] = (DayLog(_today(), DayStatus.REST), None)

    body = _command(client, "/start")

    assert "✓ 😌 Rest day" in _texts(body)


def test_language_button_switches_in_place_and_sticks(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _command(client, "/start")

    ru = _tap(client, "o1:l:ru")
    again = _command(client, "/start", "en")

    assert ru["method"] == "editMessageText"
    assert ru["text"].startswith("Намасте 🙏")
    assert _rows(ru)[-1][0] == "🗣 English"
    assert again["text"].startswith("Намасте 🙏")  # chosen: Telegram's English doesn't undo it
    [account] = storage.repo.accounts.values()
    assert account.locale_custom
    assert (account.timezone, account.name_custom) == (None, False)  # only the language


@pytest.mark.parametrize("payload", ["t_abc123", "garbage!!"])
def test_deep_link_payloads_are_ignored(client: TestClient, payload: str) -> None:
    body = _command(client, f"/start {payload}")

    assert body["text"].startswith("Namaste 🙏")


def test_no_app_row_once_the_zone_is_known(client: TestClient, storage: InMemoryStorage) -> None:
    _command(client, "/start")
    [account] = storage.repo.accounts.values()
    storage.repo.accounts[account.id] = replace(account, timezone="UTC")

    saved = _tap(client, f"d1:s:{_today():%Y%m%d}:r")

    assert ["Open the app"] not in _rows(saved)


@pytest.mark.parametrize("data", ["o1", "o1:l", "o1:l:de", "o1:x:en", "o0:l:en"])
def test_malformed_start_callbacks(data: str) -> None:
    assert decode(data) is None


def test_start_in_russian(client: TestClient) -> None:
    body = _command(client, "/start", "ru")

    assert body["text"].startswith("Намасте 🙏")
    assert _rows(body)[0] == ["🧘 Практика"]
    assert _rows(body)[-1] == ["🗣 English", "Открыть приложение"]


def test_forged_language_data_changes_nothing(client: TestClient, storage: InMemoryStorage) -> None:
    _command(client, "/start")

    body = _tap(client, "o1:l:de")

    assert body is None or body.get("method") == "answerCallbackQuery"
    [account] = storage.repo.accounts.values()
    assert (account.locale, account.locale_custom) == ("en", False)


def test_details_screen_offers_the_app_until_the_zone_is_known(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _command(client, "/start")
    d = f"{_today():%Y%m%d}"

    details = _tap(client, f"d1:s:{d}:p")
    [account] = storage.repo.accounts.values()
    storage.repo.accounts[account.id] = replace(account, timezone="UTC")
    again = _tap(client, f"p1:o:{d}")

    assert ["Open the app"] in _rows(details)
    assert ["Open the app"] not in _rows(again)
