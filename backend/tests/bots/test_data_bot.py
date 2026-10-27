"""📦 My data in the bot through the real webhook (ST-09, spec §5): the /settings row, D and X
with no statements, the export tap answered with "Preparing…" before the document goes out
and D edited to `export-sent` (or X shown again), too soon = a toast only, the bound
10-minute delete button (a foreign account or a stale minute → X with `delete-expired`,
nothing deleted), a valid one deletes and leaves no keyboard, and the `x1:` codec."""

import itertools
import time
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import FakeNotifier, InMemoryStorage
from tristhana.bots.telegram.data_callbacks import DataCallback, account_tag, decode, encode
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
_ids = itertools.count(95_000)


@pytest.fixture
def outbound(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    sent: list[tuple[str, dict[str, Any]]] = []

    async def record(self: AiohttpSession, bot: object, method: Any, **_: object) -> bool:
        sent.append((method.__api_method__, method.model_dump()))
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)
    return sent


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def client(
    storage: InMemoryStorage, notifier: FakeNotifier, outbound: list[Any]
) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
    )
    with TestClient(create_app(settings, storage, notifier)) as c:
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
    message = {"message_id": 9, "date": 1_760_000_000, "chat": {"id": 42, "type": "private"}}
    callback = {
        "id": f"cb{next(_ids)}",
        "from": _user(),
        "chat_instance": "ci",
        "data": data,
        "message": message | {"text": "…"},
    }
    return _post(client, {"update_id": next(_ids), "callback_query": callback})


def _buttons(body: Any) -> list[dict[str, str]]:
    return [b for row in body["reply_markup"]["inline_keyboard"] for b in row]


def _data(body: Any, text: str) -> str:
    return next(b["callback_data"] for b in _buttons(body) if text in b["text"])


def _answers(outbound: list[tuple[str, dict[str, Any]]]) -> list[str | None]:
    return [m.get("text") for name, m in outbound if name == "answerCallbackQuery"]


def _account_id(storage: InMemoryStorage) -> Any:
    [account] = storage.repo.accounts.values()
    return account.id


def test_settings_has_the_my_data_row(client: TestClient) -> None:
    body = _command(client, "/settings")

    assert _data(body, "📦 My data") == "x1:o"


def test_d_and_x_render_without_reads(client: TestClient, storage: InMemoryStorage) -> None:
    _command(client, "/start")
    _tap(client, "x1:o")  # the middleware's daily profile refresh happens on this one
    before = storage.repo.writes

    d = _tap(client, "x1:o")
    x = _tap(client, _data(d, "Delete my account…"))

    assert d["method"] == "editMessageText"
    assert "Download everything you've logged here" in d["text"]
    assert [b["text"] for b in _buttons(d)] == [
        "⬇️ Download my data",
        "Delete my account…",
        "⚙️ Settings",
    ]
    assert "It can't be undone." in x["text"]
    assert "within 30 days" in x["text"]
    assert [b["text"] for b in _buttons(x)] == [
        "⬇️ Download my data first",
        "Delete everything",
        "📦 My data",
    ]
    assert storage.repo.writes == before  # the middleware's read only
    assert storage.export.claimed == {}


def test_export_answers_first_then_sends_and_edits_d(
    client: TestClient, notifier: FakeNotifier, outbound: list[Any]
) -> None:
    _command(client, "/start")
    outbound.clear()

    body = _tap(client, "x1:e")

    assert _answers(outbound) == ["Preparing your file…"]
    ((recipient, file),) = notifier.exports
    assert recipient.telegram_id == "42"
    assert file.name.startswith("tristhana-export-")
    assert body["method"] == "editMessageText"
    assert body["text"].startswith("📦 Sent below.")
    assert "🌸" not in body["text"]


def test_export_from_x_shows_x_again(client: TestClient, notifier: FakeNotifier) -> None:
    _command(client, "/start")

    body = _tap(client, "x1:e:x")

    assert len(notifier.exports) == 1
    assert body["text"].startswith("📦 Sent below.")
    assert "Delete everything" in [b["text"] for b in _buttons(body)]


def test_too_soon_is_a_toast_only(
    client: TestClient, notifier: FakeNotifier, outbound: list[Any]
) -> None:
    _command(client, "/start")
    _tap(client, "x1:e")
    outbound.clear()

    body = _tap(client, "x1:e")

    assert body is None  # no edit
    assert _answers(outbound) == ["A file was sent a moment ago. Again in 10 min."]
    assert len(notifier.exports) == 1


