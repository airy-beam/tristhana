# ruff: noqa: RUF001
"""Teacher links through the real webhook (ID-04, spec §2, §5, §10): the consent screen on
`/start t_<code>` for a brand-new person, every invite state, the code kept out of every log,
`/teachers` for both sides, main-teacher rules, removal, the invite screen, the QR, the silent
note and the `t1:` callback data. Real use cases over the in-memory port."""

import base64
import importlib.util
import itertools
import logging
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tests.teacher_link_fakes import add_person
from tristhana.domain.accounts import DISPLAY_NAME_MAX, Account
from tristhana.domain.locale import Locale
from tristhana.domain.teacher_links import MAX_STUDENTS, MAX_TEACHERS
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
ME_TG = 42
CODE = "aB3dE6gH9jK2mN5p"
OTHER_CODE = "Zy8xW7vU6tS5rQ4p"
TOOL = Path(__file__).resolve().parents[3] / "tools" / "telegram" / "set_webhook.py"
_ids = itertools.count(120_000)

EN_CONSENT = (
    "🤝 Лена sent you an invite. Add them to your teachers? If you confirm: "
    "• Лена sees your name (Ash) and what you log from today on: practice or rest and your "
    "practice length. "
    "• Лена also sees your last asana as marked in your log. "
    "• All rest you log looks the same, whatever the reason. "
    "• If nothing shows for a while, Лена sees a short note saying just that. "
    "• Any teacher on your list can also mark a new asana for you. "
    "You get a message and can undo it. "
    "• Check-ins, diary notes and the reason for a rest stay private. "
    "• You can remove Лена from your list any time in /teachers. No one gets a message. "
    "Anyone can choose any name here, so confirm only if you know this person. "
    "If you tap Not now, Лена isn't told."
)
RU_CONSENT = (
    "🤝 Лена отправляет тебе приглашение. Добавить в список твоих учителей? Если подтвердить: "
    "• Лена увидит твоё имя (Ash) и то, что ты отмечаешь с сегодняшнего дня: практика или отдых "
    "и объём практики. "
    "• Ещё будет видна твоя последняя асана по отметкам в журнале. "
    "• Любой отмеченный отдых выглядит одинаково, какой бы ни была причина. "
    "• Если какое-то время показать нечего, Лена увидит об этом короткую пометку. "
    "• Любой учитель из твоего списка может отметить тебе новую асану. "
    "Придёт сообщение, и отметку можно отменить. "
    "• Самочувствие, заметки и причина отдыха остаются личными. "
    "• Убрать из списка можно в любой момент в /teachers. Сообщений никто не получит. "
    "Имя здесь может выбрать любой, поэтому подтверждай, только если знаешь этого человека. "
    "Если нажать «Не сейчас», Лена об этом не узнает."
)


@dataclass
class Sent:
    """One Bot API call that went out on its own (not as a webhook reply)."""

    name: str
    fields: dict[str, Any]
    method: Any
    timeout: float | None


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def outbound(storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch) -> list[Sent]:
    sent: list[Sent] = []

    async def record(self: AiohttpSession, bot: object, method: Any, **options: Any) -> bool:
        sent.append(
            Sent(method.__api_method__, method.model_dump(), method, options.get("timeout"))
        )
        storage.teacher_links.writes.append(method.__api_method__)
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)
    return sent


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "test",
        "telegram_bot_token": SecretStr(TOKEN),
        "telegram_webhook_secret": SecretStr(SECRET),
        "miniapp_url": "https://tristhana.web.app",
        "telegram_bot_username": BOT,
    }
    return Settings(**(values | overrides))


@pytest.fixture
def client(storage: InMemoryStorage, outbound: list[Sent]) -> Iterator[TestClient]:
    with TestClient(create_app(_settings(), storage)) as c:
        yield c


def _post(client: TestClient, update: dict[str, Any]) -> Any:
    response = client.post(
        "/telegram/webhook", json=update, headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}
    )
    assert response.status_code == 200
    return response.json() if response.content else None


def _user(lang: str, first_name: str) -> dict[str, Any]:
    return {"id": ME_TG, "is_bot": False, "first_name": first_name, "language_code": lang}


def _command(client: TestClient, text: str, lang: str = "en", first_name: str = "Ash") -> Any:
    message = {
        "message_id": next(_ids),
        "date": 1_760_000_000,
        "chat": {"id": ME_TG, "type": "private"},
        "from": _user(lang, first_name),
        "text": text,
        "entities": [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}],
    }
    return _post(client, {"update_id": next(_ids), "message": message})


