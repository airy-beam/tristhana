# ruff: noqa: RUF001
"""MD-02 through the real webhook (spec §2, §7): the source line on /moon in both languages,
"👥 Follow my teacher" in the picker (`m1:f`), the settings line, the lead lines after the
student's own taps, the teacher's shared line and invite hint, the first-student note with
[Keep 📍 …] (`m1:k:<slug>`), forged data, and answering before the write. Real use cases over
the in-memory ports, with the account inputs loaded as the middleware's statement does."""

import asyncio
import itertools
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.fakes import InMemoryStorage
from tests.moon_follow_fakes import following_storage, person
from tristhana.domain.accounts import Account
from tristhana.domain.locale import Locale
from tristhana.domain.moon import FOLLOW_TEACHER, MoonDay, MoonDayKind
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
ME_TG = 42
CODE = "aB3dE6gH9jK2mN5p"
OTHER_CODE = "Zy8xW7vU6tS5rQ4p"
_ids = itertools.count(150_000)

SOURCE_EN = "👥 Same as your main teacher, Anna. You can choose another city."
SOURCE_RU = "👥 Как у основного учителя: Anna. Можно выбрать другой город."
NONE_EN = "👥 Anna hasn't chosen a city yet, so the dates are for 📍 Mysuru for now."
NONE_RU = "👥 У учителя (Anna) пока не выбран город, поэтому даты считаются по городу 📍 Майсур."
CHANGED_ANNA = "🌙 Your moon days now follow Anna: 📍 Almaty. You can change this in /moon."
ENDED = "🌙 Your moon days are now for 📍 Mysuru. You can change this in /moon."
JOINED = "👥 Ash is on your list of students now."
OWN_EN = (
    "🌙 Now that you have students, your moon days follow your own setting: 📍 Mysuru. "
    "To keep 📍 Almaty (as with Maya), tap below."
)
KEPT = "🌙 Done: your moon days stay with 📍 Almaty. You can change this in /moon."


@dataclass
class Sent:
    name: str
    fields: dict[str, Any]


@pytest.fixture
def storage() -> InMemoryStorage:
    s = following_storage()
    soon = datetime.now(UTC).date() + timedelta(days=3)
    for slug, shift in (("mysuru", 0), ("almaty", -1), ("moscow", 1)):
        s.moon_repo.days_by_location[slug] = [
            MoonDay(soon + timedelta(days=shift), MoonDayKind.PURNIMA)
        ]
    return s


@pytest.fixture
def outbound(storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch) -> list[Sent]:
    sent: list[Sent] = []

    async def record(self: AiohttpSession, bot: object, method: Any, **options: Any) -> bool:
        sent.append(Sent(method.__api_method__, method.model_dump()))
        storage.teacher_links.writes.append(method.__api_method__)
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
        telegram_bot_username=BOT,
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
    return {"id": ME_TG, "is_bot": False, "first_name": "Ash", "language_code": lang}


def _command(client: TestClient, text: str, lang: str = "en") -> Any:
    message = {
        "message_id": next(_ids),
        "date": 1_760_000_000,
        "chat": {"id": ME_TG, "type": "private"},
        "from": _user(lang),
        "text": text,
        "entities": [{"type": "bot_command", "offset": 0, "length": len(text.split()[0])}],
    }
    return _post(client, {"update_id": next(_ids), "message": message})


