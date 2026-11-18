"""`/start` through the real webhook (UI-01, UI-06): the front door once for a person who has
done nothing yet, Today for everyone else and from then on; an invite never shows the front
door, then or later."""

import itertools
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.bots.statements import Statements
from tests.fakes import InMemoryStorage
from tristhana.bots.telegram.start import decode
from tristhana.domain.accounts import Account
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.moon import ShalaMoon, TeacherMoon
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
APP = "https://tristhana.web.app"
OTHER = UUID("33333333-3333-4333-8333-333333333333")  # a teacher's or a shala's id
FRONT = ["🧘 Log my practice", "👥 Invite my students", "🏛 Shala and classes", "🗣 Русский"]
FRONT_RU = [
    "🧘 Отмечать свою практику",
    "👥 Пригласить своих учеников",
    "🏛 Шала и занятия",
    "🗣 English",
]
TODAY_ROWS = [["🧘 Practiced"], ["😌 Rest day"], ["Other…"], ["☰ Menu"]]
HINT = "Everything else is now under ☰ Menu."
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
        telegram_bot_username="tristhana_test_bot",
        miniapp_url=APP,
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
        "entities": [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}],
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


def _data(body: Any) -> list[str | None]:
    return [b.get("callback_data") for row in body["reply_markup"]["inline_keyboard"] for b in row]


def _today(lang: str = "en") -> date:
    """The provisional "today" (no zone yet): en UTC, ru Moscow."""
    zone = ZoneInfo("Europe/Moscow" if lang == "ru" else "UTC")
    return datetime.now(UTC).astimezone(zone).date()


def _me(client: TestClient, storage: InMemoryStorage) -> Account:
    """The account, created by a first contact that is not `/start` (so not yet welcomed)."""
    _command(client, "/moon")
    [account] = storage.repo.accounts.values()
    return account


# The front door (F0)


def test_a_new_person_meets_the_front_door(client: TestClient) -> None:
    body = _command(client, "/start")

    assert body["method"] == "sendMessage"
    assert body["text"].startswith("Namaste 🙏")
    assert body["text"].endswith("Where shall we start?")
    assert _texts(body) == FRONT
    assert _data(body) == ["w1:p", "w1:t", "w1:s:f", "w1:l:ru"]


def test_the_front_door_in_russian(client: TestClient) -> None:
    body = _command(client, "/start", "ru")

    assert body["text"].startswith("Намасте 🙏")
    assert _texts(body) == FRONT_RU
    assert _data(body)[-1] == "w1:l:en"


def test_the_front_door_is_shown_once(client: TestClient, storage: InMemoryStorage) -> None:
    _command(client, "/start")

    again = _command(client, "/start")

    assert _rows(again) == TODAY_ROWS
    assert "Namaste" not in again["text"]
    assert HINT not in again["text"]  # the hint is for people who already used the bot
    [account] = storage.repo.accounts.values()
    assert account.welcomed


