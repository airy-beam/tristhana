# ruff: noqa: RUF001
"""Shalas through the real webhook (SC-01 spec §2, §5, §7, §8): both consents in both
languages, no person in a preview, every state line, ✅ edits into the card, a used or
expired staff link, the card per role, remove and leave with one confirm each, forged ids,
the silent staff note, `/teachers` rows, the moon picker's 🏛 row (`m1:h`), every `h1:` datum
within 64 bytes, answered before the write, and no code in any log. Real use cases over the
in-memory port."""

import itertools
import logging
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tests.moon_follow_fakes import person
from tests.shala_fakes import shala_storage
from tristhana.bots.telegram.shalas_callbacks import short_id
from tristhana.domain.accounts import Account
from tristhana.domain.locale import Locale
from tristhana.domain.moon import FOLLOW_SHALA
from tristhana.domain.shalas import MAX_STUDENTS, ShalaRole
from tristhana.infrastructure.i18n.fluent import FluentTranslator
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
ME_TG = 42
JOIN = "J0inC0deJ0inC0de"
STAFF = "St4ffC0deSt4ffC0"
_ids = itertools.count(150_000)

EN_JOIN = (
    "🏛 Join Ashtanga Almaty (📍 Almaty)? "
    "If you join: "
    "• The shala's teachers and staff see your name (Ash). Nothing from your log. "
    "• The shala's staff can send announcements to members through the bot. You can mute them. "
    "• Your moon days follow the shala's calendar, unless you've chosen a city, or your "
    "teacher has. If your teacher teaches here, the shala's calendar comes first. "
    "• The shala's staff can mark that you came to a class, and so can you. You see these marks "
    "and can remove them any time. "  # SC-05 (Q190)
    "• You can leave any time in /teachers. No one gets a message. "
    "Join only a shala you know: anyone can create one with any name."
)
RU_JOIN = (
    "🏛 Присоединиться к шале Ashtanga Almaty (📍 Алматы)? "
    "Если присоединиться: "
    "• Преподаватели и сотрудники шалы увидят твоё имя (Ash). Ничего из журнала. "
    "• Сотрудники шалы могут отправлять участникам объявления через бота. Их можно отключить. "
    "• Лунные дни будут считаться по календарю шалы, если город не выбран ни тобой, ни твоим "
    "учителем. Если учитель преподаёт в этой шале, календарь шалы важнее. "
    "• Посещение занятий могут отмечать сотрудники шалы, и ты тоже. Эти отметки видны тебе, и их "
    "можно снять в любой момент. "  # SC-05 (Q190)
    "• Выйти можно в любой момент в /teachers. Сообщений никто не получит. "
    "Присоединяйся только к знакомой шале: создать шалу с любым названием может кто угодно."
)
EN_STAFF = (
    "🏛 Anna invites you to Ashtanga Almaty as Assistant. "
    "If you confirm: "
    "• Everyone in the shala, students included, sees your name (Ash) and role. "
    "• You'll see the names of its students and staff, not their logs. "
    "• The shala's announcements come to you through the bot too. You can mute them. "
    "• You can mark who came to its classes. "  # SC-05 (Q190)
    "• You can leave any time in /teachers."
)
RU_STAFF = (
    "🏛 Anna приглашает тебя в шалу Ashtanga Almaty. Роль: Ассистент. "
    "Если подтвердить: "
    "• Все в шале, включая учеников, увидят твоё имя (Ash) и роль. "
    "• Тебе будут видны имена учеников и сотрудников, но не их журналы. "
    "• Объявления шалы тоже будут приходить тебе через бота. Их можно отключить. "
    "• Можно отмечать посещение занятий. "  # SC-05 (Q190)
    "• Выйти можно в любой момент в /teachers."
)


@dataclass
class Sent:
    name: str
    fields: dict[str, Any]


@pytest.fixture
def storage() -> InMemoryStorage:
    return shala_storage()


@pytest.fixture
def outbound(storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch) -> list[Sent]:
    sent: list[Sent] = []

    async def record(self: AiohttpSession, bot: object, method: Any, **options: Any) -> bool:
        sent.append(Sent(method.__api_method__, method.model_dump()))
        storage.shalas.writes.append(method.__api_method__)
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)
    return sent


