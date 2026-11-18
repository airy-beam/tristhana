"""The simple journey's own screens through the real webhook (UI-06 §2): what follows the
front door (F1-F3), the Menu for each kind of person (M0), "For teachers and shalas" (M1),
Help (H0), `/menu`, and the Menu as the reply to anything typed. Also the `w1:` codec."""

import itertools
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.bots.statements import Statements
from tests.fakes import InMemoryStorage
from tristhana.bots.telegram import home_callbacks as cb
from tristhana.domain.accounts import Account
from tristhana.domain.moon import ShalaMoon
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
APP = "https://tristhana.web.app"
GUIDE = "https://tristhana.app"
BOT = "tristhana_test_bot"
SHALA = UUID("11111111-1111-4111-8111-111111111111")
MENU = ["☰ Menu"]
BACK = "‹ Back"  # noqa: RUF001
TYPED = "I can't answer messages yet. Here is everything I can do 🙏\n\n☰ Menu"
_ids = itertools.count(260_000)
_OUTBOUND: list[Any] = []


@pytest.fixture
def outbound(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Bot API calls made directly (not as the webhook reply), as aiogram method objects."""
    sent = _OUTBOUND
    sent.clear()

    async def record(self: AiohttpSession, bot: object, method: Any, **_: object) -> bool:
        sent.append(method)
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)
    return sent


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


def _client(
    storage: InMemoryStorage, miniapp_url: str = APP, public_site_url: str = "", bot: str = BOT
) -> TestClient:
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
        telegram_bot_username=bot,
        miniapp_url=miniapp_url,
        public_site_url=public_site_url,
    )
    return TestClient(create_app(settings, storage))


@pytest.fixture
def client(storage: InMemoryStorage, outbound: list[Any]) -> Iterator[TestClient]:
    with _client(storage) as c:
        yield c


def _post(client: TestClient, update: dict[str, Any]) -> Any:
    _OUTBOUND.clear()
    response = client.post(
        "/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}
    )
    assert response.status_code == 200
    return response.json() if response.content else None


def _user(lang: str) -> dict[str, Any]:
    return {"id": 42, "is_bot": False, "first_name": "Ash", "language_code": lang}


def _text(client: TestClient, text: str, lang: str = "en") -> Any:
    message: dict[str, Any] = {
        "message_id": 7,
        "date": 1_760_000_000,
        "chat": {"id": 42, "type": "private"},
        "from": _user(lang),
        "text": text,
    }
    if text.startswith("/"):
        length = len(text.split()[0])
        message["entities"] = [{"type": "bot_command", "offset": 0, "length": length}]
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


def _buttons(body: Any) -> list[dict[str, Any]]:
    return [b for row in body["reply_markup"]["inline_keyboard"] for b in row]


def _rows(body: Any) -> list[list[str]]:
    return [[b["text"] for b in row] for row in body["reply_markup"]["inline_keyboard"]]


def _where(body: Any) -> dict[str, str]:
    """Label → where the button leads: callback data, a URL or a Mini App URL."""
    return {
        b["text"]: b.get("callback_data") or b.get("url") or b["web_app"]["url"]
        for b in _buttons(body)
    }


def _today() -> date:
    return datetime.now(UTC).date()  # no zone yet: provisional UTC for an English client


def _me(client: TestClient, storage: InMemoryStorage, **role: Any) -> Account:
    _text(client, "/moon")  # a first contact
    [account] = storage.repo.accounts.values()
    storage.repo.accounts[account.id] = account = replace(account, **role)
    return account


# The Menu (M0)

NOBODY_MENU = {
    "📝 Today": "w1:n",
    "📊 My practice": f"{APP}?open=practice",
    "🌙 Moon days": "m1:v",
    "🙏 Teacher and shala": "t1:o",
    "⚙️ Settings": "s1:v",
    "❓ Help": "w1:h",
    "For teachers and shalas": "w1:o",
}
STUDENT_AT = ShalaMoon(SHALA, "Ashtanga Almaty", "almaty", False, False)
STAFF_AT = ShalaMoon(SHALA, "Ashtanga Almaty", "almaty", True, False)


def test_the_menu_for_someone_with_no_role(client: TestClient, outbound: list[Any]) -> None:
    body = _tap(client, "w1:m")

    assert [m.__api_method__ for m in outbound] == ["answerCallbackQuery"]
    assert body["method"] == "editMessageText"
    assert body["text"] == "☰ Menu"
    assert _where(body) == NOBODY_MENU
    assert all(len(row) == 1 for row in _rows(body))  # one per row


@pytest.mark.parametrize(
    ("role", "added", "quiet"),
    [
        ({"shala": STUDENT_AT}, {"🗓 My schedule": "c1:m:0:a"}, True),
        ({"teaches": True}, {"👥 My students": "t1:s:0"}, False),
        ({"shala": STAFF_AT}, {"🗓 My schedule": "c1:m:0:a"}, True),  # no students yet: quiet row
        (
            {"teaches": True, "shala": STAFF_AT},
            {"🗓 My schedule": "c1:m:0:a", "👥 My students": "t1:s:0"},
            False,
        ),
    ],
    ids=["shala student", "teacher", "staff", "teacher on a staff"],
)
def test_the_menu_follows_what_the_person_is(
    client: TestClient,
    storage: InMemoryStorage,
    role: dict[str, Any],
    added: dict[str, str],
    quiet: bool,
) -> None:
    _me(client, storage, **role)

    where = _where(_text(client, "/menu"))

    expected = NOBODY_MENU | added
    if not quiet:  # Q310: no students and on no staff
        del expected["For teachers and shalas"]
    assert where == expected
    assert len(where) <= 9  # at most eight rows and the quiet one


def test_the_menu_keeps_its_fixed_order(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage, teaches=True, shala=STAFF_AT)

    assert _rows(_text(client, "/menu")) == [
        ["📝 Today"],
        ["📊 My practice"],
        ["🌙 Moon days"],
        ["🗓 My schedule"],
        ["🙏 Teacher and shala"],
        ["👥 My students"],
        ["⚙️ Settings"],
        ["❓ Help"],
    ]


def test_the_menu_in_russian(client: TestClient) -> None:
    body = _text(client, "/menu", "ru")

    assert body["text"] == "☰ Меню"
    assert _rows(body)[0] == ["📝 Сегодня"]
    assert _rows(body)[-1] == ["Учителям и шалам"]


def test_the_menu_without_a_mini_app_has_no_practice_row(storage: InMemoryStorage) -> None:
    with _client(storage, miniapp_url="") as client:
        body = _text(client, "/menu")

    assert "📊 My practice" not in _where(body)


@pytest.mark.parametrize("send", ["/menu", "w1:m", "hello", "/admin"])
def test_the_menu_costs_no_statement(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch, send: str
) -> None:
    _me(client, storage, teaches=True, shala=STAFF_AT)
    statements = Statements(monkeypatch, storage)

    body = _tap(client, send) if send.startswith("w1") else _text(client, send)

    assert "📝 Today" in _where(body)
    assert statements.names == []


# Anything typed opens the Menu


def test_typed_text_opens_the_menu_with_a_line_on_top(client: TestClient) -> None:
    body = _text(client, "hello")

    assert body["method"] == "sendMessage"
    assert body["text"] == TYPED
    assert _where(body) == NOBODY_MENU


def test_an_unknown_command_is_typed_text_too(client: TestClient) -> None:
    assert _text(client, "/nonsense") == _text(client, "what can you do?")


def test_admin_from_a_non_admin_is_typed_text_byte_for_byte(client: TestClient) -> None:
    # ADR-0042: one function builds both, so the command can't be probed.
    assert _text(client, "/admin") == _text(client, "hello")


# "For teachers and shalas" (M1)


def test_for_teachers_and_shalas(client: TestClient) -> None:
    body = _tap(client, "w1:o")

    assert body["method"] == "editMessageText"
    assert body["text"].startswith("For teachers and shalas\n")
    assert _where(body) == {
        "Invite students": "t1:i",
        "Shala and classes": "w1:s:o",
        "☰ Menu": "w1:m",
    }


# The front door's paths (F1, F2, F3)


def test_invite_on_the_first_run_offers_the_link_and_the_qr_code(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    _me(client, storage)
    statements = Statements(monkeypatch, storage)

    body = _tap(client, "w1:t")

    assert body["method"] == "editMessageText"
    assert body["text"] == (
        "Send your link to your students. Each one confirms for themselves, "
        "and then you see what they share."
    )
    where = _where(body)
    assert list(where) == ["✉️ Send the link", "🔳 QR code", "Continue ›"]  # noqa: RUF001
    assert (where["🔳 QR code"], where["Continue ›"]) == ("t1:q", "w1:c")  # noqa: RUF001
    share = urlsplit(where["✉️ Send the link"])
    assert (share.netloc, share.path) == ("t.me", "/share/url")
    [link] = parse_qs(share.query)["url"]
    assert link.startswith(f"https://t.me/{BOT}?start=t_")
    assert statements.count == 1  # the code: read, or created on the first visit


def test_the_same_invite_link_every_time(client: TestClient) -> None:
    first = _where(_tap(client, "w1:t"))["✉️ Send the link"]
    second = _where(_tap(client, "w1:t"))["✉️ Send the link"]

    assert first == second


def test_invite_then_the_teachers_closing_then_today(client: TestClient) -> None:
    _tap(client, "w1:t")

    closing = _tap(client, "w1:c")
    today = _tap(client, _where(closing)["🧘 Log my own practice"])

    assert "☰ Menu → For teachers and shalas" in closing["text"]  # where the link is now
    assert "☰ Menu → 👥 My students" in closing["text"]  # where students will appear
    assert _where(closing) == {
        "🧘 Log my own practice": "w1:n",
        "Shala and classes": "w1:s:c",
        "☰ Menu": "w1:m",
    }
    assert _rows(today) == [["🧘 Practiced"], ["😌 Rest day"], ["Other…"], MENU]


def test_invite_without_a_bot_name_goes_to_the_closing_screen(storage: InMemoryStorage) -> None:
    with _client(storage, bot="") as client:  # dev without a bot name: there is no link
        body = _tap(client, "w1:t")

    assert "🧘 Log my own practice" in _where(body)


@pytest.mark.parametrize(("letter", "back"), [("f", "w1:f"), ("o", "w1:o"), ("c", "w1:c")])
def test_shala_and_classes_opens_the_form_and_goes_back_where_it_came_from(
    client: TestClient, letter: str, back: str
) -> None:
    body = _tap(client, f"w1:s:{letter}")

    assert body["method"] == "editMessageText"
    assert "Ask your shala for its link" in body["text"]
    assert _where(body) == {"🏛 Create a shala": f"{APP}?open=new-shala", BACK: back}
    assert "web_app" in _buttons(body)[0]


def test_shala_and_classes_without_a_mini_app_has_only_back(storage: InMemoryStorage) -> None:
    with _client(storage, miniapp_url="") as client:
        body = _tap(client, "w1:s:f")

    assert _rows(body) == [[BACK]]


def test_back_from_shala_and_classes_is_the_front_door_again(client: TestClient) -> None:
    body = _tap(client, "w1:f")

    assert body["text"].endswith("Where shall we start?")
    assert _rows(body)[0] == ["My practice"]


@pytest.mark.parametrize("data", ["w1:m", "w1:o", "w1:h", "w1:c", "w1:f", "w1:s:f"])
def test_the_inner_screens_cost_no_statement(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch, data: str
) -> None:
    _me(client, storage)
    statements = Statements(monkeypatch, storage)

    assert _tap(client, data)["method"] == "editMessageText"
    assert statements.names == []


# Help (H0)


def test_help_is_a_list_of_things_to_do(client: TestClient) -> None:
    body = _text(client, "/help")

    assert body["method"] == "sendMessage"
    assert body["text"] == "❓ Help\nWhat would you like to do?"
    assert _where(body) == {
        "📅 Log another day": f"d1:w:{_today():%Y%m%d}",
        "🔔 Practice reminder": "r1:v",
        "🧘 My asanas": "g1:o",
        "🙏 Add my teacher or shala": "t1:o",
        "For teachers and shalas": "w1:o",
        "☰ Menu": "w1:m",
    }


def test_help_from_the_menu_edits_in_place(client: TestClient) -> None:
    body = _tap(client, "w1:h")

    assert body["method"] == "editMessageText"
    assert body["text"].startswith("❓ Help")


def test_help_names_no_command(client: TestClient) -> None:
    for lang in ("en", "ru"):
        assert "/" not in _text(client, "/help", lang)["text"]


@pytest.mark.parametrize(
    ("lang", "label", "url"),
    [("en", "📖 Guide", f"{GUIDE}/"), ("ru", "📖 Справка", f"{GUIDE}/ru/")],
)
def test_help_links_to_the_guide_in_the_persons_language(
    storage: InMemoryStorage, outbound: list[Any], lang: str, label: str, url: str
) -> None:
    # UI-05: a trailing slash in the setting doesn't double up.
    with _client(storage, public_site_url=f"{GUIDE}/") as client:
        body = _text(client, "/help", lang)

    assert _where(body)[label] == url
    assert [b["text"] for b in _buttons(body)][-2] == label  # above the Menu row
    assert [b for b in _buttons(body) if "url" in b] == [{"text": label, "url": url}]


def test_the_guide_address_must_be_https() -> None:
    with pytest.raises(ValueError, match="must be an https://"):
        Settings(app_env="test", public_site_url="http://tristhana.app")


# Hidden commands still answer (they left the command list, not the bot)


@pytest.mark.parametrize(
    "command", ["/log", "/asanas", "/remind", "/teachers", "/classes", "/menu"]
)
def test_hidden_commands_still_answer_with_their_own_screen(
    client: TestClient, command: str
) -> None:
    body = _text(client, command)

    assert body["method"] == "sendMessage"
    assert body["text"] != TYPED


def test_the_hidden_commands_are_the_ones_the_tool_does_not_list() -> None:
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "tools" / "telegram" / "set_webhook.py"
    spec = importlib.util.spec_from_file_location("set_webhook", path)
    assert spec is not None
    assert spec.loader is not None
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)

    assert tool.COMMANDS == ("start", "schedule", "moon", "settings", "help")
    assert tool.HIDDEN_COMMANDS == ("log", "asanas", "remind", "teachers", "classes", "menu")


def test_schedule_without_a_shala_keeps_its_line_and_gains_the_menu(client: TestClient) -> None:
    body = _text(client, "/schedule")

    assert body["text"].startswith("Your shala's classes appear here once you join.")
    assert _rows(body) == [MENU]


# The `w1:` codec


ALL = [
    cb.MENU,
    cb.TODAY,
    cb.HELP,
    cb.TEACH,
    cb.FRONT,
    cb.PRACTICE,
    cb.INVITE,
    cb.CLOSING,
    cb.shala("f"),
    cb.shala("o"),
    cb.shala("c"),
    cb.language("en"),
    cb.language("ru"),
]


def test_every_new_callback_decodes_and_is_short() -> None:
    assert len(set(ALL)) == len(ALL)
    for data in ALL:
        assert cb.decode(data) is not None
        assert len(data.encode()) <= 22  # spec §2: every new value, well under Telegram's 64


def test_the_codec_round_trips() -> None:
    assert cb.decode(cb.shala("o")) == cb.HomeTap("shala", back="o")
    assert cb.decode(cb.language("ru")) == cb.HomeTap("language", locale="ru")
    assert cb.decode(cb.MENU) == cb.HomeTap("menu")


FORGED = [None, "", "w1", "w1:", "w1:zz", "w1:m:1", "w1:s", "w1:s:x", "w1:l:de", "w1:l", "w2:m"]


@pytest.mark.parametrize("data", FORGED)
def test_malformed_data_decodes_to_nothing(data: str | None) -> None:
    assert cb.decode(data) is None


@pytest.mark.parametrize("data", [d for d in FORGED if d and d.startswith("w1:")])
def test_forged_data_only_answers(
    client: TestClient, storage: InMemoryStorage, outbound: list[Any], data: str
) -> None:
    body = _tap(client, data)

    assert body is None or body.get("method") == "answerCallbackQuery"
    assert [m.__api_method__ for m in outbound] in (["answerCallbackQuery"], [])
    [account] = storage.repo.accounts.values()
    assert (account.locale, account.welcomed) == ("en", False)