def _tap(client: TestClient, data: str, lang: str = "en", first_name: str = "Ash") -> Any:
    message = {"message_id": 9, "date": 1_760_000_000, "chat": {"id": ME_TG, "type": "private"}}
    callback = {
        "id": f"cb{next(_ids)}",
        "from": _user(lang, first_name),
        "chat_instance": "ci",
        "data": data,
        "message": message | {"text": "…"},
    }
    return _post(client, {"update_id": next(_ids), "callback_query": callback})


def _buttons(body: Any) -> list[dict[str, Any]]:
    return [b for row in body["reply_markup"]["inline_keyboard"] for b in row]


def _texts(body: Any) -> list[str]:
    return [b["text"] for b in _buttons(body)]


def _rows(body: Any) -> list[list[str]]:
    return [[b["text"] for b in row] for row in body["reply_markup"]["inline_keyboard"]]


def _data(body: Any, text: str) -> str:
    return next(b["callback_data"] for b in _buttons(body) if text in b["text"])


def _flat(text: str) -> str:
    return " ".join(text.split())


def _today() -> date:
    return datetime.now(UTC).date()  # en: provisional UTC


def _me(client: TestClient, storage: InMemoryStorage) -> Account:
    _command(client, "/start")
    return next(a for a in storage.repo.accounts.values() if a.display_name == "Ash")


def _teacher(
    storage: InMemoryStorage,
    name: str | None = "Лена",
    telegram_id: str = "1001",
    locale: Locale = "en",
    code: str = CODE,
) -> Account:
    teacher = add_person(storage.repo, telegram_id, name, locale)
    storage.teacher_links.codes[teacher.id] = code
    return teacher


def _two_teachers(
    client: TestClient, storage: InMemoryStorage, *, chosen: bool = False
) -> tuple[Account, Account, Account]:
    """`me` with Лена (oldest) and Boris; `chosen` makes Boris the explicit main teacher."""
    me = _me(client, storage)
    first, second = _teacher(storage), _teacher(storage, "Boris", "1002", code=OTHER_CODE)
    storage.teacher_links.add(me.id, first.id)
    storage.teacher_links.add(me.id, second.id, primary=chosen)
    return me, first, second


def _students(
    client: TestClient, storage: InMemoryStorage, n: int
) -> tuple[Account, list[Account]]:
    me = _me(client, storage)
    students = [add_person(storage.repo, f"{2000 + i}", f"Student {i:02d}") for i in range(n)]
    for student in students:
        storage.teacher_links.add(student.id, me.id)
    return me, students


def _note(outbound: list[Sent], chat_id: int) -> Sent:
    [note] = [s for s in outbound if s.name == "sendMessage" and s.fields["chat_id"] == chat_id]
    return note


# The consent screen


@pytest.mark.parametrize(
    ("lang", "consent", "confirm", "other_language", "switch"),
    [
        ("en", EN_CONSENT, "✅ Confirm", "🗣 Русский", "ru"),
        ("ru", RU_CONSENT, "✅ Подтвердить", "🗣 English", "en"),
    ],
)
def test_a_brand_new_person_gets_the_consent_screen_in_their_language(
    client: TestClient,
    storage: InMemoryStorage,
    lang: str,
    consent: str,
    confirm: str,
    other_language: str,
    switch: str,
) -> None:
    teacher = _teacher(storage)

    body = _command(client, f"/start t_{CODE}", lang)

    assert body["method"] == "sendMessage"
    assert _flat(body["text"]) == consent
    decline = "Not now" if lang == "en" else "Не сейчас"
    assert _rows(body) == [[confirm, decline], [other_language]]
    assert _data(body, confirm) == f"t1:a:{CODE}"
    assert _data(body, decline) == "t1:n"
    assert _data(body, other_language) == f"t1:l:{switch}:{CODE}"
    new = [a for a in storage.repo.accounts.values() if a.id != teacher.id]
    assert [a.display_name for a in new] == ["Ash"]  # the account exists, nothing else yet
    assert storage.teacher_links.rows == {}