@pytest.fixture
def client(storage: InMemoryStorage, outbound: list[Sent]) -> Iterator[TestClient]:
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
        miniapp_url="https://tristhana.web.app",
        telegram_bot_username=BOT,  # pyright: ignore[reportCallIssue]
    )
    with TestClient(create_app(settings, storage)) as c:
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
    return [b for row in body.get("reply_markup", {}).get("inline_keyboard", []) for b in row]


def _texts(body: Any) -> list[str]:
    return [b["text"] for b in _buttons(body)]


def _rows(body: Any) -> list[list[str]]:
    return [[b["text"] for b in row] for row in body["reply_markup"]["inline_keyboard"]]


def _data(body: Any, text: str) -> str:
    return next(b["callback_data"] for b in _buttons(body) if text in b["text"])


def _flat(text: str) -> str:
    return " ".join(text.split())


def _t(key: str, locale: Locale = "en", **args: str | int) -> str:
    return _flat(FluentTranslator().t(locale, key, **args))


def _me(client: TestClient, storage: InMemoryStorage, lang: str = "en") -> Account:
    _command(client, "/start", lang)
    return next(a for a in storage.repo.accounts.values() if a.display_name == "Ash")


def _owner(storage: InMemoryStorage, name: str = "Anna", locale: Locale = "en") -> Account:
    return person(storage, "1001", name, locale=locale)


def _shala(storage: InMemoryStorage, owner: Account, name: str = "Ashtanga Almaty") -> UUID:
    return storage.shalas.add_shala(owner.id, name, "almaty", code=JOIN).id


def _invite(storage: InMemoryStorage, shala: UUID, role: ShalaRole = ShalaRole.ASSISTANT) -> None:
    storage.shalas.add_invite(shala, STAFF, role)


def _note(outbound: list[Sent], chat_id: int) -> Sent:
    [note] = [s for s in outbound if s.name == "sendMessage" and s.fields["chat_id"] == chat_id]
    return note


# The student consent (`/start h_<code>`)


@pytest.mark.parametrize(
    ("lang", "consent", "other_language", "switch"),
    [("en", EN_JOIN, "🗣 Русский", "ru"), ("ru", RU_JOIN, "🗣 English", "en")],
)
def test_a_brand_new_person_gets_the_join_consent_in_their_language(
    client: TestClient,
    storage: InMemoryStorage,
    lang: str,
    consent: str,
    other_language: str,
    switch: str,
) -> None:
    shala = _shala(storage, _owner(storage))

    body = _command(client, f"/start h_{JOIN}", lang)

    assert body["method"] == "sendMessage"
    assert _flat(body["text"]) == consent
    assert "parse_mode" not in body or body["parse_mode"] is None  # names are plain text
    datas = [b["callback_data"] for b in _buttons(body)]
    assert datas == [f"h1:a:{JOIN}", "h1:n", f"h1:l:{switch}:{JOIN}"]
    assert _texts(body)[2] == other_language
    if lang == "en":
        assert _texts(body)[:2] == ["✅ Join", "Not now"]
    assert storage.shalas.students_of(shala) == []


def test_the_preview_shows_no_person(client: TestClient, storage: InMemoryStorage) -> None:
    owner = _owner(storage, "Secret Owner")
    shala = _shala(storage, owner)
    storage.shalas.add_staff(shala, person(storage, "1002", "Secret Staff").id, ShalaRole.TEACHER)
    storage.shalas.add_student(shala, person(storage, "1003", "Secret Student").id)

    body = _command(client, f"/start h_{JOIN}")

    assert "Secret" not in body["text"]
    assert all("Secret" not in t for t in _texts(body))


def test_join_edits_into_the_card(client: TestClient, storage: InMemoryStorage) -> None:
    owner = _owner(storage)
    shala = _shala(storage, owner)
    consent = _command(client, f"/start h_{JOIN}")

    body = _tap(client, _data(consent, "✅"))

    assert body["method"] == "editMessageText"
    text = body["text"]
    assert text.splitlines()[0] == "🏛 Ashtanga Almaty"
    assert "📍 Almaty · shala time: Almaty (UTC+5)" in text
    assert "🌙 Moon days: 📍 Almaty" in text
    assert "Anna" in text  # a member sees the staff
    me = next(a for a in storage.repo.accounts.values() if a.display_name == "Ash")
    assert storage.shalas.students_of(shala) == [me.id]
    assert storage.teacher_links.rows == {}  # no teacher link