def _tap(client: TestClient, data: str, lang: str = "en", text: str = "…") -> Any:
    message = {
        "message_id": 9,
        "date": 1_760_000_000,
        "chat": {"id": ME_TG, "type": "private"},
        "text": text,
    }
    callback = {
        "id": f"cb{next(_ids)}",
        "from": _user(lang),
        "chat_instance": "ci",
        "data": data,
        "message": message,
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


def _me(
    client: TestClient, storage: InMemoryStorage, moon: str | None = None, lang: str = "en"
) -> Account:
    _command(client, "/start", lang)
    me = next(a for a in storage.repo.accounts.values() if a.display_name == "Ash")
    storage.repo.accounts[me.id] = replace(me, moon_location=moon)
    return storage.repo.accounts[me.id]


def _stored(storage: InMemoryStorage, account: Account) -> str | None:
    return storage.repo.accounts[account.id].moon_location


def _teacher(
    storage: InMemoryStorage,
    name: str = "Anna",
    moon: str | None = "almaty",
    tg: str = "1001",
    code: str = CODE,
    locale: Locale = "en",
) -> Account:
    teacher = person(storage, tg, name, moon=moon, locale=locale)
    storage.teacher_links.codes[teacher.id] = code
    return teacher


def _student_of(storage: InMemoryStorage, teacher: Account, tg: str = "2001") -> Account:
    student = person(storage, tg, "Student")
    storage.teacher_links.add(student.id, teacher.id)
    return student


# /moon: the source line (spec §2).


@pytest.mark.parametrize(
    ("lang", "title", "line"),
    [("en", "🌙 Moon days · 📍 Almaty", SOURCE_EN), ("ru", "📍 Алматы", SOURCE_RU)],
)
def test_moon_names_the_teacher_it_follows(
    client: TestClient, storage: InMemoryStorage, lang: str, title: str, line: str
) -> None:
    me = _me(client, storage, lang=lang)
    storage.teacher_links.add(me.id, _teacher(storage).id)

    body = _command(client, "/moon", lang)

    assert title in body["text"].splitlines()[0]
    assert line in body["text"]


@pytest.mark.parametrize(("lang", "line"), [("en", NONE_EN), ("ru", NONE_RU)])
def test_following_a_teacher_without_a_city_says_so(
    client: TestClient, storage: InMemoryStorage, lang: str, line: str
) -> None:
    me = _me(client, storage, FOLLOW_TEACHER, lang)
    storage.teacher_links.add(me.id, _teacher(storage, moon=None).id)

    body = _command(client, "/moon", lang)

    assert line in body["text"]
    assert "📍 Mysuru" in body["text"] or "📍 Майсур" in body["text"]


@pytest.mark.parametrize(
    ("own", "theirs"),
    [("moscow", "almaty"), (None, None), (None, FOLLOW_TEACHER)],
    ids=["chosen", "teacher-without-city", "one-hop"],
)
def test_no_source_line_unless_following(
    client: TestClient, storage: InMemoryStorage, own: str | None, theirs: str | None
) -> None:
    me = _me(client, storage, own)
    storage.teacher_links.add(me.id, _teacher(storage, moon=theirs).id)

    body = _command(client, "/moon")

    assert "👥" not in body["text"]


def test_use_city_time_is_only_offered_for_a_chosen_city(
    client: TestClient, storage: InMemoryStorage
) -> None:
    """A teacher's city is not where the student lives (MD-04 Q3); no zone is known here."""
    me = _me(client, storage)
    storage.teacher_links.add(me.id, _teacher(storage).id)

    following = _command(client, "/moon")
    storage.repo.accounts[me.id] = replace(storage.repo.accounts[me.id], moon_location="almaty")
    chosen = _command(client, "/moon")

    assert not any("🕐" in t for t in _texts(following))
    assert any("🕐" in t for t in _texts(chosen))


# The picker: 👥 Follow my teacher (m1:f).


def test_the_picker_offers_follow_my_teacher_first_with_a_main_teacher(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    storage.teacher_links.add(me.id, _teacher(storage).id)

    picker = _tap(client, "m1:c:0")

    first = _rows(picker)[0]
    assert len(first) == 1
    assert "👥 Follow my teacher (Anna)" in first[0]
    assert _data(picker, "Follow my teacher") == "m1:f"
    assert first[0].startswith("✓")  # the effective source is the teacher
    assert [t for t in _texts(picker) if t.startswith("✓")] == [first[0]]  # one tick


def test_the_follow_row_comes_before_same_as_my_city(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage, "moscow")
    storage.repo.accounts[me.id] = replace(
        storage.repo.accounts[me.id], timezone="Asia/Almaty", home_city="astana"
    )
    storage.teacher_links.add(me.id, _teacher(storage).id)

    picker = _tap(client, "m1:c:0")

    assert "Follow my teacher" in _rows(picker)[0][0]
    assert not _rows(picker)[0][0].startswith("✓")  # a chosen city: no tick on the row
    assert "Same as my city" in _rows(picker)[1][0]


def test_follow_chosen_ticks_the_row_even_without_a_teacher_city(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage, FOLLOW_TEACHER)
    storage.teacher_links.add(me.id, _teacher(storage, moon=None).id)

    picker = _tap(client, "m1:c:0")

    assert _rows(picker)[0][0].startswith("✓")
    assert "✓ Mysuru" not in _texts(picker)


def test_no_follow_row_without_a_teacher(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage, FOLLOW_TEACHER)

    picker = _tap(client, "m1:c:0")

    assert not any("Follow my teacher" in t for t in _texts(picker))
    assert "m1:f" not in [b["callback_data"] for b in _buttons(picker)]


@pytest.mark.parametrize("lang", ["en", "ru"])
def test_the_follow_row_in_russian_and_english(
    client: TestClient, storage: InMemoryStorage, lang: str
) -> None:
    me = _me(client, storage, "moscow", lang)
    storage.teacher_links.add(me.id, _teacher(storage).id)

    picker = _tap(client, "m1:c:0", lang)

    label = "👥 Follow my teacher (Anna)" if lang == "en" else "👥 Как у учителя (Anna)"
    assert _rows(picker)[0] == [label]


def test_tapping_follow_stores_it_and_shows_the_teachers_calendar(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage, "moscow")
    storage.teacher_links.add(me.id, _teacher(storage).id)

    body = _tap(client, "m1:f")

    assert body["method"] == "editMessageText"
    assert body["text"].startswith("🌙 Moon days · 📍 Almaty")
    assert SOURCE_EN in body["text"]
    assert _stored(storage, me) == FOLLOW_TEACHER


def test_follow_data_is_short(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    storage.teacher_links.add(me.id, _teacher(storage).id)

    picker = _tap(client, "m1:c:0")

    assert all(len(b["callback_data"].encode()) <= 64 for b in _buttons(picker))


def test_the_sentinel_as_a_city_slug_rerenders_and_writes_nothing(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage, "moscow")

    body = _tap(client, f"m1:s:{FOLLOW_TEACHER}")

    assert body["text"].startswith("🌙 Moon days · 📍 Moscow")
    assert _stored(storage, me) == "moscow"


def test_follow_is_answered_before_the_write(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage, "moscow")
    storage.teacher_links.add(me.id, _teacher(storage).id)
    writes = storage.teacher_links.writes
    original = storage.repo.set_moon_location

    async def logged(account_id: Any, slug: Any) -> Account:
        await asyncio.sleep(0)  # the round trip, as the other fakes do
        saved = await original(account_id, slug)
        writes.append("set_moon_location")  # the write finished
        return saved

    storage.repo.set_moon_location = logged  # type: ignore[method-assign]
    writes.clear()

    _tap(client, "m1:f")

    assert writes.index("answerCallbackQuery") < writes.index("set_moon_location")


# /settings.


@pytest.mark.parametrize(
    ("lang", "line"),
    [
        ("en", "🌙 Moon days: 📍 Almaty (as Anna)"),
        ("ru", "🌙 Лунные дни: 📍 Алматы (как у учителя: Anna)"),
    ],
)
def test_the_settings_line_names_the_teacher(
    client: TestClient, storage: InMemoryStorage, lang: str, line: str
) -> None:
    me = _me(client, storage, lang=lang)
    storage.teacher_links.add(me.id, _teacher(storage).id)

    body = _command(client, "/settings", lang)

    assert line in body["text"].splitlines()


def test_the_settings_line_is_plain_for_a_chosen_city(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage, "moscow")
    storage.teacher_links.add(me.id, _teacher(storage).id)

    body = _command(client, "/settings")

    assert "🌙 Moon days: 📍 Moscow" in body["text"].splitlines()


# Lead lines after the student's own taps (spec §2): in place, only when the slug changes.


def test_confirming_a_first_teacher_says_the_moon_days_follow_them(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _teacher(storage)
    consent = _command(client, f"/start t_{CODE}")

    body = _tap(client, _data(consent, "✅"))

    assert body["method"] == "editMessageText"
    assert "✅ Anna is on your list of teachers now." in body["text"]
    assert CHANGED_ANNA in body["text"]


@pytest.mark.parametrize("own", ["mysuru", "almaty"])
def test_confirming_says_nothing_when_the_city_stays(
    client: TestClient, storage: InMemoryStorage, own: str
) -> None:
    _me(client, storage, own)
    _teacher(storage)
    consent = _command(client, f"/start t_{CODE}")

    body = _tap(client, _data(consent, "✅"))

    assert "🌙 Your moon days" not in body["text"]


def test_confirming_a_teacher_without_a_city_says_nothing(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _teacher(storage, moon=None)
    consent = _command(client, f"/start t_{CODE}")

    body = _tap(client, _data(consent, "✅"))

    assert "🌙 Your moon days" not in body["text"]


def test_make_main_says_the_moon_days_follow_the_new_main(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    storage.teacher_links.add(me.id, _teacher(storage).id)
    boris = _teacher(storage, "Boris", "moscow", "1002", OTHER_CODE)
    storage.teacher_links.add(me.id, boris.id)

    body = _tap(client, f"t1:p:{boris.id}")

    assert (
        "🌙 Your moon days now follow Boris: 📍 Moscow. You can change this in /moon."
        in body["text"]
    )


def test_removing_the_only_teacher_says_the_days_are_for_mysuru(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    anna = _teacher(storage)
    storage.teacher_links.add(me.id, anna.id)

    body = _tap(client, f"t1:x:{anna.id}")

    assert ENDED in body["text"]


@pytest.mark.parametrize("lang", ["ru"])
def test_the_lead_lines_in_russian(client: TestClient, storage: InMemoryStorage, lang: str) -> None:
    me = _me(client, storage, lang=lang)
    anna = _teacher(storage)
    storage.teacher_links.add(me.id, anna.id)

    body = _tap(client, f"t1:x:{anna.id}", lang)

    assert (
        "🌙 Лунные дни теперь считаются по городу 📍 Майсур. Поменять можно в /moon."
        in body["text"]
    )


def test_removing_a_teacher_who_isnt_main_says_nothing(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    storage.teacher_links.add(me.id, _teacher(storage).id)
    boris = _teacher(storage, "Boris", "moscow", "1002", OTHER_CODE)
    storage.teacher_links.add(me.id, boris.id)

    body = _tap(client, f"t1:x:{boris.id}")

    assert "🌙 Your moon days" not in body["text"]


# The teacher's side: /moon, the invite hint, the first-student note and Keep.


@pytest.mark.parametrize(
    ("own", "line"),
    [
        ("almaty", "👥 Students who haven't chosen a city follow yours: 📍 Almaty."),
        (
            None,
            "👥 Your students' moon days are for 📍 Mysuru, like yours. You can keep it or "
            "choose your city in /moon.",
        ),
    ],
)
def test_a_teacher_is_told_students_follow_their_city(
    client: TestClient, storage: InMemoryStorage, own: str | None, line: str
) -> None:
    me = _me(client, storage, own)
    _student_of(storage, me)

    body = _command(client, "/moon")

    assert line in body["text"]


def test_no_shared_line_without_students(client: TestClient, storage: InMemoryStorage) -> None:
    _me(client, storage, "almaty")

    body = _command(client, "/moon")

    assert "Students who" not in body["text"]


def test_the_invite_screen_says_students_will_follow(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage)

    body = _tap(client, "t1:i")

    assert "Share this link or QR code. Each student confirms for themselves." in body["text"]
    assert (
        "Students who haven't chosen a moon city will follow the city you choose in /moon."
        in body["text"]
    )


def _note(outbound: list[Sent], chat_id: int) -> Sent:
    [note] = [s for s in outbound if s.name == "sendMessage" and s.fields["chat_id"] == chat_id]
    return note


def _lena_who_follows_maya(storage: InMemoryStorage, own: str | None = None) -> Account:
    lena = _teacher(storage, "Лена", own)
    maya = person(storage, "1009", "Maya", moon="almaty")
    storage.teacher_links.add(lena.id, maya.id)
    return lena


def test_the_first_student_note_offers_to_keep_the_inherited_city(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    _lena_who_follows_maya(storage)
    consent = _command(client, f"/start t_{CODE}")

    _tap(client, _data(consent, "✅"))

    note = _note(outbound, 1001)
    assert note.fields["text"].startswith(JOINED)
    assert OWN_EN in " ".join(note.fields["text"].split())
    assert note.fields["disable_notification"] is True
    keyboard = note.fields["reply_markup"]["inline_keyboard"]
    flat = [b for row in keyboard for b in row]
    keep = next(b for b in flat if b["text"].startswith("Keep"))
    assert keep["text"] == "Keep 📍 Almaty"
    assert keep["callback_data"] == "m1:k:almaty"
    assert len(keep["callback_data"].encode()) <= 29
    assert any(b["callback_data"] == "t1:s:0" for b in flat)  # 👥 My students stays


@pytest.mark.parametrize("own", ["moscow", FOLLOW_TEACHER])
def test_a_teacher_who_chose_gets_the_plain_note(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent], own: str
) -> None:
    _lena_who_follows_maya(storage, own)
    consent = _command(client, f"/start t_{CODE}")

    _tap(client, _data(consent, "✅"))

    note = _note(outbound, 1001)
    assert note.fields["text"] == JOINED
    [[only]] = note.fields["reply_markup"]["inline_keyboard"]
    assert only["callback_data"] == "t1:s:0"


def test_a_second_student_gets_the_plain_note(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    lena = _lena_who_follows_maya(storage)
    _student_of(storage, lena)
    consent = _command(client, f"/start t_{CODE}")

    _tap(client, _data(consent, "✅"))

    assert _note(outbound, 1001).fields["text"] == JOINED


def test_the_note_is_in_the_teachers_language(
    client: TestClient, storage: InMemoryStorage, outbound: list[Sent]
) -> None:
    lena = _lena_who_follows_maya(storage)
    storage.repo.accounts[lena.id] = replace(storage.repo.accounts[lena.id], locale="ru")
    consent = _command(client, f"/start t_{CODE}")

    _tap(client, _data(consent, "✅"))

    note = _note(outbound, 1001)
    text = " ".join(note.fields["text"].split())
    assert (
        "🌙 Теперь, когда у тебя есть ученики, лунные дни считаются по твоей настройке: "
        "📍 Майсур. Чтобы оставить 📍 Алматы, как у учителя (Maya), нажми кнопку ниже." in text
    )
    flat = [b for row in note.fields["reply_markup"]["inline_keyboard"] for b in row]
    assert "Оставить 📍 Алматы" in [b["text"] for b in flat]


def _me_as_teacher(client: TestClient, storage: InMemoryStorage, own: str | None = None) -> Account:
    """42 is the teacher now: never chose (or `own`), follows Maya (Almaty), has a student."""
    me = _me(client, storage, own)
    maya = person(storage, "1009", "Maya", moon="almaty")
    storage.teacher_links.add(me.id, maya.id)
    _student_of(storage, me)
    return me


NOTE_TEXT = f"{JOINED}\n\n{OWN_EN}"


def test_keep_stores_the_city_and_edits_the_note(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me_as_teacher(client, storage)

    body = _tap(client, "m1:k:almaty", text=NOTE_TEXT)

    assert body["method"] == "editMessageText"
    assert body["text"].startswith(JOINED)
    assert KEPT in body["text"]
    flat = _buttons(body)
    assert [b["callback_data"] for b in flat] == ["t1:s:0"]  # Keep gone, 👥 My students kept
    assert _stored(storage, me) == "almaty"


@pytest.mark.parametrize(
    ("own", "line"),
    [
        ("moscow", "🌙 Your moon city is already chosen: 📍 Moscow. You can change it in /moon."),
        (
            FOLLOW_TEACHER,
            "🌙 Your moon city is already chosen: 📍 Almaty. You can change it in /moon.",
        ),
    ],
)
def test_keep_after_a_choice_writes_nothing_and_says_so(
    client: TestClient, storage: InMemoryStorage, own: str, line: str
) -> None:
    me = _me_as_teacher(client, storage, own)

    body = _tap(client, "m1:k:almaty", text=NOTE_TEXT)

    assert line in body["text"]
    assert [b["callback_data"] for b in _buttons(body)] == ["t1:s:0"]
    assert _stored(storage, me) == own


def test_keep_twice_writes_once(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me_as_teacher(client, storage)

    _tap(client, "m1:k:almaty", text=NOTE_TEXT)
    again = _tap(client, "m1:k:almaty", text=NOTE_TEXT)

    assert "already chosen: 📍 Almaty" in again["text"]
    assert storage.repo.conditional_writes == 1  # type: ignore[attr-defined]
    assert _stored(storage, me) == "almaty"


@pytest.mark.parametrize("slug", ["atlantis", FOLLOW_TEACHER])
def test_a_forged_keep_rerenders_moon_and_writes_nothing(
    client: TestClient, storage: InMemoryStorage, slug: str
) -> None:
    me = _me_as_teacher(client, storage)

    body = _tap(client, f"m1:k:{slug}", text=NOTE_TEXT)

    assert body["text"].startswith("🌙 Moon days · 📍 Mysuru")
    assert _stored(storage, me) is None


@pytest.mark.parametrize("data", ["m1:k", "m1:k:", "m1:k:Almaty", "m1:k:" + "a" * 25, "m1:f:x"])
def test_malformed_keep_or_follow_is_only_answered(
    client: TestClient, storage: InMemoryStorage, data: str
) -> None:
    me = _me_as_teacher(client, storage)

    body = _tap(client, data, text=NOTE_TEXT)

    assert body is None or body.get("method") == "answerCallbackQuery"
    assert _stored(storage, me) is None


def test_keep_is_answered_before_the_write(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me_as_teacher(client, storage)
    writes = storage.teacher_links.writes
    original = storage.repo.set_moon_location_if_unset  # type: ignore[attr-defined]

    async def logged(account_id: Any, slug: str) -> Any:
        saved = await original(account_id, slug)  # its fake takes the round trip
        writes.append("keep")  # the write finished
        return saved

    storage.repo.set_moon_location_if_unset = logged  # type: ignore[attr-defined]
    writes.clear()

    _tap(client, "m1:k:almaty", text=NOTE_TEXT)

    assert writes.index("answerCallbackQuery") < writes.index("keep")
    assert _stored(storage, me) == "almaty"


def test_a_follow_chosen_teacher_is_told_students_get_the_default(
    client: TestClient, storage: InMemoryStorage
) -> None:
    """One hop: their students get Mysuru, not the Almaty this teacher inherits."""
    me = _me(client, storage, FOLLOW_TEACHER)
    storage.teacher_links.add(me.id, _teacher(storage).id)
    _student_of(storage, me)

    body = _command(client, "/moon")

    assert body["text"].startswith("🌙 Moon days · 📍 Almaty")
    assert (
        "👥 Your students' moon days are for 📍 Mysuru. You can keep it or choose your city "
        "in /moon." in body["text"]
    )