@pytest.mark.parametrize(
    ("lang", "bare"),
    [
        ("en", "• Лена sees your name and what you log from today on:"),
        ("ru", "• Лена увидит твоё имя и то, что ты отмечаешь с сегодняшнего дня:"),
    ],
)
def test_without_a_name_the_parenthesis_drops_out(
    client: TestClient, storage: InMemoryStorage, lang: str, bare: str
) -> None:
    _teacher(storage)

    body = _command(client, f"/start t_{CODE}", lang, first_name="   ")

    assert bare in _flat(body["text"])
    assert "()" not in body["text"]


def test_a_teacher_without_a_name_is_shown_as_no_name(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _teacher(storage, name=None)

    body = _command(client, f"/start t_{CODE}")

    assert body["text"].startswith("🤝 (no name) sent you an invite.")


def test_the_language_button_keeps_the_invite(client: TestClient, storage: InMemoryStorage) -> None:
    _teacher(storage)
    first = _command(client, f"/start t_{CODE}")

    ru = _tap(client, _data(first, "🗣"))

    assert ru["method"] == "editMessageText"
    assert _flat(ru["text"]) == RU_CONSENT
    assert _data(ru, "✅") == f"t1:a:{CODE}"
    assert _data(ru, "🗣") == f"t1:l:en:{CODE}"
    me = next(a for a in storage.repo.accounts.values() if a.display_name == "Ash")
    assert (me.locale, me.locale_custom) == ("ru", True)  # the same `UpdateProfile` as `o1:`
    assert storage.teacher_links.rows == {}


def test_confirm_edits_into_the_grid_and_the_grid_still_logs(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    teacher = _teacher(storage)
    consent = _command(client, f"/start t_{CODE}")

    body = _tap(client, _data(consent, "✅"))

    assert body["method"] == "editMessageText"
    assert body["text"].startswith("✅ Лена is on your list of teachers now.")
    assert "Namaste 🙏" in body["text"]
    assert "⭐ Make main" not in _texts(body)  # a first link is main by itself
    me = next(a for a in storage.repo.accounts.values() if a.display_name == "Ash")
    assert storage.teacher_links.teachers_of(me.id) == [teacher.id]

    saved = _tap(client, f"d1:s:{_today():%Y%m%d}:r")
    assert saved["text"].startswith("✓ Today")


def test_not_now_stores_nothing_and_messages_no_one(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    _teacher(storage)
    consent = _command(client, f"/start t_{CODE}")

    body = _tap(client, _data(consent, "Not now"))

    assert body["method"] == "editMessageText"
    assert body["text"].startswith("Namaste 🙏")
    assert storage.teacher_links.rows == {}
    assert [s.name for s in outbound] == ["answerCallbackQuery"]


# The other invite states: each the /start grid with one line on top


def _grid_with(body: Any, lead: str) -> None:
    assert body["text"].startswith(lead)
    assert "Namaste 🙏" in body["text"]
    assert "🧘 Practiced" in _texts(body)


def test_an_unknown_code_says_invalid(client: TestClient) -> None:
    body = _command(client, f"/start t_{CODE}")

    _grid_with(body, "This invite link no longer works. The person who shared it can send a new")


def test_ones_own_link_says_so(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    storage.teacher_links.codes[me.id] = CODE

    body = _command(client, f"/start t_{CODE}")

    _grid_with(body, "This is your own invite link: share it with your students.")


def test_an_existing_teacher_says_already(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    teacher = _teacher(storage)
    storage.teacher_links.add(me.id, teacher.id)

    body = _command(client, f"/start t_{CODE}")

    _grid_with(body, "Лена is already on your list of teachers.")


@pytest.mark.parametrize("side", ["mine", "theirs"])
def test_either_cap_says_full(client: TestClient, storage: InMemoryStorage, side: str) -> None:
    me = _me(client, storage)
    teacher = _teacher(storage)
    if side == "mine":
        for _ in range(MAX_TEACHERS):
            storage.teacher_links.add(me.id, uuid4())
    else:
        for _ in range(MAX_STUDENTS):
            storage.teacher_links.add(uuid4(), teacher.id)

    body = _command(client, f"/start t_{CODE}")

    _grid_with(body, "This link can't add a teacher right now.")


def test_a_stale_confirm_after_rotation_says_invalid_and_links_nothing(
    client: TestClient, storage: InMemoryStorage
) -> None:
    teacher = _teacher(storage)
    consent = _command(client, f"/start t_{CODE}")
    storage.teacher_links.codes[teacher.id] = OTHER_CODE

    body = _tap(client, _data(consent, "✅"))

    _grid_with(body, "This invite link no longer works.")
    assert storage.teacher_links.rows == {}


def test_a_second_confirm_says_already_and_notes_once(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    _teacher(storage)
    consent = _command(client, f"/start t_{CODE}")
    _tap(client, _data(consent, "✅"))

    body = _tap(client, _data(consent, "✅"))

    _grid_with(body, "Лена is already on your list of teachers.")
    assert _note(outbound, 1001)


def test_a_forged_confirm_of_ones_own_code_says_own(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    storage.teacher_links.codes[me.id] = CODE

    body = _tap(client, f"t1:a:{CODE}")

    _grid_with(body, "This is your own invite link")
    assert storage.teacher_links.rows == {}


def test_a_confirm_at_the_cap_says_full(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    _teacher(storage)
    for _ in range(MAX_TEACHERS):
        storage.teacher_links.add(me.id, uuid4())

    body = _tap(client, f"t1:a:{CODE}")

    _grid_with(body, "This link can't add a teacher right now.")


@pytest.mark.parametrize("payload", ["t_abc123", "garbage!!", f"s_{CODE}", f"t_{CODE}x"])
def test_any_other_payload_behaves_as_a_plain_start(
    client: TestClient, storage: InMemoryStorage, payload: str
) -> None:
    plain = _command(client, "/start")

    body = _command(client, f"/start {payload}")

    assert body["text"] == plain["text"]
    assert _rows(body) == _rows(plain)
    assert storage.teacher_links.previews == 0


# The code never reaches a log (spec §9)


class _Everything(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(f"{self.format(record)} {record.args!r} {record.__dict__!r}")


@pytest.fixture
def logs(client: TestClient) -> Iterator[list[str]]:
    """Every logger at DEBUG into one handler. After `client`: `configure_logging` replaces the
    root handlers (pytest's caplog handler included) when the app is built."""
    handler = _Everything()
    root = logging.getLogger()
    named = [
        logger
        for logger in logging.Logger.manager.loggerDict.values()
        if isinstance(logger, logging.Logger)
    ]
    levels = [(logger, logger.level) for logger in [root, *named]]
    root.addHandler(handler)
    for logger, _ in levels:
        logger.setLevel(logging.DEBUG)
    yield handler.lines
    root.removeHandler(handler)
    for logger, level in levels:
        logger.setLevel(level)


def _assert_clean(lines: list[str], expected: str) -> None:
    assert any(expected in line for line in lines), "the capture saw nothing: a vacuous pass"
    assert [line for line in lines if CODE in line] == []


def test_the_code_stays_out_of_the_logs_on_start_and_confirm(
    client: TestClient, storage: InMemoryStorage, logs: list[str]
) -> None:
    _teacher(storage)

    consent = _command(client, f"/start t_{CODE}")
    _tap(client, _data(consent, "🗣"))
    _tap(client, _data(consent, "✅"))

    _assert_clean(logs, "reply editMessageText")


def test_the_code_stays_out_of_the_logs_when_a_handler_fails(
    client: TestClient, storage: InMemoryStorage, logs: list[str]
) -> None:
    _teacher(storage)

    storage.teacher_links.fail_with = RuntimeError(f"boom {CODE}")
    _command(client, f"/start t_{CODE}")
    storage.teacher_links.fail_with = RuntimeError(f"boom {CODE}")
    _tap(client, f"t1:a:{CODE}")

    _assert_clean(logs, "telegram handler failed")


@pytest.mark.parametrize(
    "body",
    [
        f'{{"update_id": 1, "message": {{"text": "/start t_{CODE}"',  # not JSON
        f'{{"update_id": "x", "message": {{"text": "/start t_{CODE}"}}}}',  # not an update
    ],
)
def test_the_code_stays_out_of_the_logs_on_a_malformed_body(
    client: TestClient, logs: list[str], body: str
) -> None:
    response = client.post(
        "/telegram/webhook",
        content=body.encode(),
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET, "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    _assert_clean(logs, "malformed body")


# Size


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_the_consent_fits_one_message_with_the_longest_names(
    client: TestClient, storage: InMemoryStorage, lang: str
) -> None:
    longest = "😀" * DISPLAY_NAME_MAX  # two UTF-16 units each, which is what Telegram counts
    _teacher(storage, name=longest)

    body = _command(client, f"/start t_{CODE}", lang, first_name=longest)

    assert longest in body["text"].split("\n")[0]
    assert f"({longest})" in body["text"]
    assert len(body["text"].encode("utf-16-le")) // 2 <= 4096


# Main teacher


def test_a_second_link_offers_make_main_above_the_grid(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    first = _teacher(storage, "Boris", "1002", code=OTHER_CODE)
    storage.teacher_links.add(me.id, first.id)
    second = _teacher(storage)
    consent = _command(client, f"/start t_{CODE}")

    body = _tap(client, _data(consent, "✅"))

    assert body["text"].startswith("✅ Лена is on your list of teachers now.")
    assert _rows(body)[0] == ["⭐ Make main"]
    assert _rows(body)[1] == ["🧘 Practiced"]
    assert _data(body, "⭐ Make main") == f"t1:p:{second.id}"


def test_make_main_after_confirming_moves_the_star_and_ignoring_it_changes_nothing(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me, first, second = _two_teachers(client, storage)

    ignored = _command(client, "/teachers")
    chosen = _tap(client, f"t1:p:{second.id}")

    assert "⭐ Main teacher: Лена (first on your list)" in ignored["text"]
    assert chosen["method"] == "editMessageText"
    assert "⭐ Main teacher: Boris" in chosen["text"]
    assert "first on your list" not in chosen["text"]
    assert storage.teacher_links.rows[(me.id, second.id)].is_primary
    assert not storage.teacher_links.rows[(me.id, first.id)].is_primary


def test_no_star_with_one_teacher(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    teacher = _teacher(storage)
    storage.teacher_links.add(me.id, teacher.id)

    screen = _command(client, "/teachers")
    card = _tap(client, f"t1:c:{teacher.id}")

    assert "Лена" in _texts(screen)
    assert "⭐" not in f"{screen['text']} {_texts(screen)}"
    assert "⭐" not in f"{card['text']} {_texts(card)}"


def test_two_teachers_separate_a_choice_from_the_default(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _two_teachers(client, storage)
    automatic = _command(client, "/teachers")

    assert "⭐ Main teacher: Лена (first on your list)" in automatic["text"]
    assert any("⭐" in t and "Лена" in t for t in _texts(automatic))
    assert not any("⭐" in t and "Boris" in t for t in _texts(automatic))


def test_a_chosen_main_teacher_is_shown_as_chosen(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _two_teachers(client, storage, chosen=True)

    body = _command(client, "/teachers")

    assert "⭐ Main teacher: Boris" in body["text"]
    assert "first on your list" not in body["text"]
    assert any("⭐" in t and "Boris" in t for t in _texts(body))


def test_the_teacher_card_offers_make_main_only_off_the_main(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _, first, second = _two_teachers(client, storage)

    main = _tap(client, f"t1:c:{first.id}")
    other = _tap(client, f"t1:c:{second.id}")

    assert "⭐ Make main" not in _texts(main)
    assert "Remove…" in _texts(main)
    assert "⭐ Make main" in _texts(other)


# Removal


def test_removing_the_main_teacher_names_who_takes_over(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _, first, _ = _two_teachers(client, storage)

    ask = _tap(client, f"t1:u:{first.id}")

    assert "Remove Лена from your teachers?" in ask["text"]
    assert "Boris becomes your main teacher." in ask["text"]


def test_removing_a_teacher_who_isnt_main_names_no_one(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _, _, second = _two_teachers(client, storage)

    ask = _tap(client, f"t1:u:{second.id}")

    assert "becomes your main teacher" not in ask["text"]


def test_removing_a_teacher_takes_one_confirm_and_tells_no_one(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    me = _me(client, storage)
    teacher = _teacher(storage)
    storage.teacher_links.add(me.id, teacher.id)

    ask = _tap(client, f"t1:u:{teacher.id}")
    assert storage.teacher_links.teachers_of(me.id) == [teacher.id]  # asking changes nothing
    assert (
        ask["text"]
        == "Remove Лена from your teachers? They won't get a message, but you'll no longer be on "
        "their list."
    )
    done = _tap(client, _data(ask, "Remove"))

    assert done["method"] == "editMessageText"
    assert storage.teacher_links.teachers_of(me.id) == []
    assert "No teachers on your list. Your log works the same either way." in done["text"]
    assert {s.name for s in outbound} == {"answerCallbackQuery"}


def test_removing_a_student_takes_one_confirm_and_tells_no_one(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    me, [student] = _students(client, storage, 1)

    card = _tap(client, f"t1:v:{student.id}")
    ask = _tap(client, _data(card, "Remove…"))
    assert storage.teacher_links.students_of(me.id) == [student.id]
    assert ask["text"] == "Remove Student 00 from your students? They won't get a message."
    done = _tap(client, _data(ask, "Remove"))

    assert done["method"] == "editMessageText"
    assert storage.teacher_links.students_of(me.id) == []
    assert {s.name for s in outbound} == {"answerCallbackQuery"}


# /teachers for a teacher


def test_students_are_paged_ten_at_a_time(client: TestClient, storage: InMemoryStorage) -> None:
    _students(client, storage, 12)

    first = _tap(client, "t1:s:0")
    second = _tap(client, _data(first, "▶"))

    names = [t for t in _texts(first) if t.startswith("Student")]
    assert len(names) == 10
    assert "◀" not in _texts(first)
    assert [t for t in _texts(second) if t.startswith("Student")] == ["Student 10", "Student 11"]
    assert "▶" not in _texts(second)
    assert _data(second, "◀") == "t1:s:0"


def test_a_stale_page_shows_the_first_one(client: TestClient, storage: InMemoryStorage) -> None:
    """ST-06 §4: an offset past the end has no total, so the bot re-reads page 0."""
    _students(client, storage, 12)

    body = _tap(client, "t1:s:9")

    assert "Student 00" in _texts(body)
    assert "◀" not in _texts(body)


def test_a_teacher_sees_the_count_and_the_plain_invite_button(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _students(client, storage, 12)

    body = _command(client, "/teachers")

    assert "👥 My students (12)" in _texts(body)
    assert "➕ Invite students" in _texts(body)
    assert "I teach: invite students" not in _texts(body)
    assert "Open the app" in _texts(body)


def test_with_no_students_the_i_teach_label_goes_last(
    client: TestClient, storage: InMemoryStorage
) -> None:
    body = _command(client, "/teachers")

    assert _rows(body)[-1] == ["I teach: invite students"]
    assert _data(body, "I teach") == "t1:i"
    assert not any("My students" in t for t in _texts(body))
    assert "➕ Invite students" not in _texts(body)
    assert "No teachers on your list. Your log works the same either way." in body["text"]


def test_with_no_students_in_russian_too(client: TestClient) -> None:
    body = _command(client, "/teachers", "ru")

    assert _rows(body)[-1] == ["Я преподаю: пригласить учеников"]
    assert "Учителей в списке нет. Журнал практики работает и так." in body["text"]


def test_a_teacher_sees_nothing_of_being_main(client: TestClient, storage: InMemoryStorage) -> None:
    me, [student] = _students(client, storage, 1)
    storage.teacher_links.rows[(student.id, me.id)].is_primary = True

    screens = [_command(client, "/teachers"), _tap(client, "t1:s:0")]
    screens.append(_tap(client, f"t1:v:{student.id}"))

    for screen in screens:
        seen = f"{screen['text']} {_texts(screen)}"
        assert "⭐" not in seen
        assert "main" not in seen.lower()


def test_a_student_without_a_name_is_shown_as_no_name(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    nameless = add_person(storage.repo, "2000", None)
    storage.teacher_links.add(nameless.id, me.id)

    body = _tap(client, "t1:s:0")

    assert "(no name)" in _texts(body)


# The invite


def test_the_invite_screen_shows_the_link_and_a_share_button(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    storage.teacher_links.codes[me.id] = CODE
    url = f"https://t.me/{BOT}?start=t_{CODE}"

    body = _tap(client, "t1:i")

    assert url in body["text"]
    assert "Share this link or QR code. Each student confirms for themselves." in body["text"]
    assert body.get("parse_mode") is None
    assert _data(body, "🔳 QR code") == "t1:q"
    assert _data(body, "🔄 New link…") == "t1:w"
    link: str = next(b["url"] for b in _buttons(body) if b["text"] == "📤 Share")
    parts = urlsplit(link)
    query = parse_qs(parts.query)
    assert (parts.netloc, parts.path) == ("t.me", "/share/url")
    assert query["url"] == [url]
    assert query["text"] == [
        "My link to add me as your teacher in Tristhana. The bot shows what I'd see before you "
        "confirm."
    ]


def test_opening_the_invite_twice_keeps_the_link(
    client: TestClient, storage: InMemoryStorage
) -> None:
    first = _tap(client, "t1:i")
    second = _tap(client, "t1:i")

    assert first["text"] == second["text"]
    assert "?start=t_" in first["text"]


def test_a_new_link_takes_one_confirm_and_keeps_the_list(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me, [student] = _students(client, storage, 1)
    storage.teacher_links.codes[me.id] = CODE

    ask = _tap(client, "t1:w")
    assert storage.teacher_links.codes[me.id] == CODE  # asking changes nothing
    assert ask["text"] == (
        "Get a new link? The old link and QR stop working. People already on your list stay."
    )
    done = _tap(client, _data(ask, "🔄 Yes, new link"))

    assert done["method"] == "editMessageText"
    fresh = storage.teacher_links.codes[me.id]
    assert fresh != CODE
    assert f"t_{fresh}" in done["text"]
    assert CODE not in done["text"]
    assert storage.teacher_links.students_of(me.id) == [student.id]


def test_the_qr_is_sent_as_a_png_to_forward(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    me = _me(client, storage)
    storage.teacher_links.codes[me.id] = CODE

    _tap(client, "t1:q")

    [photo] = [s for s in outbound if s.name == "sendPhoto"]
    assert photo.fields["chat_id"] == ME_TG
    assert photo.fields["caption"] == "Scan to add me as your teacher in Tristhana."
    assert photo.method.photo.data.startswith(base64.b64decode("iVBORw0KGgo="))
    assert "answerCallbackQuery" in [s.name for s in outbound]


def test_an_empty_bot_username_hides_the_invite(
    storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    with TestClient(create_app(_settings(telegram_bot_username=""), storage)) as client:
        body = _command(client, "/teachers")

    assert not any("invite" in t.lower() for t in _texts(body))


# The note to the teacher


@pytest.mark.parametrize(
    ("locale", "text", "button"),
    [
        ("en", "👥 Ash is on your list of students now.", "👥 My students"),
        ("ru", "👥 Ash теперь в списке твоих учеников.", "👥 Мои ученики"),
    ],
)
def test_the_note_is_silent_in_the_teachers_language(
    client: TestClient,
    storage: InMemoryStorage,
    outbound: list[Sent],
    locale: Locale,
    text: str,
    button: str,
) -> None:
    _teacher(storage, locale=locale)
    consent = _command(client, f"/start t_{CODE}", "en")

    _tap(client, _data(consent, "✅"))

    note = _note(outbound, 1001)
    assert note.fields["text"] == text
    assert note.fields["disable_notification"] is True
    assert note.timeout == 3
    [[keyboard_button]] = note.fields["reply_markup"]["inline_keyboard"]
    assert keyboard_button["text"].startswith(button)
    assert keyboard_button["callback_data"] == "t1:s:0"


def test_the_note_never_mentions_main(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    _teacher(storage)
    consent = _command(client, f"/start t_{CODE}")

    _tap(client, _data(consent, "✅"))

    words = str(_note(outbound, 1001).fields).lower()
    assert "main" not in words
    assert "⭐" not in words


def test_a_student_without_a_name_is_no_name_in_the_note(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    _teacher(storage)
    consent = _command(client, f"/start t_{CODE}", first_name="   ")

    _tap(client, _data(consent, "✅"), first_name="   ")

    assert _note(outbound, 1001).fields["text"] == "👥 (no name) is on your list of students now."


# Callback data


def test_every_screen_keeps_its_data_short_and_versioned(
    client: TestClient, storage: InMemoryStorage
) -> None:
    """Walks every read-only `t1:` button from /teachers and the consent screen."""
    me, teachers_first, _ = _two_teachers(client, storage)
    for i in range(12):
        storage.teacher_links.add(add_person(storage.repo, f"{3000 + i}", f"S{i}").id, me.id)
    outsider = _teacher(storage, "Clara", "1003", code="Qq1Ww2Ee3Rr4Tt5Y")
    assert outsider.id != teachers_first.id
    consent = _command(client, "/start t_Qq1Ww2Ee3Rr4Tt5Y", "ru")
    safe = ("t1:o", "t1:s", "t1:c", "t1:u", "t1:v", "t1:r", "t1:i", "t1:w")
    seen: set[str] = set()
    todo = [_command(client, "/teachers"), consent]

    while todo:
        screen = todo.pop()
        for data in (b["callback_data"] for b in _buttons(screen) if "callback_data" in b):
            if data in seen or not data.startswith("t1:"):
                continue
            seen.add(data)
            if data.startswith(safe):
                todo.append(_tap(client, data))

    assert {d[:4] for d in seen} >= {"t1:a", "t1:n", "t1:l", "t1:o", "t1:s", "t1:c", "t1:u"}
    assert not [d for d in seen if d.startswith("t1:y")]  # ST-06: no screen offers it any more
    assert {d[:4] for d in seen} >= {"t1:v", "t1:r", "t1:z", "t1:i", "t1:q", "t1:w"}
    assert max(len(d.encode()) for d in seen) <= 46  # ST-06 spec §5; Telegram allows 64


@pytest.mark.parametrize("action", ["c", "p", "u", "x", "v", "r", "z"])
def test_a_forged_uuid_changes_nothing_and_shows_a_list(
    client: TestClient, storage: InMemoryStorage, action: str
) -> None:
    me, first, second = _two_teachers(client, storage)
    stranger = add_person(storage.repo, "9999", "Mallory")
    before = dict(storage.teacher_links.rows)

    body = _tap(client, f"t1:{action}:{stranger.id}")

    assert body["method"] == "editMessageText"
    assert "Mallory" not in body["text"]
    assert storage.teacher_links.rows == before
    assert storage.teacher_links.teachers_of(me.id) == [first.id, second.id]


@pytest.mark.parametrize(
    "data",
    [
        "t1",
        "t1:",
        "t1:y",
        "t1:y:short",
        f"t1:y:{CODE}x",
        "t1:a",
        "t1:a:short",
        f"t1:a:{CODE}x",
        "t1:l:de:" + CODE,
        "t1:l:ru:short",
        "t1:s:x",
        "t1:s:-1",
        "t1:c:not-a-uuid",
        "t1:x:not-a-uuid",
        "t1:zz",
        "t1:q:1",
        "t0:o",
    ],
)
def test_malformed_data_is_only_answered(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent], data: str
) -> None:
    _me(client, storage)

    body = _tap(client, data)

    assert body is None or body.get("method") == "answerCallbackQuery"
    assert "answerCallbackQuery" in [s.name for s in outbound] or body is not None
    assert storage.teacher_links.rows == {}


@pytest.mark.parametrize(
    ("data", "write"),
    [
        (f"t1:a:{CODE}", "accept"),
        ("t1:p:{teacher}", "set_primary"),
        ("t1:x:{teacher}", "unlink"),
    ],
    ids=["confirm", "make-main", "remove"],
)
def test_the_tap_is_answered_before_the_write_finishes(
    client: TestClient, storage: InMemoryStorage, data: str, write: str
) -> None:
    me = _me(client, storage)
    teacher = _teacher(storage)
    if write != "accept":
        storage.teacher_links.add(me.id, teacher.id)
    storage.teacher_links.writes.clear()

    _tap(client, data.format(teacher=teacher.id))

    order = storage.teacher_links.writes
    assert order.index("answerCallbackQuery") < order.index(write)


# Commands


def test_teachers_is_in_the_menu_and_in_help(client: TestClient) -> None:
    spec = importlib.util.spec_from_file_location("set_webhook", TOOL)
    assert spec is not None
    assert spec.loader is not None
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)

    assert "teachers" in tool.COMMANDS
    assert "👥 /teachers: your teachers and students" in _command(client, "/help")["text"]


def test_teachers_in_a_group_is_ignored(client: TestClient) -> None:
    message = {
        "message_id": 1,
        "date": 1_760_000_000,
        "chat": {"id": -100, "type": "group"},
        "from": _user("en", "Ash"),
        "text": "/teachers",
        "entities": [{"type": "bot_command", "offset": 0, "length": 9}],
    }

    assert _post(client, {"update_id": next(_ids), "message": message}) is None


def test_the_note_carries_the_stored_name_over_telegrams(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    _teacher(storage)
    me = _me(client, storage)
    storage.repo.accounts[me.id] = replace(me, display_name="Аша", name_custom=True)

    _tap(client, f"t1:a:{CODE}")

    assert _note(outbound, 1001).fields["text"] == "👥 Аша is on your list of students now."
