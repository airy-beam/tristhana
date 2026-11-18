"""The bot's quick tour (UI-02) was retired by UI-06. Its buttons are still in chat history,
so each one lands on the nearest living screen (spec §5): "Done" under a tour opened from
/start on Today, everything else on Help. Never a bare answer."""

import itertools
from collections.abc import Iterator
from typing import Any

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tristhana.bots.telegram.tour_callbacks import STEPS, decode
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
_ids = itertools.count(99_000)


@pytest.fixture(autouse=True)
def outbound(monkeypatch: pytest.MonkeyPatch) -> None:
    async def record(self: AiohttpSession, bot: object, method: Any, **_: object) -> bool:
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


def _client(storage: InMemoryStorage, miniapp_url: str, public_site_url: str = "") -> TestClient:
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
        miniapp_url=miniapp_url,
        public_site_url=public_site_url,
    )
    return TestClient(create_app(settings, storage))


@pytest.fixture
def client(storage: InMemoryStorage) -> Iterator[TestClient]:
    with _client(storage, "https://tristhana.web.app") as c:
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


def _rows(body: Any) -> list[list[str]]:
    return [[b["text"] for b in row] for row in body["reply_markup"]["inline_keyboard"]]


def _data(body: Any) -> list[str]:
    return [
        b["callback_data"]
        for row in body["reply_markup"]["inline_keyboard"]
        for b in row
        if "callback_data" in b
    ]


HELP = "❓ Help\nWhat would you like to do?"


@pytest.mark.parametrize("lang", ["en", "ru"])
@pytest.mark.parametrize("origin", ["s", "h"])
@pytest.mark.parametrize("n", range(1, STEPS + 1))
def test_every_old_step_button_opens_help_in_place(
    client: TestClient, n: int, origin: str, lang: str
) -> None:
    body = _tap(client, f"q1:{n}:{origin}", lang)

    assert body["method"] == "editMessageText"
    assert body["text"] == _command(client, "/help", lang)["text"]
    assert _data(body)[-1] == "w1:m"


def test_done_under_a_tour_opened_from_help_is_help(client: TestClient) -> None:
    body = _tap(client, "q1:d:h")

    assert body["method"] == "editMessageText"
    assert body["text"] == HELP


def test_done_under_a_tour_opened_from_start_is_today(client: TestClient) -> None:
    body = _tap(client, "q1:d:s")

    assert body["method"] == "editMessageText"
    assert _rows(body) == [
        ["🧘 Practiced"],
        ["😌 Rest day"],
        ["Other…"],
        ["📅 Another day", "☰ Menu"],
    ]


def test_a_status_tap_still_works_after_an_old_done(client: TestClient) -> None:
    today = _tap(client, "q1:d:s")

    saved = _tap(client, _data(today)[1])

    assert saved["method"] == "editMessageText"
    assert saved["text"].startswith("✓ Today")


def test_the_tour_is_offered_nowhere(client: TestClient) -> None:
    for command in ("/start", "/help", "/menu", "/log"):
        body = _command(client, command)
        assert not [d for d in _data(body) if d.startswith("q1:")]
        assert "🧭" not in str(body)


def test_the_decoder_still_knows_the_six_steps() -> None:
    assert STEPS == 6
    assert decode("q1:9:h") == decode("q1:6:h")  # a step past the end is the last one


@pytest.mark.parametrize(
    "data", ["q1", "q1:", "q1:0:h", "q1:-1:h", "q1:x:h", "q1:1:z", "q1:d:z", "q1:1:h:x", "q1:٣:h"]
)
def test_forged_data_does_nothing(client: TestClient, data: str) -> None:
    assert decode(data) is None
    body = _tap(client, data)

    assert body is None or body.get("method") == "answerCallbackQuery"


def test_an_old_step_reads_nothing_beyond_the_account(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _command(client, "/start")
    storage.day_repo.down = True  # any day read would now fail

    body = _tap(client, "q1:2:s")

    assert body["method"] == "editMessageText"