def test_not_now_stores_nothing_and_messages_no_one(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    shala = _shala(storage, _owner(storage))
    consent = _command(client, f"/start h_{JOIN}")

    body = _tap(client, _data(consent, "Not now"))

    assert body["method"] == "editMessageText"
    assert storage.shalas.students_of(shala) == []
    assert [s.name for s in outbound] == ["answerCallbackQuery"]


def test_a_student_join_sends_no_note(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    """Q105: a room scanning a QR would flood the owner."""
    _shala(storage, _owner(storage))

    _tap(client, f"h1:a:{JOIN}")

    assert [s for s in outbound if s.name == "sendMessage"] == []


def test_the_language_button_keeps_the_code(client: TestClient, storage: InMemoryStorage) -> None:
    _shala(storage, _owner(storage))
    first = _command(client, f"/start h_{JOIN}")

    ru = _tap(client, _data(first, "🗣"))

    assert ru["method"] == "editMessageText"
    assert _flat(ru["text"]) == RU_JOIN
    assert _data(ru, "✅") == f"h1:a:{JOIN}"


def _state_text(client: TestClient) -> str:
    body = _command(client, f"/start h_{JOIN}")
    assert "✅ Join" not in _texts(body)
    return body["text"]


def test_every_join_state_has_its_own_line(client: TestClient, storage: InMemoryStorage) -> None:
    owner = _owner(storage)
    texts: dict[str, str] = {"invalid": _state_text(client)}
    me = _me(client, storage)
    shala = _shala(storage, owner)
    storage.shalas.add_student(shala, me.id)
    texts["already"] = _state_text(client)
    storage.shalas.students_rows.clear()
    storage.shalas.add_staff(shala, me.id, ShalaRole.TEACHER)
    texts["staff"] = _state_text(client)
    storage.shalas.staff.pop((shala, me.id))
    for _ in range(MAX_STUDENTS):
        storage.shalas.add_student(shala, person(storage, f"x{next(_ids)}").id)
    texts["full"] = _state_text(client)

    firsts = {state: text.splitlines()[0] for state, text in texts.items()}
    assert len(set(firsts.values())) == 4, firsts
    assert _t("shala-invalid") in _flat(texts["invalid"])


def test_a_stale_join_after_rotation_says_invalid(
    client: TestClient, storage: InMemoryStorage
) -> None:
    shala = _shala(storage, _owner(storage))
    consent = _command(client, f"/start h_{JOIN}")
    storage.shalas.shalas[shala].join_code = "R0tat3dR0tat3dXy"

    body = _tap(client, _data(consent, "✅"))

    assert _t("shala-invalid") in _flat(body["text"])
    assert storage.shalas.students_of(shala) == []


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_long_names_still_fit_one_message(
    client: TestClient, storage: InMemoryStorage, lang: str
) -> None:
    owner = _owner(storage, "O" * 64)
    shala = storage.shalas.add_shala(owner.id, "Ш" * 64, "almaty", code=JOIN).id
    _invite(storage, shala)

    join = _command(client, f"/start h_{JOIN}", lang, first_name="A" * 64)
    staff = _command(client, f"/start hs_{STAFF}", lang, first_name="A" * 64)

    assert len(join["text"]) <= 4096
    assert len(staff["text"]) <= 4096


# The staff consent (`/start hs_<code>`)


@pytest.mark.parametrize(("lang", "consent"), [("en", EN_STAFF), ("ru", RU_STAFF)])
def test_the_staff_consent_in_both_languages(
    client: TestClient, storage: InMemoryStorage, lang: Locale, consent: str
) -> None:
    shala = _shala(storage, _owner(storage))
    _invite(storage, shala, ShalaRole.ASSISTANT)

    body = _command(client, f"/start hs_{STAFF}", lang)

    assert _flat(body["text"]).startswith(consent)
    assert _t("shala-know-them", lang) in _flat(body["text"])  # on every join screen
    assert _data(body, "✅") == f"h1:b:{STAFF}"
    assert storage.shalas.staff_of(shala) == [storage.shalas.shalas[shala].owner_id]


def test_staff_accept_edits_into_the_card_and_notes_the_inviter_silently(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    owner = person(storage, "1001", "Anna", locale="ru")
    shala = _shala(storage, owner)
    _invite(storage, shala, ShalaRole.ASSISTANT)
    consent = _command(client, f"/start hs_{STAFF}")

    body = _tap(client, _data(consent, "✅"))

    assert body["method"] == "editMessageText"
    assert body["text"].splitlines()[0] == "🏛 Ashtanga Almaty"
    note = _note(outbound, 1001)
    assert note.fields["text"] == "🏛 Ash теперь в шале Ashtanga Almaty. Роль: Ассистент."
    assert note.fields["disable_notification"] is True
    me = next(a for a in storage.repo.accounts.values() if a.display_name == "Ash")
    assert storage.shalas.membership(shala, me.id).roles == frozenset({ShalaRole.ASSISTANT})  # type: ignore[union-attr]


@pytest.mark.parametrize("how", ["used", "expired"])
def test_a_used_or_expired_staff_link_says_invalid(
    client: TestClient, storage: InMemoryStorage, how: str
) -> None:
    shala = _shala(storage, _owner(storage))
    if how == "used":
        _invite(storage, shala)
        storage.shalas.add_staff(shala, person(storage, "1009", "First").id, ShalaRole.TEACHER)
        del storage.shalas.invites[STAFF]
    else:
        storage.shalas.add_invite(shala, STAFF, expires_at=datetime.now(UTC) - timedelta(seconds=1))
    storage.repo.clock.instant = datetime.now(UTC)

    start = _command(client, f"/start hs_{STAFF}")
    tap = _tap(client, f"h1:b:{STAFF}")

    for body in (start, tap):
        assert _t("shala-invalid") in _flat(body["text"])
        assert "✅" not in "".join(_texts(body))


def test_staff_accept_by_a_never_chose_teacher_offers_keep(
    client: TestClient, storage: InMemoryStorage
) -> None:
    """Q98: their own students won't inherit the shala city, so `m1:k:<slug>` is offered."""
    me = _me(client, storage)
    storage.teacher_links.add(person(storage, "2001", "Student").id, me.id)
    shala = storage.shalas.add_shala(_owner(storage).id, "Moscow Shala", "moscow", code=JOIN).id
    _invite(storage, shala, ShalaRole.TEACHER)

    body = _tap(client, f"h1:b:{STAFF}")

    assert "m1:k:moscow" in [b.get("callback_data") for b in _buttons(body)]


# The card per role


def _open_card(client: TestClient, shala: UUID) -> Any:
    return _tap(client, f"h1:c:{short_id(shala)}")


@pytest.mark.parametrize(
    ("role", "students", "invite_students", "invite_staff", "leave"),
    [
        ("owner", True, True, True, False),
        ("admin", True, True, True, True),
        ("teacher", True, True, False, True),
        ("office", True, True, False, True),
        ("student", False, False, False, True),
    ],
)
def test_the_card_per_role(
    client: TestClient,
    storage: InMemoryStorage,
    role: str,
    students: bool,
    invite_students: bool,
    invite_staff: bool,
    leave: bool,
) -> None:
    me = _me(client, storage)
    if role == "owner":
        shala = storage.shalas.add_shala(me.id, "Ashtanga Almaty", "almaty", code=JOIN).id
    else:
        shala = _shala(storage, _owner(storage))
        if role == "student":
            storage.shalas.add_student(shala, me.id)
        else:
            storage.shalas.add_staff(shala, me.id, ShalaRole(role))
    for i in range(3):
        storage.shalas.add_student(shala, person(storage, f"30{i}", f"S{i}").id)

    body = _open_card(client, shala)
    texts = _texts(body)

    assert any(t.startswith("👥 Students") for t in texts) is students
    assert ("➕ Invite students" in texts) is invite_students
    assert ("➕ Invite staff" in texts) is invite_staff
    assert any(t.startswith("Leave") for t in texts) is leave
    assert "S0" not in body["text"]  # students are never listed on the card


def test_the_card_names_roles(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala = _shala(storage, _owner(storage))
    storage.shalas.add_staff(shala, person(storage, "1002", "Boris").id, ShalaRole.TEACHER)
    storage.shalas.add_staff(shala, person(storage, "1003", "Dana").id, ShalaRole.ASSISTANT)
    storage.shalas.add_student(shala, me.id)

    text = _open_card(client, shala)["text"]

    staff_line = next(line for line in text.splitlines() if "Anna" in line)
    assert "Teachers and staff:" in staff_line
    for name, role in (("Anna", "owner"), ("Boris", "teacher"), ("Dana", "assistant")):
        assert name in staff_line
        assert role in staff_line.lower()


def test_the_students_page_is_staff_only(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala = _shala(storage, _owner(storage))
    storage.shalas.add_student(shala, me.id)
    storage.shalas.add_student(shala, person(storage, "2002", "Bea").id)

    body = _tap(client, f"h1:m:{short_id(shala)}:0")

    assert "Bea" not in body["text"]
    assert all("Bea" not in t for t in _texts(body))


def test_staff_page_students(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala = _shala(storage, _owner(storage))
    storage.shalas.add_staff(shala, me.id, ShalaRole.TEACHER)
    storage.shalas.add_student(shala, person(storage, "2002", "Bea").id)

    body = _tap(client, f"h1:m:{short_id(shala)}:0")

    assert "Bea" in body["text"] or "Bea" in _texts(body)


# Remove and leave: one confirm each, silent


def test_leave_is_ask_then_leave(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    me = _me(client, storage)
    shala = _shala(storage, _owner(storage))
    storage.shalas.add_student(shala, me.id)
    card = _open_card(client, shala)

    ask = _tap(client, _data(card, "Leave"))
    assert storage.shalas.membership(shala, me.id) is not None
    done = _tap(client, f"h1:ky:{short_id(shala)}")

    assert _data(card, "Leave") == f"h1:k:{short_id(shala)}"
    assert f"h1:ky:{short_id(shala)}" in [b.get("callback_data") for b in _buttons(ask)]
    assert done["method"] == "editMessageText"
    assert storage.shalas.membership(shala, me.id) is None
    assert [s for s in outbound if s.name == "sendMessage"] == []


def test_the_owner_gets_no_leave_even_by_forged_data(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala = storage.shalas.add_shala(me.id, "Mine", "almaty", code=JOIN).id

    _tap(client, f"h1:ky:{short_id(shala)}")

    assert storage.shalas.membership(shala, me.id) is not None


def test_remove_a_student_is_ask_then_remove(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala = storage.shalas.add_shala(me.id, "Mine", "almaty", code=JOIN).id
    bea = person(storage, "2002", "Bea")
    storage.shalas.add_student(shala, bea.id)

    ask = _tap(client, f"h1:u:{short_id(shala)}:{short_id(bea.id)}")
    assert storage.shalas.membership(shala, bea.id) is not None
    _tap(client, f"h1:x:{short_id(shala)}:{short_id(bea.id)}")

    assert f"h1:x:{short_id(shala)}:{short_id(bea.id)}" in [
        b.get("callback_data") for b in _buttons(ask)
    ]
    assert storage.shalas.membership(shala, bea.id) is None


@pytest.mark.parametrize("action", ["c", "m", "i", "q", "w", "wy", "e", "k", "ky"])
def test_a_forged_shala_id_changes_nothing_and_leaks_nothing(
    client: TestClient, storage: InMemoryStorage, action: str
) -> None:
    _me(client, storage)
    stranger = person(storage, "9999", "Mallory")
    shala = storage.shalas.add_shala(stranger.id, "Hidden Shala", "almaty", code=JOIN).id
    before = (dict(storage.shalas.staff), dict(storage.shalas.students_rows), JOIN)
    suffix = ":0" if action == "m" else ""

    body = _tap(client, f"h1:{action}:{short_id(shala)}{suffix}")

    assert body is None or "Hidden Shala" not in body.get("text", "")
    assert body is None or "Mallory" not in body.get("text", "")
    assert (
        dict(storage.shalas.staff),
        dict(storage.shalas.students_rows),
        storage.shalas.shalas[shala].join_code,
    ) == before
    assert storage.shalas.invites == {}


# Invites from the bot


def test_the_join_link_screen_and_rotate(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala = storage.shalas.add_shala(me.id, "Mine", "almaty", code=JOIN).id

    screen = _tap(client, f"h1:i:{short_id(shala)}")
    _tap(client, f"h1:wy:{short_id(shala)}")

    assert f"https://t.me/{BOT}?start=h_{JOIN}" in str(screen)
    assert storage.shalas.shalas[shala].join_code != JOIN


def test_the_staff_role_picker_offers_manager_only_to_the_owner(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    owned = storage.shalas.add_shala(me.id, "Mine", "almaty", code=JOIN).id
    other = storage.shalas.add_shala(
        _owner(storage).id, "Theirs", "almaty", code="Th3irsC0deTh3irs"
    ).id
    storage.shalas.add_staff(other, me.id, ShalaRole.ADMIN)

    as_owner = [b.get("callback_data") for b in _buttons(_tap(client, f"h1:e:{short_id(owned)}"))]
    as_admin = [b.get("callback_data") for b in _buttons(_tap(client, f"h1:e:{short_id(other)}"))]

    assert f"h1:e:{short_id(owned)}:m" in as_owner
    assert f"h1:e:{short_id(other)}:m" not in as_admin
    assert {f"h1:e:{short_id(other)}:{r}" for r in "tao"} <= set(as_admin)


def test_a_staff_link_from_the_bot_says_once_and_seven_days(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala = storage.shalas.add_shala(me.id, "Mine", "almaty", code=JOIN).id

    body = _tap(client, f"h1:e:{short_id(shala)}:a")

    [code] = list(storage.shalas.invites)
    assert storage.shalas.invites[code].role is ShalaRole.ASSISTANT
    assert f"https://t.me/{BOT}?start=hs_{code}" in str(body)
    assert _t("shala-staff-link-hint", role="Assistant") in _flat(str(body.get("text", "")))


def test_a_forged_manager_invite_by_an_admin_creates_nothing(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala = _shala(storage, _owner(storage))
    storage.shalas.add_staff(shala, me.id, ShalaRole.ADMIN)

    _tap(client, f"h1:e:{short_id(shala)}:m")

    assert storage.shalas.invites == {}


# /teachers and the invite screen


def test_teachers_lists_my_shalas_above_open_the_app(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala = _shala(storage, _owner(storage))
    storage.shalas.add_student(shala, me.id)

    body = _command(client, "/teachers")

    rows = _rows(body)
    shala_row = next(i for i, r in enumerate(rows) if r == ["🏛 Ashtanga Almaty"])
    app_row = next(i for i, r in enumerate(rows) if any("Open the app" in t for t in r))
    assert shala_row < app_row
    assert _data(body, "🏛 Ashtanga Almaty") == f"h1:c:{short_id(shala)}"


def test_the_invite_screen_offers_create_a_shala_in_the_app(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage)

    body = _tap(client, "t1:i")

    [create] = [b for b in _buttons(body) if b["text"] == "🏛 Create a shala"]
    assert "web_app" in create


# Moon: 🏛 Follow my shala (m1:h)


def test_the_picker_offers_follow_my_shala_only_with_a_shala(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    without = _tap(client, "m1:c:0")
    shala = storage.shalas.add_shala(_owner(storage).id, "Moscow Shala", "moscow", code=JOIN).id
    storage.shalas.add_student(shala, me.id)

    with_shala = _tap(client, "m1:c:0")

    assert "m1:h" not in [b.get("callback_data") for b in _buttons(without)]
    assert _data(with_shala, "Follow my shala") == "m1:h"
    assert any("🏛 Follow my shala (Moscow Shala)" in t for t in _texts(with_shala))


def test_follow_my_shala_comes_after_follow_my_teacher(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    storage.teacher_links.add(me.id, person(storage, "1005", "Teacher", moon="almaty").id)
    shala = storage.shalas.add_shala(_owner(storage).id, "Moscow Shala", "moscow", code=JOIN).id
    storage.shalas.add_student(shala, me.id)

    texts = _texts(_tap(client, "m1:c:0"))

    teacher = next(i for i, t in enumerate(texts) if "Follow my teacher" in t)
    shala_i = next(i for i, t in enumerate(texts) if "Follow my shala" in t)
    assert teacher < shala_i


def test_tapping_follow_my_shala_stores_it(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage, "en")
    shala = storage.shalas.add_shala(_owner(storage).id, "Moscow Shala", "moscow", code=JOIN).id
    storage.shalas.add_student(shala, me.id)
    storage.repo.accounts[me.id] = replace(storage.repo.accounts[me.id], moon_location="minsk")

    body = _tap(client, "m1:h")

    assert body["method"] == "editMessageText"
    assert storage.repo.accounts[me.id].moon_location == FOLLOW_SHALA
    assert _t("moon-source-shala", shala="Moscow Shala") in _flat(body["text"])


# Callback data and the order of replies


def test_every_shala_screen_keeps_its_data_within_64_bytes(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala = storage.shalas.add_shala(me.id, "Ш" * 64, "almaty", code=JOIN).id
    for i in range(12):
        storage.shalas.add_student(shala, person(storage, f"40{i:02d}", f"S{i}").id)
        storage.shalas.add_staff(
            shala, person(storage, f"50{i:02d}", f"T{i}").id, ShalaRole.TEACHER
        )
    reads = ("h1:c", "h1:m", "h1:v", "h1:i")  # screens only; `h1:e:<s>` picks, `:<r>` writes
    seen: set[str] = set()
    todo = [_open_card(client, shala), _command(client, "/teachers")]

    while todo:
        screen = todo.pop()
        if screen is None:
            continue
        for data in (b["callback_data"] for b in _buttons(screen) if "callback_data" in b):
            if data in seen or not data.startswith("h1:"):
                continue
            seen.add(data)
            if data.startswith(reads) or (data.startswith("h1:e:") and data.count(":") == 2):
                todo.append(_tap(client, data))

    assert {d[:4] for d in seen} >= {"h1:c", "h1:m", "h1:i", "h1:e"}
    assert max(len(d.encode()) for d in seen) <= 64


@pytest.mark.parametrize(
    ("data", "write"),
    [(f"h1:a:{JOIN}", "join"), (f"h1:b:{STAFF}", "accept_staff"), ("leave", "remove_student")],
    ids=["join", "staff-accept", "leave"],
)
def test_the_tap_is_answered_before_the_write_finishes(
    client: TestClient, storage: InMemoryStorage, data: str, write: str
) -> None:
    me = _me(client, storage)
    shala = _shala(storage, _owner(storage))
    _invite(storage, shala)
    if data == "leave":
        storage.shalas.add_student(shala, me.id)
        data = f"h1:ky:{short_id(shala)}"
    storage.shalas.writes.clear()

    _tap(client, data)

    order = storage.shalas.writes
    assert order.index("answerCallbackQuery") < order.index(write)


# Codes never reach a log


class _Everything(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.setFormatter(logging.Formatter("%(name)s %(levelname)s %(message)s"))
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(f"{self.format(record)} {record.args!r} {record.__dict__!r}")


@pytest.fixture
def logs(client: TestClient) -> Iterator[list[str]]:
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


def test_codes_stay_out_of_the_logs(
    client: TestClient, storage: InMemoryStorage, logs: list[str]
) -> None:
    shala = _shala(storage, _owner(storage))
    _invite(storage, shala)

    _command(client, f"/start h_{JOIN}")
    _tap(client, f"h1:l:ru:{JOIN}")
    _tap(client, f"h1:a:{JOIN}")
    _command(client, f"/start hs_{STAFF}")
    _tap(client, f"h1:b:{STAFF}")

    assert any("editMessageText" in line for line in logs), "the capture saw nothing"
    assert [line for line in logs if JOIN in line or STAFF in line] == []


def test_codes_stay_out_of_the_logs_when_a_handler_fails(
    client: TestClient, storage: InMemoryStorage, logs: list[str]
) -> None:
    _shala(storage, _owner(storage))

    storage.shalas.fail_with = RuntimeError(f"boom {JOIN}")
    _command(client, f"/start h_{JOIN}")
    storage.shalas.fail_with = RuntimeError(f"boom {STAFF}")
    _tap(client, f"h1:b:{STAFF}")

    assert any("telegram handler failed" in line for line in logs), "the capture saw nothing"
    assert [line for line in logs if JOIN in line or STAFF in line] == []
