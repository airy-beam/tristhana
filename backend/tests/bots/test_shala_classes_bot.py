# ruff: noqa: RUF001
"""UI-06 stage 6, slice A2, through the real webhook: the bot's shala and classes (spec §3, §4).

The card's Classes block per role and its buttons into the app (B1, §3.1); the week's and My
schedule's (B1); "Shala and classes" for nobody, a student and the staff of two shalas (B3,
C12); Today's shala step (B4); the two invites named apart (B5); "🏛 Shala in the app" on
"Teacher and shala" (C1); "🗓 Shala classes" in Help (C17). Every button into the app is a
`web_app` button whose `open` value the Mini App knows (`test_app_targets.py`).

The clock is frozen on Mon 9 Nov 2026, 08:00 in Almaty."""

import itertools
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.bots.statements import Statements
from tests.fakes import InMemoryStorage
from tests.moon_follow_fakes import person
from tests.shala_fakes import shala_storage
from tristhana.bots.telegram.callbacks import DayCallback, encode
from tristhana.bots.telegram.shalas_callbacks import short_id
from tristhana.domain.accounts import Account
from tristhana.domain.classes import ClassType
from tristhana.domain.journey import JourneyFacts, OwnedShala
from tristhana.domain.shalas import ShalaRole
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
APP = "https://tristhana.web.app"
ME_TG = 42
NOW = datetime(2026, 11, 9, 3, 0, tzinfo=UTC)  # Mon 9 Nov, 08:00 Almaty
_ids = itertools.count(270_000)


@dataclass
class Frozen:
    instant: datetime = NOW

    def now(self) -> datetime:
        return self.instant


@pytest.fixture
def clock() -> Frozen:
    return Frozen()


@pytest.fixture
def storage(clock: Frozen) -> InMemoryStorage:
    storage = shala_storage()
    storage.repo.clock.instant = clock.instant
    return storage


@pytest.fixture
def client(
    storage: InMemoryStorage, clock: Frozen, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    import tristhana.main

    async def record(self: AiohttpSession, bot: object, method: Any, **options: Any) -> bool:
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)
    monkeypatch.setattr(tristhana.main, "SystemClock", lambda: clock)
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
        miniapp_url=APP,
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


def _tap(client: TestClient, data: str, lang: str = "en") -> Any:
    message = {"message_id": 9, "date": 1_760_000_000, "chat": {"id": ME_TG, "type": "private"}}
    callback = {
        "id": f"cb{next(_ids)}",
        "from": _user(lang),
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
    return next(b["callback_data"] for b in _buttons(body) if b["text"] == text)


def _app(body: Any, text: str) -> dict[str, list[str]]:
    url: str = next(b["web_app"]["url"] for b in _buttons(body) if b["text"] == text)
    url = next(b["web_app"]["url"] for b in _buttons(body) if b["text"] == text)
    assert url.startswith(f"{APP}?")
    return parse_qs(urlsplit(url).query)


def _lines(body: Any) -> list[str]:
    return [" ".join(line.split()) for line in body["text"].splitlines()]


def _me(client: TestClient, storage: InMemoryStorage, lang: str = "en") -> Account:
    _command(client, "/start", lang)
    return next(a for a in storage.repo.accounts.values() if a.display_name == "Ash")


def _shala(
    storage: InMemoryStorage, me: Account, role: str | None, *, name: str = "Ashtanga Almaty"
) -> tuple[UUID, Account]:
    """Anna's shala with me as `role` ("owner": mine; None: a student; "nobody")."""
    anna = person(storage, f"10{next(_ids)}", "Anna")
    if role == "owner":
        return storage.shalas.add_shala(me.id, name, "almaty").id, anna
    shala = storage.shalas.add_shala(anna.id, name, "almaty").id
    if role is None:
        storage.shalas.add_student(shala, me.id)
    elif role != "nobody":
        storage.shalas.add_staff(shala, me.id, ShalaRole(role))
    return shala, anna


def _owned(storage: InMemoryStorage, me: Account, shala: UUID, classes: int) -> None:
    """The journey read's facts (seeded in the fake): I own `shala`, with no student yet."""
    owned = (OwnedShala(shala, classes=classes, students=0),)
    storage.repo.journey[me.id] = JourneyFacts(owned=owned)


def _card(client: TestClient, shala: UUID, lang: str = "en") -> Any:
    return _tap(client, f"h1:c:{short_id(shala)}", lang)


# The card (B1, §3.1)


@pytest.mark.parametrize(
    ("role", "manages", "edits"),
    [
        ("owner", True, True),
        ("admin", True, True),
        ("teacher", True, False),
        ("office", True, False),
        ("assistant", False, False),
        (None, False, False),  # a student
    ],
)
def test_the_card_per_role_has_the_classes_and_the_buttons_into_the_app(
    client: TestClient, storage: InMemoryStorage, role: str | None, manages: bool, edits: bool
) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, role)
    storage.schedule.add_class(shala, teacher_id=me.id)

    body = _card(client, shala)

    assert ("Classes" in _lines(body)) is manages
    assert ("Mysore · Mon–Fri · 06:00–09:30 · Ash" in _lines(body)) is manages
    assert ("🗓 Add or change classes" in _texts(body)) is manages
    assert "➕ Add a class" not in _texts(body)
    if manages:
        assert _app(body, "🗓 Add or change classes") == {"open": ["shala"], "shala": [str(shala)]}
    assert ("✏️ Edit the shala" in _texts(body)) is edits
    if edits:
        assert _app(body, "✏️ Edit the shala") == {"open": ["edit-shala"], "shala": [str(shala)]}
    # Below the Schedule, which stays by date for everyone.
    rows = _rows(body)
    if manages:
        assert rows.index(["🗓 Add or change classes"]) == rows.index(["🗓 Schedule"]) + 1


