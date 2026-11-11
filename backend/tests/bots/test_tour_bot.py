"""The quick tour through the real webhook (UI-02): a carousel edited in place, reached from
/start and /help, and left in one tap back to where it started."""

import itertools
from collections.abc import Iterator
from typing import Any

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tristhana.bots.telegram.tour_callbacks import STEPS, decode, done, step
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


def test_help_keeps_its_text_and_offers_the_tour(client: TestClient) -> None:
    body = _command(client, "/help")

    assert body["text"].startswith("I'm Tristhana")
    assert "/remind: practice reminder" in body["text"]
    assert _rows(body) == [["🧭 Quick tour"]]
    assert _data(body) == [step(1, "h")]


GUIDE = "https://tristhana.app"


def _links(body: Any) -> list[tuple[str, str]]:
    return [
        (b["text"], b["url"])
        for row in body["reply_markup"]["inline_keyboard"]
        for b in row
        if "url" in b
    ]


@pytest.mark.parametrize(
    ("lang", "label", "url"),
    [("en", "📖 Guide", f"{GUIDE}/"), ("ru", "📖 Справка", f"{GUIDE}/ru/")],
)
def test_help_links_to_the_guide_in_the_persons_language(
    storage: InMemoryStorage, lang: str, label: str, url: str
) -> None:
    # UI-05: a trailing slash in the setting doesn't double up.
    with _client(storage, "https://tristhana.web.app", f"{GUIDE}/") as client:
        body = _command(client, "/help", lang)

    assert _rows(body)[-1] == [label]
    assert _links(body) == [(label, url)]
    assert _data(body) == [step(1, "h")]  # the tour stays, above the link


def test_done_from_the_tour_brings_the_guide_link_back(storage: InMemoryStorage) -> None:
    with _client(storage, "https://tristhana.web.app", GUIDE) as client:
        _command(client, "/help")
        body = _tap(client, done("h"))

    assert _links(body) == [("📖 Guide", f"{GUIDE}/")]


def test_the_guide_address_must_be_https() -> None:
    with pytest.raises(ValueError, match="must be an https://"):
        Settings(app_env="test", public_site_url="http://tristhana.app")


def test_start_offers_the_tour_last_and_leaves_the_rest_alone(client: TestClient) -> None:
    rows = _rows(_command(client, "/start"))

    assert rows[0] == ["🧘 Practiced"]
    assert rows[-3] == ["📅 Another day"]
    assert rows[-2] == ["🗣 Русский", "Open the app"]
    assert rows[-1] == ["🧭 Quick tour"]


def test_the_russian_name_is_znakomstvo(client: TestClient) -> None:
    assert _rows(_command(client, "/start", "ru"))[-1] == ["🧭 Знакомство"]


@pytest.mark.parametrize("lang", ["en", "ru"])
@pytest.mark.parametrize("n", range(1, STEPS + 1))
def test_every_step_edits_in_place(client: TestClient, n: int, lang: str) -> None:
    body = _tap(client, step(n, "h"), lang)

    assert body["method"] == "editMessageText"
    assert body["text"].startswith(f"{n} ")  # "2 of 5" / "2 из 5"
    assert "🌸" not in body["text"]


def test_the_first_step_has_no_back(client: TestClient) -> None:
    body = _tap(client, step(1, "s"))

    assert _rows(body) == [["Next ›"], ["✓ Done"]]  # noqa: RUF001
    assert _data(body) == [step(2, "s"), done("s")]


def test_a_middle_step_goes_both_ways(client: TestClient) -> None:
    body = _tap(client, step(3, "h"))

    assert _rows(body) == [["‹ Back", "Next ›"], ["✓ Done"]]  # noqa: RUF001
    assert _data(body) == [step(2, "h"), step(4, "h"), done("h")]


def test_the_last_step_opens_the_app(client: TestClient) -> None:
    body = _tap(client, step(STEPS, "s"))

    assert _rows(body) == [["‹ Back", "✓ Done"], ["Open the app"]]  # noqa: RUF001


def test_the_last_step_without_a_mini_app(storage: InMemoryStorage) -> None:
    with _client(storage, "") as bare:
        assert _rows(_tap(bare, step(STEPS, "s"))) == [["‹ Back", "✓ Done"]]  # noqa: RUF001


def test_done_from_start_is_the_log_grid_again(client: TestClient) -> None:
    body = _tap(client, done("s"))

    assert body["method"] == "editMessageText"
    assert body["text"].startswith("Namaste 🙏")
    assert _rows(body)[0] == ["🧘 Practiced"]


def test_a_status_tap_on_start_still_works_after_the_tour(client: TestClient) -> None:
    grid = _tap(client, done("s"))

    saved = _tap(client, _data(grid)[1])

    assert saved["method"] == "editMessageText"
    assert saved["text"].startswith("✓ Today")


def test_done_from_help_is_the_help_text(client: TestClient) -> None:
    body = _tap(client, done("h"))

    assert body["method"] == "editMessageText"
    assert body["text"].startswith("I'm Tristhana")
    assert _rows(body) == [["🧭 Quick tour"]]


def test_a_step_past_the_end_shows_the_last_one(client: TestClient) -> None:
    body = _tap(client, f"q1:{STEPS + 3}:h")

    assert body["text"] == _tap(client, step(STEPS, "h"))["text"]


@pytest.mark.parametrize(
    "data", ["q1", "q1:", "q1:0:h", "q1:-1:h", "q1:x:h", "q1:1:z", "q1:d:z", "q1:1:h:x", "q1:٣:h"]
)
def test_forged_data_does_nothing(client: TestClient, data: str) -> None:
    assert decode(data) is None
    body = _tap(client, data)

    assert body is None or body.get("method") == "answerCallbackQuery"


def test_callback_data_fits_telegram(client: TestClient) -> None:
    assert all(len(d.encode()) <= 64 for d in (step(STEPS, "s"), done("h")))


def test_a_step_reads_nothing_beyond_the_account(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _command(client, "/start")
    storage.day_repo.down = True  # any day read would now fail

    body = _tap(client, step(2, "s"))

    assert body["method"] == "editMessageText"