def test_failed_upload_says_try_again(client: TestClient, notifier: FakeNotifier) -> None:
    from tristhana.application.ports.notifications import DeliveryResult, DeliveryStatus

    _command(client, "/start")
    notifier.export_outcomes.append(DeliveryResult(DeliveryStatus.FAILED))

    body = _tap(client, "x1:e")

    assert body["text"].startswith("Sorry, I've hit a small hiccup")
    assert _tap(client, "x1:e")["text"].startswith("📦 Sent below.")  # the slot was freed


def _confirm(account_id: Any, minutes_ago: int = 0) -> str:
    minute = int(time.time() // 60) - minutes_ago
    return encode(DataCallback("delete", account=account_tag(account_id), minute=minute))


def test_delete_for_another_account_is_refused(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _command(client, "/start")

    body = _tap(client, _confirm(uuid4()))

    assert body["text"].startswith("This button is out of date.")
    assert storage.repo.deleted == []


def test_stale_delete_button_is_refused(client: TestClient, storage: InMemoryStorage) -> None:
    _command(client, "/start")

    body = _tap(client, _confirm(_account_id(storage), minutes_ago=10))

    assert body["text"].startswith("This button is out of date.")
    assert "Delete everything" in [b["text"] for b in _buttons(body)]
    assert storage.repo.deleted == []


def test_valid_delete_removes_the_account_and_the_keyboard(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _command(client, "/start")
    me = _account_id(storage)
    x = _tap(client, "x1:d")

    body = _tap(client, _data(x, "Delete everything"))

    assert storage.repo.deleted == [me]
    assert body["method"] == "editMessageText"
    assert body["text"].startswith("Your account and data are deleted.")
    assert "reply_markup" not in body or body["reply_markup"] is None
    _command(client, "/start")  # writing again starts fresh
    assert _account_id(storage) != me


def test_nine_minute_old_button_still_works(client: TestClient, storage: InMemoryStorage) -> None:
    _command(client, "/start")

    _tap(client, _confirm(_account_id(storage), minutes_ago=9))

    assert len(storage.repo.deleted) == 1


@pytest.mark.parametrize(
    "cb",
    [
        DataCallback("open"),
        DataCallback("export"),
        DataCallback("export", from_delete=True),
        DataCallback("explain"),
        DataCallback("delete", account="0123abcd", minute=29_000_000),
    ],
)
def test_codec_round_trips_within_64_bytes(cb: DataCallback) -> None:
    data = encode(cb)

    assert len(data.encode()) <= 64
    assert decode(data) == cb


@pytest.mark.parametrize(
    "data",
    [
        "",
        "x1",
        "x1:z",
        "x2:o",
        "x1:o:1",
        "x1:e:y",
        "x1:y:0123abcd",
        "x1:y:0123ABCD:a",
        "x1:y:xyz:1",
    ],
)
def test_malformed_is_ignored(data: str) -> None:
    assert decode(data) is None


def test_malformed_tap_answers_and_changes_nothing(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any]
) -> None:
    _command(client, "/start")
    outbound.clear()

    assert _tap(client, "x1:y:zz") is None
    assert _answers(outbound) == [None]
    assert storage.repo.deleted == []


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (None, "sent"),
        ("forbidden", "blocked"),
        ("network", "failed"),
    ],
)
async def test_notifier_uploads_the_document(
    monkeypatch: pytest.MonkeyPatch, error: str | None, status: str
) -> None:
    from datetime import date

    from aiogram.exceptions import TelegramForbiddenError
    from aiogram.methods import SendDocument
    from aiogram.types import BufferedInputFile

    from tests.bots.test_moon_bot import _METHOD, _notifier  # pyright: ignore[reportPrivateUsage]
    from tristhana.application.ports.notifications import ExportFile, Recipient

    raised = {
        None: None,
        "forbidden": TelegramForbiddenError(_METHOD, "bot was blocked by the user"),
        "network": OSError("down"),
    }[error]
    notifier, sent = _notifier(monkeypatch, raised)

    result = await notifier.send_export(
        Recipient("42", "ru"),
        ExportFile("tristhana-export-2026-10-27.zip", b"PK", date(2026, 10, 27)),
    )

    assert result.status.value == status
    (method,) = sent
    assert isinstance(method, SendDocument)
    assert method.chat_id == 42
    assert isinstance(method.document, BufferedInputFile)
    assert method.document.filename == "tristhana-export-2026-10-27.zip"
    assert method.caption is not None
    assert method.caption.startswith("Твои данные из Tristhana на")
    assert "2026" in method.caption
