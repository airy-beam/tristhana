"""An explicit Mysuru choice through the real webhook (ID-04 spec §7): the guard in
`bots/telegram/moon.py` (MD-03: picking Mysuru never sets a zone, so its time zone button is never
offered), ✓ on the stored slug, and the same settings line as never having chosen."""

import itertools
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tristhana.domain.accounts import Account
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
_ids = itertools.count(130_000)


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
    s.moon_repo.days_by_location["almaty"] = [MoonDay(soon, MoonDayKind.PURNIMA)]
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


def _user() -> dict[str, Any]:
    return {"id": 42, "is_bot": False, "first_name": "Ash", "language_code": "en"}


def _command(client: TestClient, text: str) -> Any:
    message = {
        "message_id": next(_ids),
        "date": 1_760_000_000,
        "chat": {"id": 42, "type": "private"},
        "from": _user(),
        "text": text,
        "entities": [{"type": "bot_command", "offset": 0, "length": len(text)}],
    }
    return _post(client, {"update_id": next(_ids), "message": message})


def _tap(client: TestClient, data: str) -> Any:
    message = {
        "message_id": 9,
        "date": 1_760_000_000,
        "chat": {"id": 42, "type": "private"},
        "text": "…",
    }
    callback = {
        "id": f"cb{next(_ids)}",
        "from": _user(),
        "chat_instance": "ci",
        "data": data,
        "message": message,
    }
    return _post(client, {"update_id": next(_ids), "callback_query": callback})


def _buttons(body: Any) -> list[dict[str, str]]:
    return [b for row in body["reply_markup"]["inline_keyboard"] for b in row]


def _data(body: Any) -> list[str]:
    return [b["callback_data"] for b in _buttons(body)]


def _store(client: TestClient, storage: InMemoryStorage, slug: str | None) -> Account:
    _command(client, "/moon")
    [account] = storage.repo.accounts.values()
    storage.repo.accounts[account.id] = replace(account, moon_location=slug)
    return storage.repo.accounts[account.id]


def test_a_stored_mysuru_with_no_zone_offers_no_time_zone_button(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _store(client, storage, "mysuru")

    body = _command(client, "/moon")

    assert not [d for d in _data(body) if d.startswith("m1:z:")]


def test_picking_mysuru_offers_no_time_zone_button(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _store(client, storage, "almaty")

    body = _tap(client, "m1:s:mysuru")

    [account] = storage.repo.accounts.values()
    assert account.moon_location == "mysuru"
    assert not [d for d in _data(body) if d.startswith("m1:z:")]


def test_another_city_with_no_zone_still_offers_its_time_zone(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _store(client, storage, "almaty")

    body = _command(client, "/moon")

    assert "m1:z:almaty" in _data(body)


def test_the_picker_marks_mysuru_from_the_stored_slug(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _store(client, storage, "mysuru")

    body = _tap(client, "m1:c:0")

    marked = [b["text"] for b in _buttons(body) if b["text"].startswith("✓")]
    assert marked == ["✓ Mysuru"]


@pytest.mark.parametrize("stored", [None, "mysuru"])
def test_the_settings_line_is_the_same_for_a_choice_and_the_default(
    client: TestClient, storage: InMemoryStorage, stored: str | None
) -> None:
    _store(client, storage, stored)

    body = _command(client, "/settings")

    assert "🌙 Moon days: 📍 Mysuru" in body["text"]