def test_a_shala_without_a_current_class_says_so_and_adds_one_in_the_app(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "owner")
    storage.schedule.add_class(shala, ends_on=date(2026, 11, 1))  # ended last week

    body = _card(client, shala)

    lines = _lines(body)
    assert lines[lines.index("Classes") + 1] == "No classes yet."
    assert "🗓 Add or change classes" not in _texts(body)
    assert _app(body, "➕ Add a class") == {"open": ["class"], "shala": [str(shala)]}


def test_the_classes_read_as_the_apps_list_in_order(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala, anna = _shala(storage, me, "owner")
    storage.shalas.add_staff(shala, anna.id, ShalaRole.TEACHER)
    add = storage.schedule.add_class
    add(shala, type=ClassType.LED, start=time(8), minutes=90, weekdays=frozenset({7}))
    add(shala, teacher_id=anna.id)
    add(shala, ends_on=date(2026, 11, 8))  # ended yesterday: gone
    add(shala, ends_on=date(2026, 11, 9), start=time(7))  # ends today: still runs
    add(
        shala,
        type=ClassType.PRANAYAMA,
        title="Nadi",
        start=time(17),
        minutes=60,
        weekdays=frozenset({1, 3, 5}),
        every=2,
    )
    add(shala, weekdays=frozenset(range(1, 8)), start=time(7, 30), online=True, city="moscow")
    add(
        shala,
        type=ClassType.CHANTING,
        start=time(19),
        minutes=60,
        weekdays=frozenset({6, 7, 1}),
        starts_on=date(2026, 11, 11),
    )
    add(
        shala,
        type=ClassType.WORKSHOP,
        start=time(10),
        minutes=120,
        weekdays=frozenset(),
        starts_on=date(2026, 11, 12),
    )
    add(shala, type=ClassType.WORKSHOP, weekdays=frozenset(), starts_on=date(2026, 11, 8))

    lines = _lines(_card(client, shala))

    start = lines.index("Classes")
    assert lines[start : start + 8] == [
        "Classes",
        "Mysore · Mon–Fri · 06:00–09:30 · Anna",
        "Mysore · Mon–Fri · 07:00–10:30 · through Mon, Nov 9",
        "Mysore · every day · 07:30–11:00 · 🌐 Moscow (UTC+3)",
        "Pranayama Nadi · Mon, Wed, Fri · 17:00–18:00 · every 2 weeks",
        "Chanting · Mon, Sat, Sun · 19:00–20:00 · from Wed, Nov 11",
        "Led · Sun · 08:00–09:30",
        "Workshop · Thu, Nov 12 · 10:00–12:00",
    ]
    assert "Workshop · Sun, Nov 8" not in " ".join(lines)


def test_the_classes_read_in_russian(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage, "ru")
    shala, _ = _shala(storage, me, "owner")
    storage.schedule.add_class(shala)
    storage.schedule.add_class(shala, weekdays=frozenset(range(1, 8)), start=time(8), every=3)

    body = _card(client, shala, "ru")

    lines = _lines(body)
    assert lines[lines.index("Занятия") + 1 :][:2] == [
        "Майсор · пн–пт · 06:00–09:30",
        "Майсор · каждый день · 08:00–11:30 · каждые 3 недели",
    ]
    assert "🗓 Настроить занятия" in _texts(body)
    assert "✏️ Изменить шалу" in _texts(body)


def test_a_long_list_stops_at_twelve(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "owner")
    for i in range(14):
        storage.schedule.add_class(shala, start=time(5 + i), minutes=30)

    lines = _lines(_card(client, shala))

    start = lines.index("Classes")
    assert lines[start + 12] == "Mysore · Mon–Fri · 16:00–16:30"
    assert lines[start + 13] == "…"


def test_the_classes_read_alongside_the_card(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "teacher")
    statements = Statements(monkeypatch, storage)

    _card(client, shala)

    # Spec §8: +1 statement, in parallel with the card's read.
    assert "InMemorySchedule.classes_of" in statements.names


def test_a_failed_classes_read_leaves_the_card_without_its_classes(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review fix: the Classes block is optional; the card shows without it."""
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "teacher")

    async def broken(*_: object, **__: object) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(storage.schedule, "classes_of", broken)

    body = _card(client, shala)

    assert body["text"].startswith("🏛 Ashtanga Almaty")
    assert "Classes" not in _lines(body)
    assert "🗓 Schedule" in _texts(body)


def test_the_no_teachers_hint_says_where_and_opens_the_shala_in_the_app(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala = storage.shalas.add_shala(me.id, "Ashtanga Almaty", "almaty", roles=frozenset()).id

    body = _card(client, shala)

    assert body["text"].endswith(
        "No one here has the Teacher role yet, so students can't pick a teacher. To give it, "
        "open the shala in the app, then Teachers and staff."
    )
    assert _app(body, "🏛 Shala in the app") == {"open": ["shala"], "shala": [str(shala)]}


# The week and My schedule (B1)


@pytest.mark.parametrize("classes", [0, 1])
def test_the_week_offers_staff_who_manage_it_the_classes_in_the_app(
    client: TestClient, storage: InMemoryStorage, classes: int
) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "teacher")
    for _ in range(classes):
        storage.schedule.add_class(shala)

    body = _tap(client, f"c1:w:{short_id(shala)}:0")

    assert _app(body, "🗓 Add or change classes") == {"open": ["shala"], "shala": [str(shala)]}
    assert "🗓 Full week in the app" not in _texts(body)


def test_a_week_cut_short_offers_a_student_the_full_week_in_the_app(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tristhana.bots.telegram import classes

    me = _me(client, storage)
    shala, _ = _shala(storage, me, None)
    storage.schedule.add_class(shala, weekdays=frozenset(range(1, 8)))
    week = f"c1:w:{short_id(shala)}:0"
    assert "🗓 Full week in the app" not in _texts(_tap(client, week))

    monkeypatch.setattr(classes, "BUDGET", 300)
    body = _tap(client, week)

    assert "…" in _lines(body)
    assert _app(body, "🗓 Full week in the app") == {"open": ["shala"], "shala": [str(shala)]}
    assert "🗓 Add or change classes" not in _texts(body)


def test_my_schedule_cut_short_has_the_full_week_as_a_button(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tristhana.bots.telegram import classes

    me = _me(client, storage)
    shala, _ = _shala(storage, me, None)
    storage.schedule.add_class(shala, weekdays=frozenset(range(1, 8)))
    assert "🗓 Full week in the app" not in _texts(_command(client, "/schedule"))

    monkeypatch.setattr(classes, "BUDGET", 300)
    body = _command(client, "/schedule")

    assert _lines(body)[-1] == "…"
    assert "The full week is in the app." not in _lines(body)
    assert _app(body, "🗓 Full week in the app") == {"open": ["schedule"]}


# "Shala and classes" (B3, C12)

STUDENT_LINE = (
    "Looking for your shala's classes? Ask your shala for its link. Once you join, the schedule "
    "is under ☰ Menu → 🗓 My schedule."
)


def test_shala_and_classes_for_someone_in_no_shala_puts_the_student_line_first(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    _me(client, storage)
    statements = Statements(monkeypatch, storage)

    body = _tap(client, "w1:s:o")

    assert body["text"].startswith(STUDENT_LINE + "\n\nA shala here is a page for your students")
    assert _rows(body) == [["🏛 Create a shala"], ["‹ Back"]]
    assert _app(body, "🏛 Create a shala") == {"open": ["new-shala"]}
    assert statements.names == []  # a pure render


def test_shala_and_classes_for_a_student_lists_their_shala_on_top(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, None)

    body = _tap(client, "w1:s:f")

    assert _rows(body) == [["🏛 Ashtanga Almaty"], ["🏛 Create a shala"], ["‹ Back"]]
    assert _data(body, "🏛 Ashtanga Almaty") == f"h1:c:{short_id(shala)}"
    assert body["text"].startswith(STUDENT_LINE)


def test_shala_and_classes_for_the_staff_of_two_shalas(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    me = _me(client, storage)
    mine, _ = _shala(storage, me, "owner", name="Mysore Almaty")
    theirs, _ = _shala(storage, me, "teacher", name="Ashtanga Astana")
    statements = Statements(monkeypatch, storage)

    body = _tap(client, "w1:s:o")

    assert body["text"] == "Tap a shala below: its schedule, the student invite and more are there."
    rows = _rows(body)
    assert sorted(rows[:2]) == [["🏛 Ashtanga Astana"], ["🏛 Mysore Almaty"]]
    assert rows[2:] == [["🏛 Create another shala"], ["‹ Back"]]
    assert _data(body, "🏛 Mysore Almaty") == f"h1:c:{short_id(mine)}"
    assert _data(body, "🏛 Ashtanga Astana") == f"h1:c:{short_id(theirs)}"
    assert _data(body, "‹ Back") == "w1:o"
    assert statements.names == ["InMemoryShalas.mine"]  # one read


# Today's shala step (B4)


def test_today_offers_a_new_shalas_owner_to_add_a_class(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "owner")
    _owned(storage, me, shala, classes=0)

    body = _tap(client, "w1:n")

    assert (
        "Your shala has no classes yet. Add the first one, and students will see the schedule."
        in _lines(body)
    )
    rows = _rows(body)
    assert rows[-2:] == [["Add a class"], ["📅 Another day", "☰ Menu"]]
    assert _app(body, "Add a class") == {"open": ["class"], "shala": [str(shala)]}
    assert "Not now" not in _texts(body)


def test_a_failed_next_steps_read_leaves_today_without_its_step(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review fix: the step is optional; Today shows without it."""
    me = _me(client, storage)
    _shala(storage, me, "owner")

    async def broken(*_: object, **__: object) -> None:
        raise RuntimeError("db down")

    monkeypatch.setattr(storage.repo, "journey_facts", broken)

    body = _tap(client, "w1:n")

    assert body["text"].startswith("Today, ")
    assert _rows(body)[-1] == ["📅 Another day", "☰ Menu"]
    assert "Add a class" not in _texts(body)


def test_today_offers_the_shala_invite_once_it_has_a_class(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "owner")
    storage.schedule.add_class(shala)
    _owned(storage, me, shala, classes=1)

    body = _tap(client, "w1:n")

    assert "Your shala has a schedule now. Invite students, and they'll see its classes." in _lines(
        body
    )
    assert _rows(body)[-2:] == [["Invite students to the shala"], ["📅 Another day", "☰ Menu"]]
    assert _data(body, "Invite students to the shala") == f"h1:i:{short_id(shala)}"


@pytest.mark.parametrize("role", [None, "teacher"])
def test_today_has_no_shala_step_for_a_student_or_a_staff_teacher(
    client: TestClient, storage: InMemoryStorage, role: str | None
) -> None:
    me = _me(client, storage)
    _shala(storage, me, role)  # Anna's shala: the steps are for its owner only

    body = _tap(client, "w1:n")

    assert _rows(body)[-1] == ["📅 Another day", "☰ Menu"]
    assert not any("Your shala" in line for line in _lines(body))


def test_today_reads_no_steps_for_someone_off_any_staff(
    client: TestClient, storage: InMemoryStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    me = _me(client, storage)
    _shala(storage, me, None)
    statements = Statements(monkeypatch, storage)

    _tap(client, "w1:n")

    assert not [n for n in statements.names if n.endswith("journey_facts")]


def test_the_day_editor_offers_no_step(client: TestClient, storage: InMemoryStorage) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "owner")
    _owned(storage, me, shala, classes=0)

    body = _tap(client, encode(DayCallback("open", date(2026, 11, 8))))

    assert "Add a class" not in _texts(body)


# The two invites (B5)


def test_for_teachers_offers_shala_staff_the_shalas_own_invite(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "teacher")

    body = _tap(client, "w1:o")

    assert _rows(body)[0] == ["➕ Invite students to the shala"]
    assert _data(body, "➕ Invite students to the shala") == f"h1:i:{short_id(shala)}"
    assert "👥 Invite my students" not in _texts(body)
    assert "🏛 Shala and classes" in _texts(body)


def test_for_teachers_offers_everyone_else_the_personal_invite(
    client: TestClient, storage: InMemoryStorage
) -> None:
    _me(client, storage)

    body = _tap(client, "w1:o")

    assert _rows(body) == [["👥 Invite my students"], ["🏛 Shala and classes"], ["☰ Menu"]]
    assert _data(body, "👥 Invite my students") == "t1:i"


@pytest.mark.parametrize(("role", "line"), [("teacher", True), (None, False), ("nobody", False)])
def test_the_personal_invite_tells_shala_staff_it_is_not_the_shalas(
    client: TestClient, storage: InMemoryStorage, role: str | None, line: bool
) -> None:
    me = _me(client, storage)
    _shala(storage, me, role)

    body = _tap(client, "t1:i")

    own = (
        "This is your own link, not the shala's. "
        "The shala's link is on its card: ➕ Invite students to the shala."
    )
    assert (own in _lines(body)) is line


def test_the_shala_link_says_what_students_do_next(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, "owner")

    body = _tap(client, f"h1:i:{short_id(shala)}")

    assert body["text"].endswith(
        "Send this link or show the QR code. Each student confirms for themselves. They join "
        "the shala and can then pick their teacher there."
    )


# "Teacher and shala" (C1) and Help (C17)


def test_teacher_and_shala_opens_the_shala_tab_by_name(
    client: TestClient, storage: InMemoryStorage
) -> None:
    me = _me(client, storage)
    _shala(storage, me, None)

    body = _tap(client, "t1:o")

    assert "Open the app" not in _texts(body)
    assert _app(body, "🏛 Shala in the app") == {"open": ["shala"]}


@pytest.mark.parametrize(("role", "row"), [("owner", True), ("teacher", True), (None, False)])
def test_help_offers_shala_staff_their_shalas_classes(
    client: TestClient, storage: InMemoryStorage, role: str | None, row: bool
) -> None:
    me = _me(client, storage)
    shala, _ = _shala(storage, me, role)

    body = _command(client, "/help")

    assert ("🗓 Shala classes" in _texts(body)) is row
    if row:
        assert _data(body, "🗓 Shala classes") == f"h1:c:{short_id(shala)}"
        rows = _rows(body)
        assert rows.index(["🗓 Shala classes"]) == rows.index(["🙏 Add my teacher or shala"]) + 1
