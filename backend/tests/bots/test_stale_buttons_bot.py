"""Buttons under messages sent before UI-06 (spec §5, §8): a tap on any of them still gets a
screen, an edit or a message, never only the answer that stops the spinner. And the right
screen: each reply is checked for what identifies it (`FULL`, `BARE`), since "some message
went out" also holds for a fallback that hides a broken handler.

Two worlds serve every entry of the frozen list (`fixtures/pre_ui06_callbacks.py`). The full
one is seeded with the ids, codes and dates inside the strings: me (a platform admin, a
teacher and a student of the other person, on the staff of the shala), the shala with one
class and one student, a rest period, a directory request. The bare one has only me: nothing
logged, nobody linked, no shala, none of the codes. That is the person whose teacher, shala
or day is gone by the time they tap. The clock is fixed on the list's own day.

Also here: every screen the Menu and Help open has a way back (UI-06 §2).
"""

import itertools
from collections.abc import Iterator
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tests.announcement_fakes import Member, Person
from tests.bots.fixtures import pre_ui06_callbacks as frozen
from tests.directory_listing_fakes import always
from tests.fakes import FixedClock, InMemoryStorage
from tests.moon_follow_fakes import person
from tests.shala_fakes import shala_storage
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.directory_listing import Step, clean
from tristhana.domain.moon import MoonDay, MoonDayKind
from tristhana.domain.practice import Practice, PracticeContext
from tristhana.domain.rest_periods import RestPeriod
from tristhana.domain.shalas import ShalaRole
from tristhana.infrastructure.i18n.fluent import FluentTranslator
from tristhana.main import create_app
from tristhana.settings import Settings

SECRET = "test-secret_123"
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
BOT = "tristhana_test_bot"
ME_TG = 42
NOW = datetime(2026, 11, 15, 0, 30, tzinfo=UTC)  # Sun Nov 15, 05:30 in Almaty: `frozen.DAY`
EVERY_DAY = frozenset({1, 2, 3, 4, 5, 6, 7})
# `editMessageReplyMarkup`: a pushed announcement keeps its text and gets its row redrawn.
SCREENS = {
    "editMessageText",
    "editMessageReplyMarkup",
    "sendMessage",
    "sendPhoto",
    "sendDocument",
}
STAFF_CODE = "St4ffC0deSt4ffC0"
T = FluentTranslator()
_ids = itertools.count(270_000)


@dataclass
class World:
    client: TestClient
    storage: InMemoryStorage
    out: list[Any]  # Bot API calls made directly (not as the webhook reply), as method objects
    me: UUID

    @property
    def sent(self) -> list[str]:
        return [method.__api_method__ for method in self.out]


def _fixed_ids(monkeypatch: pytest.MonkeyPatch, module: str, value: UUID) -> None:
    monkeypatch.setattr(f"{module}.uuid4", lambda: value)


def _seed(storage: InMemoryStorage, me: UUID, monkeypatch: pytest.MonkeyPatch) -> None:
    """The full world: everything the ids, codes and dates inside the strings point at."""
    owner = person(storage, "1002", "Dana")
    with monkeypatch.context() as ids:  # the ids inside the frozen strings
        _fixed_ids(ids, "tests.fakes", frozen.PERSON)
        anna = person(storage, "1001", "Anna", moon="almaty")
        _fixed_ids(ids, "tests.shala_fakes", frozen.SHALA)
        shala = storage.shalas.add_shala(owner.id, code=frozen.SHALA_CODE).id
        _fixed_ids(ids, "tests.schedule_fakes", frozen.CLASS)
        storage.schedule.add_class(
            shala, weekdays=EVERY_DAY, starts_on=date(2026, 10, 1), teacher_id=me
        )
    assert (anna.id, shala) == (frozen.PERSON, frozen.SHALA)
    storage.shalas.add_staff(shala, me, ShalaRole.ADMIN, ShalaRole.TEACHER)
    storage.shalas.add_student(shala, anna.id)
    storage.link_repo.add(me, anna.id)  # Anna is my teacher...
    storage.link_repo.add(anna.id, me)  # ... and my student
    storage.link_repo.codes[anna.id] = frozen.TEACHER_CODE
    storage.day_repo.periods.rows[(me, frozen.PERIOD_START)] = RestPeriod(
        frozen.PERIOD_START, frozen.PERIOD_END, DayStatus.SICK
    )
    # The announcement port has its own fake: the same teacher and shala in it (NT-03).
    feed = storage.announcements
    feed.people[me], feed.people[anna.id] = Person("Ash"), Person("Anna")
    feed.link(me, anna.id)
    feed.shala_names[shala] = "Ashtanga Almaty"
    feed.members[(shala, me)] = Member(NOW - timedelta(days=30), roles=frozenset({ShalaRole.ADMIN}))