def test_the_front_door_costs_one_write_and_no_read(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    _me(client, storage)
    statements = Statements(monkeypatch, storage)

    _command(client, "/start")

    assert statements.names == ["InMemoryAccounts.mark_welcomed"]


def test_the_language_button_stays_on_the_front_door(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _command(client, "/start")

    ru = _tap(client, "w1:l:ru")
    again = _command(client, "/start", "en")

    assert ru["method"] == "editMessageText"
    assert ru["text"].startswith("Намасте 🙏")
    assert _texts(ru) == FRONT_RU
    assert _rows(again)[0] == ["🧘 Практика"]  # chosen: Telegram's English doesn't undo it
    [account] = storage.repo.accounts.values()
    assert account.locale_custom
    assert (account.timezone, account.name_custom) == (None, False)  # only the language


def test_my_practice_on_the_front_door_opens_today_in_place(client: TestClient) -> None:
    _command(client, "/start")

    body = _tap(client, "w1:p")

    assert body["method"] == "editMessageText"
    assert _rows(body) == TODAY_ROWS
    assert "Practice or rest? Both go in your log." in body["text"]


@pytest.mark.parametrize("payload", ["garbage!!", "x_abc"])
def test_an_unknown_payload_is_a_plain_start(client: TestClient, payload: str) -> None:
    body = _command(client, f"/start {payload}")

    assert _texts(body) == FRONT


# Today for people who were here before UI-06


def test_someone_with_a_logged_day_gets_today_with_the_menu_hint_once(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    storage.day_repo.rows[(me.id, _today())] = (DayLog(_today(), DayStatus.REST), None)

    first = _command(client, "/start")
    second = _command(client, "/start")

    assert HINT in first["text"]
    assert "Namaste" not in first["text"]
    assert _rows(first) == [["🧘 Practiced"], ["✓ 😌 Rest day"], ["Other…"], ["☰ Menu"]]
    assert HINT not in second["text"]
    assert _rows(second) == _rows(first)


@pytest.mark.parametrize(
    "role",
    [
        {"teaches": True},
        {"main_teacher": TeacherMoon(OTHER, "Anna", "almaty")},
        {"shala": ShalaMoon(OTHER, "Ashtanga Almaty", "almaty", False, False)},
    ],
    ids=["teacher", "student", "shala"],
)
def test_a_teacher_a_student_or_a_shala_member_never_meets_the_front_door(
    client: TestClient, storage: InMemoryStorage, role: dict[str, Any]
) -> None:
    me = _me(client, storage)
    storage.repo.accounts[me.id] = replace(me, **role)

    body = _command(client, "/start")

    assert HINT in body["text"]
    assert _rows(body)[:3] == TODAY_ROWS[:3]


def test_a_returning_start_is_one_read(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    _command(client, "/start")
    statements = Statements(monkeypatch, storage)

    _command(client, "/start")

    assert statements.count == 1
    assert "mark_welcomed" not in statements.names[0]


# Invites never show the front door


@pytest.mark.parametrize(
    "payload", ["t_AbCdEfGh12345678", "h_ZyXwVuTs87654321", "hs_ZyXwVuTs87654321"]
)
def test_an_invite_start_never_shows_the_front_door_then_or_later(
    client: TestClient, storage: InMemoryStorage, payload: str
) -> None:
    invited = _command(client, f"/start {payload}")  # an unknown code: Today with a line
    later = _command(client, "/start")

    assert "Where shall we start?" not in invited["text"]
    assert _texts(invited)[:1] == ["🧘 Practiced"]
    assert _rows(later) == TODAY_ROWS
    assert "Where shall we start?" not in later["text"]
    [account] = storage.repo.accounts.values()
    assert account.welcomed


# Today after the first log


def test_first_log_from_today_edits_in_place_and_ends_with_the_menu(client: TestClient) -> None:
    _command(client, "/start")
    today = _tap(client, "w1:p")
    assert _data(today)[1] == f"d1:s:{_today():%Y%m%d}:r"  # an absolute date

    saved = _tap(client, f"d1:s:{_today():%Y%m%d}:r")

    assert saved["method"] == "editMessageText"
    assert saved["text"].startswith("✓ Today")
    assert _rows(saved) == [["✏️ Change", "📅 Another day"], ["☰ Menu"]]


def test_returning_start_marks_today(client: TestClient, storage: InMemoryStorage) -> None:
    _command(client, "/start")
    [account] = storage.repo.accounts.values()
    storage.day_repo.rows[(account.id, _today())] = (DayLog(_today(), DayStatus.REST), None)

    body = _command(client, "/start")

    assert "✓ 😌 Rest day" in _texts(body)
    assert "✓ In your log: 😌 Rest day" in body["text"]


def test_no_time_zone_tip_and_no_app_button_on_a_saved_day(
    client: TestClient, storage: InMemoryStorage
) -> None:
    # Q314: the tip left the saved screens, whether the zone is known or not.
    unknown = _tap(client, f"d1:s:{_today():%Y%m%d}:r")
    [account] = storage.repo.accounts.values()
    storage.repo.accounts[account.id] = replace(account, timezone="UTC")
    known = _tap(client, f"d1:s:{_today():%Y%m%d}:r")

    for saved in (unknown, known):
        assert "time zone" not in saved["text"]
        assert "Open the app" not in _texts(saved)


def test_no_app_button_after_practiced_whether_the_zone_is_known_or_not(
    client: TestClient, storage: InMemoryStorage
) -> None:
    # UI-06: the app is under Menu → My practice; the screens after 🧘 stay short. The
    # missing zone is named once, in the reply to the reminder offer (Q314).
    _command(client, "/start")
    d = f"{_today():%Y%m%d}"

    saved = _tap(client, f"d1:s:{d}:p")
    details = _tap(client, f"p1:o:{d}")
    done = _tap(client, f"p1:v:{d}")
    [account] = storage.repo.accounts.values()
    storage.repo.accounts[account.id] = replace(account, timezone="UTC")
    again = _tap(client, f"p1:o:{d}")

    for body in (saved, details, done, again):
        assert "Open the app" not in _texts(body)
        assert "time zone" not in body["text"]
    assert _rows(saved) == [["📝 Add details"], ["✓ Done"]]


# The language button under greetings sent before UI-06 (`o1:l:*`)


def test_an_old_language_button_switches_and_shows_today(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _command(client, "/start")

    ru = _tap(client, "o1:l:ru")

    assert ru["method"] == "editMessageText"
    assert _rows(ru) == [["🧘 Практика"], ["😌 День отдыха"], ["Другое…"], ["☰ Меню"]]
    [account] = storage.repo.accounts.values()
    assert (account.locale, account.locale_custom) == ("ru", True)


@pytest.mark.parametrize("data", ["o1", "o1:l", "o1:l:de", "o1:x:en", "o0:l:en"])
def test_malformed_start_callbacks(data: str) -> None:
    assert decode(data) is None


def test_forged_language_data_changes_nothing(client: TestClient, storage: InMemoryStorage) -> None:
    _command(client, "/start")

    body = _tap(client, "o1:l:de")

    assert body is None or body.get("method") == "answerCallbackQuery"
    [account] = storage.repo.accounts.values()
    assert (account.locale, account.locale_custom) == ("en", False)
