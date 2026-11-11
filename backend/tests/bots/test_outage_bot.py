"""A database outage after the account has loaded (Q48, Q71): every screen answers with the
gentle retry message instead of a tap that looks dead. One catch in the account middleware
covers all handlers, so a new screen gets it for free."""

import itertools
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tristhana.bots.telegram.tour_callbacks import done, step
from tristhana.domain.locale import Locale
from tristhana.infrastructure.i18n.fluent import FluentTranslator
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
_ids = itertools.count(77_000)
DAY = datetime.now(UTC).date().isoformat().replace("-", "")


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Every Bot API call made besides the webhook reply (the callback answer, mostly)."""
    calls: list[Any] = []

    async def record(self: AiohttpSession, bot: object, method: Any, **_: object) -> bool:
        calls.append(method)
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)
    return calls


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def client(storage: InMemoryStorage, sent: list[Any]) -> Iterator[TestClient]:
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


def _text(locale: Locale) -> str:
    return FluentTranslator().t(locale, "error-temporary")


def _answers(sent: list[Any]) -> int:
    return sum(type(m).__name__ == "AnswerCallbackQuery" for m in sent)


TAPS = [
    pytest.param(f"d1:s:{DAY}:p", id="d1 mark a day"),
    pytest.param("d1:t", id="d1 open today"),
    pytest.param(f"p1:c:{DAY}:m", id="p1 practice context"),
    pytest.param("o1:l:en", id="o1 language"),
    pytest.param(done("s"), id="q1 tour Done back to /start"),
    pytest.param(f"k1:m:{DAY}:4", id="k1 check-in"),
    pytest.param(f"n1:o:{DAY}:d", id="n1 diary"),
    pytest.param("g1:o", id="g1 progression"),
]


@pytest.mark.parametrize("data", TAPS)
def test_a_tap_during_an_outage_gets_the_retry_message(
    client: TestClient, storage: InMemoryStorage, sent: list[Any], data: str
) -> None:
    _command(client, "/start")
    sent.clear()
    storage.day_repo.down = True  # the account still loads; every day read or write fails

    body = _tap(client, data)

    # A new message, never an edit: the screen under the finger stays as it was.
    assert body["method"] == "sendMessage"
    assert body["chat_id"] == 42
    assert body["text"] == _text("en")
    assert _answers(sent) >= 1  # the spinner stops


@pytest.mark.parametrize("command", ["/start", "/log", "/asanas"])
def test_a_command_during_an_outage_gets_the_retry_message(
    client: TestClient, storage: InMemoryStorage, command: str
) -> None:
    _command(client, "/help")  # creates the account without reading a day
    storage.day_repo.down = True

    body = _command(client, command)

    assert body["method"] == "sendMessage"
    assert body["text"] == _text("en")


def test_the_retry_message_is_in_the_persons_language(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _command(client, "/start", lang="ru")
    storage.day_repo.down = True

    body = _tap(client, "d1:t", lang="ru")

    assert body["text"] == _text("ru")


def test_a_screen_that_reads_nothing_still_works_during_an_outage(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _command(client, "/start")
    storage.day_repo.down = True

    body = _tap(client, step(2, "s"))

    assert body["method"] == "editMessageText"