def _world(monkeypatch: pytest.MonkeyPatch, bare: bool) -> Iterator[World]:
    """`bare`: only me, as after a first /start: nothing logged, no teacher, student or
    shala, and none of the list's ids or codes exists. Not a platform admin either."""
    storage = shala_storage()
    storage.repo.clock.instant = NOW
    me = person(storage, str(ME_TG), "Ash", moon="almaty")
    if not bare:
        _seed(storage, me.id, monkeypatch)
    storage.attendance  # noqa: B018  # attaches the fake to the schedule
    storage.moon_repo.days_by_location["almaty"] = [MoonDay(frozen.MOON_DAY, MoonDayKind.PURNIMA)]
    out: list[Any] = []

    async def record(self: AiohttpSession, bot: object, method: Any, **_: object) -> bool:
        out.append(method)
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", record)
    monkeypatch.setattr("tristhana.main.SystemClock", lambda: FixedClock(NOW))
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
        miniapp_url="https://tristhana.web.app",
        telegram_bot_username=BOT,  # pyright: ignore[reportCallIssue]
        platform_admin_ids="" if bare else str(me.id),  # pyright: ignore[reportCallIssue]
        public_api_url="https://tristhana-api-test.a.run.app",  # pyright: ignore[reportCallIssue]  # SC-06
    )
    with TestClient(create_app(settings, storage)) as client:
        yield World(client, storage, out, me.id)


@pytest.fixture
def w(monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    yield from _world(monkeypatch, bare=False)


@pytest.fixture
def bare(monkeypatch: pytest.MonkeyPatch) -> Iterator[World]:
    yield from _world(monkeypatch, bare=True)


def _tap(w: World, data: str) -> Any:
    chat = {"id": ME_TG, "type": "private"}
    message = {"message_id": 9, "date": 1_760_000_000, "chat": chat, "text": "…"}
    callback = {
        "id": f"cb{next(_ids)}",
        "from": {"id": ME_TG, "is_bot": False, "first_name": "Ash", "language_code": "en"},
        "chat_instance": "ci",
        "data": data,
        "message": message,
    }
    response = w.client.post(
        "/telegram/webhook",
        json={"update_id": next(_ids), "callback_query": callback},
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
    )
    assert response.status_code == 200
    return response.json() if response.content else None


async def _seed_for(w: World, data: str) -> None:
    """What a button needs to have been on screen at all: the day it sits under was logged,
    the request it decides exists, the invite it answers is still unanswered."""
    prefix, letter = data.split(":")[:2]
    practiced = (frozen.DAY, DayLog(frozen.DAY, DayStatus.PRACTICED))
    under_practice = (("r1", "y"), ("r1", "n"), ("g1", "n"))
    if prefix in ("p1", "k1") or (prefix, letter) in under_practice or data.endswith(":k"):
        w.storage.day_repo.rows[(w.me, practiced[0])] = (practiced[1], None)
    if (prefix, letter) == ("p1", "s"):  # "Same as last time" is offered with a last time
        before = frozen.DAY - timedelta(days=1)
        w.storage.day_repo.rows[(w.me, before)] = (DayLog(before, DayStatus.PRACTICED), None)
        w.storage.day_repo.practice_rows[(w.me, before)] = Practice(PracticeContext.MYSORE)
    if (prefix, letter) in (("t1", "a"), ("t1", "y"), ("t1", "l")):
        # A consent screen is shown to someone who is not that teacher's student yet.
        del w.storage.link_repo.rows[(w.me, frozen.PERSON)]
    if (prefix, letter) in (("h1", "a"), ("h1", "b"), ("h1", "l")):
        # ... and a shala's to someone who is not in it yet.
        del w.storage.shalas.staff[(frozen.SHALA, w.me)]
    if (prefix, letter) == ("h1", "b"):
        w.storage.shalas.add_invite(frozen.SHALA, frozen.SHALA_CODE, ShalaRole.ASSISTANT)
    if (prefix, letter) == ("a1", "k"):
        # "Keep the pause" sits under a 🧘 that cut a 🌸 pause short: 13-17 became 13-14.
        w.storage.day_repo.rows[(w.me, practiced[0])] = (practiced[1], None)
        w.storage.day_repo.periods.rows[(w.me, frozen.PERIOD_START)] = RestPeriod(
            frozen.PERIOD_START, date(2026, 11, 14), DayStatus.LADIES
        )
    if prefix == "l1":
        details = clean("Anna Petrova", "Kazakhstan", "certified", None)
        await w.storage.listings.save(frozen.PERSON, details, always(Step.SEND), NOW)


D = f"{frozen.DAY:%Y%m%d}"
TODAY = f"d1:r:{D}:t"  # Today (T0): "Other…" with Back to Today
EDITOR = f"d1:r:{D}:e"  # the day editor (E0): "Other…" with Back to the editor
SAVED = f"d1:o:{D}"  # a saved day (S): ✏️ Change
AFTER_PRACTICED = f"p1:v:{D}"  # the buttons after 🧘 (P0): ✓ Done
DETAILS = f"p1:c:{D}:"  # the details (P1): the class types
DONE = (f"p1:o:{D}", "w1:m")  # the done screen (V): 📝 Details and the Menu
CHECK_IN = f"k1:e:{D}:"  # the check-in screen: the energy chips
REMINDER = "r1:t:"  # the practice reminder: the send times
SETTINGS = "s1:lp"
MOON = ("m1:c:0", "w1:m")
SHALA_CARD = "h1:k:"  # a shala's card: Leave…
SCHEDULE = "c1:p:"  # a shala's schedule, as its staff see it
# With nobody linked: "Teacher and shala" with its quiet invite row, and the empty list.
NO_TEACHER = ("t1:i:o", "w1:m")
NO_STUDENTS = ("t1:i", "w1:m")

# What identifies the right screen, by the entry itself, else its prefix and letter, else
# its prefix. A marker is the start of some button's callback data, or one of the words
# `_evidence` adds: a method (`sendPhoto`), `force_reply`, `request_location`, `url`.
FULL: dict[str, str | tuple[str, ...]] = {
    "d1:t": TODAY,
    "d1:o": EDITOR,
    "d1:s": SAVED,
    f"d1:s:{D}:p": AFTER_PRACTICED,
    "d1:x": EDITOR,
    "d1:w": ("d1:o:20261109", "w1:m"),  # the week picker: six days back, and the Menu
    "o1": TODAY,
    "q1": ("g1:o", "w1:o"),  # Help, the tour's replacement
    "q1:d:s": TODAY,
    "p1": DETAILS,
    "p1:v": DONE,
    "p1:s": DONE,
    "p1:m": f"p1:a:{D}",  # the length screen: Other…
    "p1:a": f"p1:r:{D}:",  # the series
    "p1:d": f"p1:t:{D}:",  # the durations
    "p1:r": (f"p1:g:{D}:", f"p1:a:{D}"),  # only this series, or with the previous one
    "p1:g": f"p1:l:{D}:",  # the asana grid
    "k1": CHECK_IN,
    "k1:v": DONE,
    "k1:x": DONE,
    "k1:g": f"k1:t:{D}:",  # the tags
    "k1:t": f"k1:t:{D}:",
    "n1:o": f"n1:w:{D}:",  # the note screen: Write
    "n1:w": "force_reply",
    "n1:r": "force_reply",
    "n1:y": f"n1:x:{D}:",
    "n1:x": f"n1:w:{D}:",
    f"n1:b:{D}:d": EDITOR,
    f"n1:b:{D}:k": CHECK_IN,
    "g1": ("g1:a:s", "w1:m"),  # My asanas, nothing set yet: Choose…
    "g1:c": ("g1:p:", "g1:o"),  # the change screen
    "g1:s": ("g1:u:", "w1:m"),  # set: My asanas with Undo
    "g1:a": ("g1:p:", "g1:o"),  # the series picker
    "g1:p:s:2:1": "g1:s:2:",  # the stop grid of Intermediate
    "g1:n": DETAILS,
    "r1": REMINDER,
    "r1:y": ("r1:v", "w1:m"),  # "I'll ask once a day at …"
    "r1:n": DONE,
    "r1:s": AFTER_PRACTICED,
    "r1:p": AFTER_PRACTICED,
    "r1:r": SAVED,
    "r1:q": f"r1:q:{D}:",  # the reminder message itself
    "r1:dp": "r1:dt:",  # the day off picker
    "r1:dt": "r1:dt:",
    "a1:p": ("a1:e:", SAVED),  # the pause, with End the pause
    "a1:m": f"a1:b:{D}:",  # more day counts
    "a1:b": f"a1:m:{D}:",
    "a1:o": SAVED,
    "a1:k": AFTER_PRACTICED,
    "a1:e": TODAY,
    "a1:er": REMINDER,
    "s1": SETTINGS,
    "s1:cp": "s1:c:",  # the city picker
    "s1:zp": "s1:c:",
    "s1:c:-": "request_location",
    "s1:o": ("s1:o:", "s1:v"),  # the day off picker
    "s1:h": "s1:h:",  # More
    "s1:k": "s1:k:",
    "m1": MOON,
    "m1:r": "m1:t:",  # the moon reminders
    "m1:o": "m1:t:",
    "m1:t": "m1:t:",
    "m1:c": "m1:s:",  # the city picker
    "m1:k": "t1:s:",  # the first-student note keeps its "My students" row
    "m1:q": "m1:q:",  # the moon reminder message itself
    "x1": ("x1:d", "x1:e"),  # My data
    "x1:e": "sendDocument",
    "x1:d": "x1:y:",  # the delete screen
    "x1:y": "x1:y:",
    "t1:a": TODAY,
    "t1:y": f"t1:a:{frozen.TEACHER_CODE}",  # the consent screen
    "t1:l": f"t1:a:{frozen.TEACHER_CODE}",
    "t1:n": TODAY,
    "t1:o": (f"t1:c:{frozen.PERSON}", "w1:m"),  # "Teacher and shala" with my teacher
    "t1:s": (f"t1:v:{frozen.PERSON}", "w1:m"),  # My students
    "t1:c": f"t1:u:{frozen.PERSON}",  # the teacher's card
    "t1:p": (f"t1:c:{frozen.PERSON}", "w1:m"),
    "t1:u": f"t1:x:{frozen.PERSON}",
    "t1:x": ("h1:c:", "w1:m"),  # removed: the list, where my shala still is
    "t1:v": f"t1:r:{frozen.PERSON}",  # the student's card
    "t1:r": f"t1:z:{frozen.PERSON}",
    "t1:z": NO_STUDENTS,
    "t1:i": ("t1:im", "t1:q", "url"),  # the invite
    "t1:q": "sendPhoto",
    "t1:w": "t1:wy",
    "t1:wy": ("t1:w", "t1:i"),  # More, with the new link
    # The student has no position here, so there is nothing to mark: the card again
    # (marking itself is in test_teacher_marks_bot.py).
    "t1:g": f"t1:r:{frozen.PERSON}",
    "t1:gp": f"t1:r:{frozen.PERSON}",
    "t1:gy": (f"t1:v:{frozen.PERSON}", "w1:m"),
    "h1:a": SHALA_CARD,
    "h1:b": SHALA_CARD,
    "h1:n": TODAY,
    "h1:l": f"h1:a:{frozen.SHALA_CODE}",  # the consent screen
    "h1:c": SHALA_CARD,
    "h1:m": "h1:u:",  # the shala's students
    "h1:v": "h1:x:",
    "h1:i": ("h1:q:", "url"),  # the join link
    "h1:q": "sendPhoto",
    "h1:w": "h1:wy:",
    "h1:wy": ("h1:q:", "url"),
    "h1:e": "h1:e:",  # pick a role
    "h1:e:ERERERERQRGBEREREREREQ:t": ("url", "h1:c:"),  # the staff link
    "h1:e:ERERERERQRGBEREREREREQ:a": ("url", "h1:c:"),
    "h1:e:ERERERERQRGBEREREREREQ:o": ("url", "h1:c:"),
    "h1:e:ERERERERQRGBEREREREREQ:m": SHALA_CARD,  # only the owner invites a manager
    "h1:u": "h1:x:",
    "h1:x": "h1:c:",
    "h1:k": "h1:ky:",
    "h1:ky": (f"t1:c:{frozen.PERSON}", "w1:m"),
    "c1": SCHEDULE,
    "c1:p": "c1:o:",  # pick an occurrence
    "c1:o": "c1:x:",
    "c1:d": SHALA_CARD,
    "c1:m": ("c1:m:", "w1:m"),  # My schedule
    "c1:f": "c1:f:",  # the calendar link
    "v1": "v1:i:",  # "I was there"
    "v1:p": "v1:r:",
    "v1:r": "v1:p",  # the roster
    "v1:a": "v1:p",
    "v1:y": "v1:p",
    "v1:n": "v1:p",
    "b1": ("b1:", "h1:c:"),  # a shala's announcements, Back to its card
    "b1:l:t": ("b1:", f"t1:c:{frozen.PERSON}"),  # a teacher's
    "b1:m:t": ("b1:", f"t1:c:{frozen.PERSON}"),
    "b1:u:t": ("b1:", f"t1:c:{frozen.PERSON}"),
    "l1": "t1:im",  # my directory line
    "l1:w": "l1:wy",
    "l1:a": "l1:c:",  # the admin's lists
    "l1:k": "l1:a:",
    "l1:c": "l1:y:",
    "l1:y": "l1:k:",
    "l1:n": "l1:ny:",
    "l1:ny": "l1:k:",
}
for _where in ("t", "h"):  # under the pushed message itself: only its row is redrawn
    for _letter in ("m", "u"):
        _id = "MzMzMzMzQzODMzMzMzMzMw" if _where == "t" else "ERERERERQRGBEREREREREQ"
        FULL[f"b1:{_letter}:{_where}:{_id}:n"] = ("editMessageReplyMarkup", "b1:l:")

# The bare account: where its replies differ. A day that is not Practiced opens its editor,
# with the line saying so; a teacher, student or shala that is gone opens the list it was
# on; a code that no longer exists says so above Today.
_NOT_MINE: dict[str, str | tuple[str, ...]] = {
    key: NO_TEACHER
    for key in ("h1", "c1", *FULL)
    if key.startswith(("h1", "c1", "b1"))
    and key not in ("h1:a", "h1:b", "h1:l", "h1:n", "c1:m", "c1:f")
}
BARE: dict[str, str | tuple[str, ...]] = {
    **FULL,
    **_NOT_MINE,
    "p1": EDITOR,
    "p1:v": EDITOR,
    "p1:s": EDITOR,
    "p1:d": EDITOR,
    "k1": EDITOR,
    "k1:v": EDITOR,
    "k1:x": EDITOR,
    "k1:g": EDITOR,
    "k1:t": EDITOR,
    f"n1:b:{D}:k": EDITOR,
    "g1:n": EDITOR,
    "r1:n": EDITOR,
    "a1:k": EDITOR,
    "t1:a": TODAY,
    "t1:y": TODAY,
    "t1:l": TODAY,
    "t1:o": NO_TEACHER,
    "t1:s": NO_STUDENTS,
    "t1:c": NO_TEACHER,
    "t1:p": NO_TEACHER,
    "t1:u": NO_TEACHER,
    "t1:x": NO_TEACHER,
    "t1:v": NO_STUDENTS,
    "t1:r": NO_STUDENTS,
    "t1:g": NO_STUDENTS,
    "t1:gp": NO_STUDENTS,
    "t1:gy": NO_STUDENTS,
    "h1:a": TODAY,
    "h1:b": TODAY,
    "h1:l": TODAY,
    "c1:m": "w1:m",  # no shala: the line saying how to join, and the Menu
    "v1": "c1:m:",  # no classes to mark: Back to My schedule
    "v1:p": "c1:m:",
    "v1:r": "c1:m:",
    "v1:a": "c1:m:",
    "v1:y": "c1:m:",
    "v1:n": "c1:m:",
}
# A platform admin's buttons from anyone else: only answered, like forged data, so the
# review can't be probed (ADR-0042).
ADMIN_ONLY = ("l1:a", "l1:k", "l1:c", "l1:y", "l1:n", "l1:ny")


def _markers(table: dict[str, str | tuple[str, ...]], data: str) -> tuple[str, ...]:
    parts = data.split(":")
    keys = [data, ":".join(parts[:3]), ":".join(parts[:2]), parts[0]]
    found = next(table[key] for key in keys if key in table)
    return (found,) if isinstance(found, str) else found


def _evidence(w: World, body: Any) -> tuple[set[str], str]:
    """Everything the tap put on screen, the webhook reply and direct calls alike: the
    methods, each button's callback data (`url` for a link), `force_reply`,
    `request_location`; and the text."""
    shown: list[dict[str, Any]] = [body] if body else []
    shown += [m.model_dump(exclude_none=True) | {"method": m.__api_method__} for m in w.out]
    found: set[str] = set()
    for message in shown:
        found.add(message["method"])
        markup: dict[str, Any] = message.get("reply_markup") or {}
        if markup.get("force_reply"):
            found.add("force_reply")
        rows: list[list[dict[str, Any]]] = [
            *markup.get("inline_keyboard", []),
            *markup.get("keyboard", []),
        ]
        for button in (b for row in rows for b in row):
            found.add(button.get("callback_data") or "")
            found |= {key for key in ("url", "request_location") if button.get(key)}
    text = "\n".join(m.get("text") or m.get("caption") or "" for m in shown)
    return found, text


def _assert_screen(w: World, data: str, table: dict[str, str | tuple[str, ...]]) -> str:
    body = _tap(w, data)

    found, text = _evidence(w, body)
    assert found & SCREENS, f"{data}: only {sorted(found)}"
    assert "answerCallbackQuery" in found  # and the spinner stops
    for marker in _markers(table, data):
        assert any(item.startswith(marker) for item in found), (
            f"{data}: no {marker!r} in {sorted(found)} under {text[:80]!r}"
        )
    return text


@pytest.mark.parametrize("data", frozen.PRE_UI06_CALLBACKS)
async def test_every_button_shipped_before_ui06_still_gets_a_screen(w: World, data: str) -> None:
    await _seed_for(w, data)

    _assert_screen(w, data, FULL)


@pytest.mark.parametrize("data", frozen.PRE_UI06_CALLBACKS)
def test_every_old_button_gets_a_screen_when_what_it_was_about_is_gone(
    bare: World, data: str
) -> None:
    """Nothing logged, no teacher, student or shala, codes that do not exist: the tap still
    lands on a living screen (UI-06 §5), and on the one nearest to where it was."""
    if data.startswith(ADMIN_ONLY):
        assert _tap(bare, data) is None
        assert bare.sent == ["answerCallbackQuery"]
        return

    text = _assert_screen(bare, data, BARE)

    if _markers(BARE, data) == (EDITOR,) and data.split(":")[0] in ("p1", "k1", "g1", "r1"):
        assert text.startswith(T.t("en", "practice-day-not-practiced"))


def test_the_tables_name_no_entry_that_is_not_in_the_list() -> None:
    """A key that matches nothing would be an expectation nobody checks."""
    used = {
        key
        for data in frozen.PRE_UI06_CALLBACKS
        for key in (data, ":".join(data.split(":")[:3]), ":".join(data.split(":")[:2]))
    } | {data.split(":")[0] for data in frozen.PRE_UI06_CALLBACKS}

    assert set(FULL) <= used
    assert set(BARE) <= used


def test_a_w1_button_also_gets_a_screen(w: World) -> None:
    for data in ("w1:m", "w1:n", "w1:h", "w1:o", "w1:f", "w1:p", "w1:t", "w1:c", "w1:s:f"):
        body = _tap(w, data)
        assert body["method"] == "editMessageText", data


def test_the_buttons_ui06_added_to_old_prefixes_also_get_a_screen(w: World) -> None:
    """Settings' inner screens, the consent layers and the invite's "More" (UI-06 §2)."""
    w.storage.shalas.add_invite(frozen.SHALA, STAFF_CODE, ShalaRole.ASSISTANT)
    new = [
        *("s1:lp", "s1:r", "s1:m", "t1:im"),
        *(f"t1:{letter}:{frozen.TEACHER_CODE}" for letter in ("d", "y")),
        *(f"h1:{letter}:{frozen.SHALA_CODE}" for letter in ("d", "r")),
        *(f"h1:{letter}:{STAFF_CODE}" for letter in ("ds", "rs")),
    ]

    for data in new:
        body = _tap(w, data)
        assert body["method"] == "editMessageText", data
        assert len(data.encode()) <= 22, data


def _taps(body: Any) -> dict[str, str]:
    """Label → callback data of a reply's buttons (URL and Mini App buttons left out)."""
    rows = body["reply_markup"]["inline_keyboard"]
    return {b["text"]: b["callback_data"] for row in rows for b in row if "callback_data" in b}


@pytest.mark.parametrize("world", ["w", "bare"])
@pytest.mark.parametrize("hub", ["w1:m", "w1:h"], ids=["Menu", "Help"])
def test_every_screen_the_menu_and_help_open_has_a_way_back(
    world: str, hub: str, request: pytest.FixtureRequest
) -> None:
    """UI-06 §2: `[☰ Menu]` is the last row of every top-level screen, and inner screens
    keep Back; nothing a person opens from the Menu or from Help is a dead end."""
    w: World = request.getfixturevalue(world)
    back = {T.t("en", "log-back"), T.t("en", "today-back")}
    opened = _taps(_tap(w, hub))
    assert len(opened) >= 5, opened

    dead_ends = [
        f"{label} ({data})"
        for label, data in opened.items()
        if data != "w1:m"  # the Menu itself is where the row leads
        and (screen := _taps(_tap(w, data)))
        and "w1:m" not in screen.values()
        and not back & set(screen)
    ]

    assert dead_ends == []


def test_the_world_is_on_the_lists_own_day(w: World) -> None:
    body = _tap(w, "w1:n")

    date_line, pause = body["text"].split("\n")
    assert date_line == "Today, Sun, Nov 15"
    assert pause.startswith("🤒 Sick / injury through")  # the seeded pause covers it
    assert replace(w.storage.repo.accounts[w.me]).timezone == "Asia/Almaty"
