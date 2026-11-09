"""The teacher view on real Postgres (ST-06, spec §3, §6, §8, ADR-0031), privacy leaks first:
every rest kind reads the same, "No practice" and unlogged read the same, nothing crosses the
link date, the private columns are never named and no key is held. Then the consent column, how
it's written, migration 0020, the export, paging, unlink, statement counts and `EXPLAIN`.

Everything is read through the real use cases, because the clip to a student's today is the
domain's: the SQL alone may return a planned period day."""

import asyncio
import base64
import inspect
import itertools
import json
import time
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from aiogram.client.session.aiohttp import AiohttpSession
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.domain.test_practice import catalog
from tests.fakes import FakeNotifier, FakePacker, FixedClock, cities
from tristhana.api.initdata import sign
from tristhana.application.export import SendMyExport
from tristhana.application.labels import PracticeLabels
from tristhana.application.policies import Principal
from tristhana.application.ports.teacher_links import Caps, NotLinked
from tristhana.application.practice_patch import PracticePatch
from tristhana.application.teacher_view import GetStudent, GetStudents
from tristhana.domain.accounts import Account, IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.notifications import DEFAULTS
from tristhana.domain.practice import PracticeLength
from tristhana.domain.progression import (
    STANDING_ONLY,
    Change,
    EventKind,
    Position,
    Progression,
    Track,
)
from tristhana.domain.rest_periods import RestPeriod
from tristhana.domain.teacher_links import MAX_STUDENTS, MAX_TEACHERS
from tristhana.domain.teacher_view import DayCell, SharedDay, StudentCard, StudentToday
from tristhana.infrastructure.crypto import FieldCipher, MissingCipher
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.days import SqlDayLogRepository
from tristhana.infrastructure.db.export import SqlExportRepository
from tristhana.infrastructure.db.practice import SqlPracticeRepository
from tristhana.infrastructure.db.progression import SqlProgressionRepository
from tristhana.infrastructure.db.rest_periods import SqlRestPeriodRepository
from tristhana.infrastructure.db.storage import PostgresStorage
from tristhana.infrastructure.db.teacher_links import SqlTeacherLinkRepository
from tristhana.infrastructure.db.teacher_view import SqlTeacherViewRepository
from tristhana.infrastructure.i18n.fluent import FluentTranslator
from tristhana.main import create_app
from tristhana.settings import Settings

pytestmark = pytest.mark.db

KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()
TODAY = date(2026, 11, 7)
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
LONG_AGO = date(2026, 6, 1)
ZONE = "Asia/Almaty"
CAPS = Caps(teachers=MAX_TEACHERS, students=MAX_STUDENTS)
NOBODY = UUID(int=0)
LENGTH = PracticeLength(("primary",), "navasana")
P, R = SharedDay.PRACTICED, SharedDay.REST
LOGGED_KINDS = (
    DayStatus.REST,
    DayStatus.LADIES,
    DayStatus.MOON,
    DayStatus.SICK,
    DayStatus.TRAVEL,
)
PERIOD_KINDS = (DayStatus.LADIES, DayStatus.SICK, DayStatus.TRAVEL)
TOKEN = "123456:TEST-token-for-unit-tests-only_xxxxxxxxxxx"
SECRET = "test-secret_123"
_users = itertools.count(70_000)
_codes = itertools.count(1)


def _ago(days: int, today: date = TODAY) -> date:
    return today - timedelta(days=days)


def _noon(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 12, tzinfo=UTC)


@dataclass
class World:
    """A teacher and the real repositories. `at` moves the clock; Almaty and UTC share a date at
    noon UTC, so `TODAY` is both the student's today and `utc_today`."""

    engine: AsyncEngine
    teacher: Account
    clock: FixedClock = field(default_factory=lambda: FixedClock(NOW))
    days: SqlDayLogRepository = field(init=False)
    periods: SqlRestPeriodRepository = field(init=False)
    practices: SqlPracticeRepository = field(init=False)
    links: SqlTeacherLinkRepository = field(init=False)
    view: SqlTeacherViewRepository = field(init=False)

    def __post_init__(self) -> None:
        cipher = FieldCipher(KEYS)
        self.days = SqlDayLogRepository(self.engine, cipher)
        self.periods = SqlRestPeriodRepository(self.engine, cipher)
        self.practices = SqlPracticeRepository(self.engine)
        self.links = SqlTeacherLinkRepository(self.engine)
        self.view = SqlTeacherViewRepository(self.engine)

    def at(self, day: date) -> None:
        self.clock.instant = _noon(day)

    async def student(
        self,
        name: str | None = "Anna",
        *,
        zone: str | None = ZONE,
        linked_on: date | None = LONG_AGO,
        agreed: bool = True,
        teacher: UUID | None = None,
    ) -> UUID:
        account = await _person(self.engine, name)
        await _set(self.engine, account.id, timezone=zone)
        if linked_on is not None:
            await self.link(account.id, linked_on, agreed, teacher)
        return account.id

    async def link(
        self, student: UUID, linked_on: date, agreed: bool, teacher: UUID | None = None
    ) -> None:
        async with self.engine.connect() as conn:
            await conn.execute(
                text(
                    "INSERT INTO tristhana.teacher_link"
                    " (student_id, teacher_id, linked_on, quiet_note_agreed)"
                    " VALUES (:s, :t, :on, :agreed)"
                ),
                {"s": student, "t": teacher or self.teacher.id, "on": linked_on, "agreed": agreed},
            )

    async def log(self, student: UUID, day: date, status: DayStatus) -> None:
        await self.days.upsert(student, DayLog(day, status), ZONE)

    async def practiced(self, student: UUID, day: date, length: PracticeLength = LENGTH) -> None:
        await self.log(student, day, DayStatus.PRACTICED)
        saved = await self.practices.save(student, day, PracticePatch.of(length=length))
        assert saved is not None

    async def period(self, student: UUID, start: date, end: date, kind: DayStatus) -> None:
        placed = await self.periods.place(student, RestPeriod(start, end, kind))
        assert placed.period is not None

    async def card(self, student: UUID) -> StudentCard:
        use_case = GetStudent(self.view, self.clock, Track(catalog()))
        return await use_case.execute(Principal(self.teacher), student)

    async def listing(self, offset: int = 0, limit: int = 50) -> tuple[list[StudentToday], int]:
        use_case = GetStudents(self.view, self.clock)
        found, total = await use_case.execute(Principal(self.teacher), offset, limit)
        return list(found), total

    async def today_of(self, student: UUID) -> SharedDay | None:
        found, _ = await self.listing()
        return next(s.today for s in found if s.id == student)


async def _person(engine: AsyncEngine, name: str | None = "Person", locale: str = "en") -> Account:
    return await SqlAccountRepository(engine).create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, str(next(_users))),
        NewAccount(display_name=name, locale=locale),  # type: ignore[arg-type]
    )


async def _set(engine: AsyncEngine, account: UUID, **columns: Any) -> None:
    assignments = ", ".join(f"{c} = :{c}" for c in columns)
    async with engine.connect() as conn:
        await conn.execute(
            text(f"UPDATE tristhana.account SET {assignments} WHERE id = :id"),  # noqa: S608
            columns | {"id": account},
        )


async def _flag(engine: AsyncEngine, student: UUID, teacher: UUID) -> bool | None:
    async with engine.connect() as conn:
        found = await conn.execute(
            text(
                "SELECT quiet_note_agreed FROM tristhana.teacher_link"
                " WHERE student_id = :s AND teacher_id = :t"
            ),
            {"s": student, "t": teacher},
        )
        return found.scalar_one_or_none()


@pytest.fixture
async def world(engine: AsyncEngine) -> World:
    return World(engine, await _person(engine, "Лена"))


def _anon(card: StudentCard) -> StudentCard:
    """Two students differ by id: everything else must match."""
    return replace(card, id=NOBODY)


def _shown(card: StudentCard) -> dict[date, SharedDay]:
    return {d.date: d.shown for d in card.days if d.shown is not None}


def _assert_all_equal(cards: list[StudentCard]) -> None:
    first, *rest = [_anon(c) for c in cards]
    for other in rest:
        assert other == first


# Kind matrix: every rest looks the same


@pytest.mark.parametrize("kind", LOGGED_KINDS, ids=lambda k: f"logged-{k.value}")
async def test_a_logged_rest_of_any_kind_is_rest(world: World, kind: DayStatus) -> None:
    student = await world.student()
    await world.log(student, TODAY, kind)

    card = await world.card(student)

    assert _shown(card) == {TODAY: R}
    assert await world.today_of(student) is R


@pytest.mark.parametrize("kind", PERIOD_KINDS, ids=lambda k: f"period-{k.value}")
async def test_a_period_of_any_kind_is_rest(world: World, kind: DayStatus) -> None:
    student = await world.student()
    await world.period(student, _ago(2), TODAY, kind)

    card = await world.card(student)

    assert _shown(card) == {_ago(2): R, _ago(1): R, TODAY: R}
    assert await world.today_of(student) is R


@pytest.mark.parametrize("age", [0, 3, 20, 21], ids=lambda a: f"{a}-days-ago")
async def test_swapping_any_kind_for_another_gives_a_deep_equal_card_and_list(
    world: World, age: int
) -> None:
    """Two days of each kind, logged or as a period, `age` days before today. At 21 the note is
    in play too, so it's covered by the same comparison."""
    second, first = _ago(age), _ago(age + 1)
    students: list[UUID] = []
    for kind in LOGGED_KINDS:
        student = await world.student()
        await world.log(student, first, kind)
        await world.log(student, second, kind)
        students.append(student)
    for kind in PERIOD_KINDS:
        student = await world.student()
        await world.period(student, first, second, kind)
        students.append(student)

    cards = [await world.card(s) for s in students]
    found, total = await world.listing()

    _assert_all_equal(cards)
    assert cards[0].quiet is (age == 21)
    assert total == len(students)
    assert len({(s.name, s.today) for s in found}) == 1


# Blank matrix: "No practice", unlogged, auto moon and auto day off are one thing


async def _blank_days(world: World, student: UUID, case: str, days: int = 21) -> None:
    window = [_ago(n) for n in range(days)]
    match case:
        case "no-practice":
            for day in window:
                await world.log(student, day, DayStatus.SKIPPED)
        case "auto-moon":
            async with world.engine.connect() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO tristhana.moon_day (location, date, kind)"
                        " VALUES ('mysuru', :d, 'purnima') ON CONFLICT DO NOTHING"
                    ),
                    [{"d": day} for day in window],
                )
            moon = await world.days.range_with_moon(student, window[-1], TODAY, "mysuru")
            assert moon.moon_dates == frozenset(window)  # really an auto moon day to the student
        case "auto-day-off":
            await _set(world.engine, student, day_off=127, day_off_since=LONG_AGO)
        case _:
            assert case == "unlogged"


BLANKS = ["no-practice", "unlogged", "auto-moon", "auto-day-off"]


@pytest.mark.parametrize("case", BLANKS)
async def test_each_blank_kind_is_blank_and_brings_the_note(world: World, case: str) -> None:
    student = await world.student(agreed=True)
    await _blank_days(world, student, case)

    card = await world.card(student)

    assert _shown(card) == {}
    assert [d.length for d in card.days] == [None] * 7
    assert card.quiet is True
    assert await world.today_of(student) is None


async def test_21_days_of_no_practice_and_21_of_nothing_are_deep_equal_quiet_included(
    world: World,
) -> None:
    """The flag is true, so the note is really in play: it must not tell them apart."""
    students: list[UUID] = []
    for case in BLANKS:
        student = await world.student(agreed=True)
        await _blank_days(world, student, case)
        students.append(student)

    cards = [await world.card(s) for s in students]
    found, _ = await world.listing()

    _assert_all_equal(cards)
    assert all(c.quiet is True for c in cards)
    assert {(s.name, s.today) for s in found} == {("Anna", None)}


@pytest.mark.parametrize("days", [1, 7, 20])
async def test_a_shorter_run_of_no_practice_is_deep_equal_to_nothing(
    world: World, days: int
) -> None:
    """A blank week without the note must not prove someone tapped "No practice"."""
    tapped, silent = await world.student(agreed=True), await world.student(agreed=True)
    for student in (tapped, silent):
        await world.log(student, _ago(days), DayStatus.REST)
    await _blank_days(world, tapped, "no-practice", days)

    _assert_all_equal([await world.card(tapped), await world.card(silent)])


# Logged beats period


async def test_no_practice_inside_a_period_stays_blank(world: World) -> None:
    student = await world.student()
    await world.period(student, _ago(5), _ago(1), DayStatus.SICK)
    await world.log(student, _ago(3), DayStatus.SKIPPED)

    card = await world.card(student)

    assert _shown(card) == {_ago(n): R for n in (5, 4, 2, 1)}


async def test_no_practice_today_inside_a_period_is_blank_on_the_list(world: World) -> None:
    student = await world.student()
    await world.period(student, _ago(2), TODAY + timedelta(days=2), DayStatus.LADIES)
    await world.log(student, TODAY, DayStatus.SKIPPED)

    assert await world.today_of(student) is None


async def test_practiced_inside_a_period_stays_practiced(world: World) -> None:
    student = await world.student()
    await world.period(student, _ago(5), _ago(1), DayStatus.TRAVEL)
    await world.practiced(student, _ago(2))

    card = await world.card(student)

    assert _shown(card)[_ago(2)] is P
    assert next(d for d in card.days if d.date == _ago(2)).length == LENGTH


async def test_a_practiced_row_left_inside_an_uncut_period_still_wins(world: World) -> None:
    """Logging 🧘 cuts a period, so this pins the `NOT EXISTS` by itself, with no cut to help."""
    student = await world.student()
    await world.log(student, _ago(3), DayStatus.PRACTICED)
    await world.period(student, _ago(5), _ago(4), DayStatus.TRAVEL)
    async with world.engine.connect() as conn:
        await conn.execute(
            text("UPDATE tristhana.rest_period SET end_date = :e WHERE account_id = :a"),
            {"e": _ago(1), "a": student},
        )

    assert _shown(await world.card(student)) == {
        _ago(5): R,
        _ago(4): R,
        _ago(3): P,
        _ago(2): R,
        _ago(1): R,
    }


# A rest period can't trigger the note


@pytest.mark.parametrize(
    ("after", "quiet"), [(-13, False), (-1, False), (0, False), (20, False), (21, True)]
)
async def test_a_14_day_period_brings_no_note_until_21_days_after_its_last_day(
    world: World, after: int, quiet: bool
) -> None:
    last = date(2026, 10, 1)
    student = await world.student(agreed=True)
    await world.period(student, last - timedelta(days=13), last, DayStatus.LADIES)

    world.at(last + timedelta(days=after))

    assert (await world.card(student)).quiet is quiet


# The future


async def test_future_days_of_a_current_period_are_absent(world: World) -> None:
    student = await world.student()
    await world.period(student, _ago(1), TODAY + timedelta(days=5), DayStatus.TRAVEL)

    card = await world.card(student)

    assert card.days[-1].date == TODAY
    assert _shown(card) == {_ago(1): R, TODAY: R}


async def test_a_period_ending_soon_and_one_ending_later_read_the_same(world: World) -> None:
    """A teacher can't read a planned end date, not even from the day after `utc_today`."""
    near, far = await world.student(), await world.student()
    await world.period(near, _ago(1), TODAY + timedelta(days=1), DayStatus.SICK)
    await world.period(far, _ago(1), TODAY + timedelta(days=12), DayStatus.SICK)

    _assert_all_equal([await world.card(near), await world.card(far)])


async def test_tomorrows_period_day_shows_only_once_it_is_today(world: World) -> None:
    student = await world.student(zone="UTC")
    await world.period(
        student, TODAY + timedelta(days=1), TODAY + timedelta(days=3), DayStatus.SICK
    )

    assert await world.today_of(student) is None
    assert _shown(await world.card(student)) == {}

    world.at(TODAY + timedelta(days=1))

    assert await world.today_of(student) is R


# The link date


async def test_the_link_date_itself_shows_and_the_day_before_does_not(world: World) -> None:
    student = await world.student(linked_on=_ago(2))
    await world.practiced(student, _ago(3))
    await world.practiced(student, _ago(2))

    card = await world.card(student)

    assert _shown(card) == {_ago(2): P}
    assert next(d for d in card.days if d.date == _ago(3)) == DayCell(_ago(3), None, None)


async def test_a_day_logged_before_the_link_was_made_on_the_link_date_shows(world: World) -> None:
    """ "From today on": a plain date comparison, so the time of the tap doesn't matter."""
    student = await world.student(linked_on=None)
    await world.log(student, TODAY, DayStatus.PRACTICED)

    await world.link(student, TODAY, True)

    assert await world.today_of(student) is P


async def test_a_later_backfill_before_the_link_date_never_shows(world: World) -> None:
    student = await world.student(linked_on=_ago(1))

    await world.log(student, _ago(2), DayStatus.PRACTICED)
    await world.log(student, _ago(4), DayStatus.SICK)

    assert _shown(await world.card(student)) == {}


@pytest.mark.parametrize("kind", PERIOD_KINDS, ids=lambda k: k.value)
async def test_a_period_clips_to_the_link_date(world: World, kind: DayStatus) -> None:
    student = await world.student(linked_on=_ago(2))
    await world.period(student, _ago(5), _ago(1), kind)

    assert _shown(await world.card(student)) == {_ago(2): R, _ago(1): R}


async def test_a_period_wholly_before_the_link_date_is_absent(world: World) -> None:
    student = await world.student(linked_on=_ago(2))
    await world.period(student, _ago(6), _ago(3), DayStatus.SICK)

    assert _shown(await world.card(student)) == {}


async def test_lengths_stop_at_the_link_date_too(world: World) -> None:
    student = await world.student(linked_on=_ago(1))
    await world.practiced(student, _ago(2))
    await world.practiced(student, _ago(1))

    detail = await world.view.student(world.teacher.id, student, _ago(21), TODAY)

    assert detail is not None
    assert set(detail.lengths) == {_ago(1)}


async def test_the_link_date_is_the_stored_one_not_created_at(world: World) -> None:
    student = await world.student(linked_on=_ago(1))
    await world.log(student, _ago(2), DayStatus.PRACTICED)
    async with world.engine.connect() as conn:
        await conn.execute(
            text("UPDATE tristhana.teacher_link SET created_at = :at"),
            {"at": NOW - timedelta(days=30)},
        )

    assert _shown(await world.card(student)) == {}


async def test_each_link_clips_at_its_own_date(world: World) -> None:
    other = await _person(world.engine, "Boris")
    student = await world.student(linked_on=_ago(1))
    await world.link(student, _ago(3), True, other.id)
    await world.log(student, _ago(2), DayStatus.PRACTICED)
    second_view = replace(world, teacher=other)

    assert _shown(await world.card(student)) == {}
    assert _shown(await second_view.card(student)) == {_ago(2): P}


async def test_a_re_link_hides_the_earlier_links_days(world: World) -> None:
    student = await world.student(linked_on=_ago(5))
    await world.log(student, _ago(3), DayStatus.PRACTICED)
    assert _shown(await world.card(student)) == {_ago(3): P}

    assert await world.links.unlink(student, world.teacher.id)
    await world.link(student, _ago(1), True)

    assert _shown(await world.card(student)) == {}


async def test_the_note_counts_only_since_the_link(world: World) -> None:
    fresh = await world.student(linked_on=_ago(20), agreed=True)
    older = await world.student(linked_on=_ago(21), agreed=True)

    assert (await world.card(fresh)).quiet is False
    assert (await world.card(older)).quiet is True


# Compiled SQL names nothing private


FORBIDDEN = (
    "sealed_status",
    "sealed_kind",
    "last_seen_at",
    "context",
    "online",
    "duration_min",
    "start_time",
    "items",
    "hint_",
    "marked_by",
    "is_primary",
    "progression_event",
    "check_in",
    "diary",
    "practice_milestone",
    # §3, §6: the student's `Account` isn't in reach, and `created_at` never sets the boundary.
    "day_off",
    "hide_ladies",
    "moon_location",
    "created_at",
)


@contextmanager
def _statements(engine: AsyncEngine) -> Generator[list[tuple[str, Any]]]:
    seen: list[tuple[str, Any]] = []

    def record(_conn: object, _cursor: object, statement: str, parameters: Any, *_: object) -> None:
        if "tristhana." in statement:
            seen.append((statement, parameters))

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)


async def _seeded(world: World) -> UUID:
    """A student with a bit of everything the statements could touch."""
    student = await world.student(agreed=True)
    await world.practiced(student, _ago(1))
    await world.log(student, TODAY, DayStatus.LADIES)
    await world.period(student, _ago(6), _ago(4), DayStatus.SICK)
    await world.log(student, _ago(2), DayStatus.SKIPPED)
    position = Position("primary", "navasana")
    start = Change(EventKind.START, TODAY, Progression(position), after=position)
    await SqlProgressionRepository(world.engine).apply(student, start, None, student, before=None)
    return student


async def _read_statement(world: World, read: str, student: UUID) -> tuple[str, Any]:
    with _statements(world.engine) as seen:
        if read == "list":
            found, _ = await world.listing()
            assert [s.id for s in found] == [student]
        else:
            assert (await world.card(student)).last_asana is not None
    assert len(seen) == 1, "one statement per call"
    return seen[0]


@pytest.mark.parametrize("read", ["list", "card"])
@pytest.mark.parametrize("name", FORBIDDEN)
async def test_a_statement_names_no_private_column(world: World, read: str, name: str) -> None:
    statement, _ = await _read_statement(world, read, await _seeded(world))

    assert name not in statement


async def test_only_the_card_statement_names_the_flag(world: World) -> None:
    student = await _seeded(world)

    listed, _ = await _read_statement(world, "list", student)
    carded, _ = await _read_statement(world, "card", student)

    assert "quiet_note_agreed" not in listed
    assert "quiet_note_agreed" in carded


@pytest.mark.parametrize("read", ["list", "card"])
async def test_no_practice_is_never_asked_for(world: World, read: str) -> None:
    """The status list comes from `SHARED`, so `skipped` is neither read nor filtered by name."""
    statement, parameters = await _read_statement(world, read, await _seeded(world))

    assert "skipped" not in f"{statement} {parameters!r}"


@pytest.mark.parametrize("read", ["list", "card"])
async def test_the_status_list_holds_every_stored_status_shared_shows(
    world: World, read: str
) -> None:
    statement, parameters = await _read_statement(world, read, await _seeded(world))

    seen = f"{statement} {parameters!r}"
    for status in ("practiced", "rest", "moon", "sick", "travel"):
        assert status in seen


def test_the_repository_takes_no_cipher() -> None:
    assert list(inspect.signature(SqlTeacherViewRepository).parameters) == ["engine"]


async def test_the_whole_path_runs_with_no_cipher_configured(
    world: World, migrated_url: str
) -> None:
    student = await world.student(agreed=True)
    await world.log(student, TODAY, DayStatus.LADIES)  # sealed by the world's own key
    await world.period(student, _ago(4), _ago(2), DayStatus.LADIES)
    storage = PostgresStorage(
        migrated_url, ca_file=None, pool_size=1, max_overflow=0, cipher=MissingCipher()
    )
    await storage.start()
    try:
        principal = Principal(world.teacher)
        card = await GetStudent(storage.teacher_view, world.clock, Track(catalog())).execute(
            principal, student
        )
        found, _ = await GetStudents(storage.teacher_view, world.clock).execute(principal, 0, 10)
    finally:
        await storage.stop()

    assert _shown(card) == {_ago(4): R, _ago(3): R, _ago(2): R, TODAY: R}
    assert [s.today for s in found] == [R]


# The repository's own shapes


async def test_the_repository_returns_only_shared_days(world: World) -> None:
    student = await _seeded(world)

    detail = await world.view.student(world.teacher.id, student, _ago(21), TODAY)
    page = await world.view.page(world.teacher.id, 0, 10, _ago(1), TODAY)

    assert detail is not None
    for shown in (detail.log.shown, page.students[0].shown):
        assert all(type(value) is SharedDay for value in shown.values())


async def test_a_length_comes_only_with_a_shown_practiced_day(world: World) -> None:
    student = await world.student()
    await world.practiced(student, _ago(1))
    await world.practiced(student, _ago(2))
    await world.log(student, _ago(2), DayStatus.REST)  # a change of mind clears the practice

    detail = await world.view.student(world.teacher.id, student, _ago(21), TODAY)

    assert detail is not None
    assert detail.lengths == {_ago(1): LENGTH}


async def test_a_practiced_day_with_no_length_has_none(world: World) -> None:
    student = await world.student()
    await world.log(student, TODAY, DayStatus.PRACTICED)

    card = await world.card(student)

    assert card.days[-1] == DayCell(TODAY, P, None)


@pytest.mark.parametrize(
    "length",
    [
        PracticeLength(),
        PracticeLength(("primary",)),
        PracticeLength(("primary", "intermediate"), "kapotasana", "second_half"),
    ],
    ids=["short", "full", "two-series"],
)
async def test_every_shape_of_length_survives_the_read(
    world: World, length: PracticeLength
) -> None:
    student = await world.student()
    await world.practiced(student, TODAY, length)

    assert (await world.card(student)).days[-1].length == length


async def test_the_last_asana_is_current_state_visible_from_the_start(world: World) -> None:
    student = await world.student(linked_on=TODAY)
    position = Position("intermediate", "kapotasana")
    start = Change(EventKind.START, _ago(90), Progression(position), after=position)
    await SqlProgressionRepository(world.engine).apply(student, start, None, student, before=None)

    assert (await world.card(student)).last_asana == position


async def test_not_set_is_none_and_standing_only_is_a_position(world: World) -> None:
    unset, standing = await world.student(), await world.student()
    start = Change(EventKind.START, TODAY, Progression(STANDING_ONLY), after=STANDING_ONLY)
    await SqlProgressionRepository(world.engine).apply(standing, start, None, standing, before=None)

    assert (await world.card(unset)).last_asana is None
    assert (await world.card(standing)).last_asana == STANDING_ONLY


async def test_the_port_carries_the_students_zone_and_locale_to_the_use_case(world: World) -> None:
    student = await world.student("Anna", zone="Asia/Kathmandu", linked_on=_ago(3))
    await _set(world.engine, student, locale="ru")

    detail = await world.view.student(world.teacher.id, student, _ago(21), TODAY)

    assert detail is not None
    link = detail.log.link
    assert (link.teacher_id, link.student_id, link.name) == (world.teacher.id, student, "Anna")
    assert (link.timezone, link.locale, link.linked_on) == ("Asia/Kathmandu", "ru", _ago(3))


# Time zones, on the real statements


async def test_two_students_on_one_instant_read_their_own_dates(world: World) -> None:
    west = await world.student("A", zone="Pacific/Honolulu")
    east = await world.student("B", zone="Pacific/Kiritimati")
    world.clock.instant = datetime(2026, 11, 7, 10, 30, tzinfo=UTC)
    await world.log(west, date(2026, 11, 7), DayStatus.PRACTICED)  # their today: 00:30
    await world.log(east, date(2026, 11, 7), DayStatus.PRACTICED)  # their yesterday
    await world.log(east, date(2026, 11, 8), DayStatus.SICK)  # their today: 00:30

    found, _ = await world.listing()
    card = await world.card(east)

    assert [s.today for s in found] == [P, R]
    assert card.days[-1] == DayCell(date(2026, 11, 8), R, None)


async def test_a_shown_day_on_the_oldest_date_of_the_range_keeps_the_note_away(
    world: World,
) -> None:
    """Honolulu at 09:00 UTC: today is `utc_today - 1`, so its today - 20 is `utc_today - 21`."""
    world.clock.instant = datetime(2026, 11, 7, 9, tzinfo=UTC)
    student = await world.student(zone="Pacific/Honolulu", agreed=True)
    await world.log(student, date(2026, 10, 17), DayStatus.SICK)

    assert (await world.card(student)).quiet is False


async def test_the_last_day_of_an_old_period_on_the_oldest_date_keeps_the_note_away(
    world: World,
) -> None:
    """The 13 in `:since - 13`: a 14-day period that began 34 days back still reaches the range."""
    world.clock.instant = datetime(2026, 11, 7, 9, tzinfo=UTC)
    student = await world.student(zone="Pacific/Honolulu", agreed=True)
    await world.period(student, date(2026, 10, 4), date(2026, 10, 17), DayStatus.SICK)

    assert (await world.card(student)).quiet is False


async def test_an_unknown_zone_uses_the_students_locale(world: World) -> None:
    world.clock.instant = datetime(2026, 11, 7, 21, 30, tzinfo=UTC)  # Moscow: Nov 8, 00:30
    student = await world.student(zone=None)
    await _set(world.engine, student, locale="ru")
    await world.log(student, date(2026, 11, 8), DayStatus.PRACTICED)

    assert await world.today_of(student) is P


# The consent column


async def test_two_students_alike_but_for_the_flag(world: World) -> None:
    """21 blank days each: false gives no note, true gives it, and all else is deep-equal."""
    agreed = await world.student(agreed=True)
    older = await world.student(agreed=False)
    for student in (agreed, older):
        await world.practiced(student, _ago(21))

    with_flag, without = await world.card(agreed), await world.card(older)

    assert with_flag.quiet is True
    assert without.quiet is False
    assert replace(_anon(with_flag), quiet=False) == _anon(without)


async def test_the_flag_is_per_link_so_the_same_student_differs_by_teacher(world: World) -> None:
    other = await _person(world.engine, "Boris")
    student = await world.student(agreed=False)
    await world.link(student, LONG_AGO, True, other.id)

    assert (await world.card(student)).quiet is False
    assert (await replace(world, teacher=other).card(student)).quiet is True


async def _accept(world: World, student: UUID) -> bool:
    code = await world.links.invite(world.teacher.id, f"code{next(_codes):012d}")
    accepted = await world.links.accept(code, student, CAPS, TODAY)
    assert accepted is not None
    return accepted.created


async def test_accept_stores_true(world: World) -> None:
    student = await world.student(linked_on=None)

    assert await _accept(world, student) is True

    assert await _flag(world.engine, student, world.teacher.id) is True


async def test_a_duplicate_accept_on_a_false_row_leaves_it_false(world: World) -> None:
    student = await world.student(agreed=False)

    assert await _accept(world, student) is False

    assert await _flag(world.engine, student, world.teacher.id) is False


async def test_unlink_then_accept_gives_a_new_row_with_true(world: World) -> None:
    student = await world.student(agreed=False)
    assert await world.links.unlink(student, world.teacher.id)

    assert await _accept(world, student) is True

    assert await _flag(world.engine, student, world.teacher.id) is True


async def test_accept_is_still_one_statement(world: World) -> None:
    student = await world.student(linked_on=None)
    code = await world.links.invite(world.teacher.id, "aB3dE6gH9jK2mN5p")

    with _statements(world.engine) as seen:
        await world.links.accept(code, student, CAPS, TODAY)

    assert len(seen) == 1


async def test_no_other_link_write_touches_the_flag(world: World) -> None:
    student = await world.student(agreed=False)

    assert await world.links.set_primary(student, world.teacher.id)

    assert await _flag(world.engine, student, world.teacher.id) is False


# Migration 0020


async def test_0020_leaves_an_existing_row_false_and_old_inserts_get_false(
    migrated_url: str, engine: AsyncEngine
) -> None:
    student, teacher, later = [(await _person(engine)).id for _ in range(3)]
    old_insert = text(
        "INSERT INTO tristhana.teacher_link (student_id, teacher_id, linked_on)"
        " VALUES (:s, :t, :on)"
    )
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0019")
    try:
        async with engine.connect() as conn:
            await conn.execute(old_insert, {"s": student, "t": teacher, "on": TODAY})
    finally:
        await asyncio.to_thread(migrate.upgrade, migrated_url)

    assert await _flag(engine, student, teacher) is False

    async with engine.connect() as conn:  # the old image, during the rollover
        await conn.execute(old_insert, {"s": later, "t": teacher, "on": TODAY})
    assert await _flag(engine, later, teacher) is False


async def test_0020_up_down_up_and_no_drift(migrated_url: str, engine: AsyncEngine) -> None:
    has_column = text(
        "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'tristhana'"
        " AND table_name = 'teacher_link' AND column_name = 'quiet_note_agreed'"
    )
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0019")
    try:
        async with engine.connect() as conn:
            assert (await conn.execute(has_column)).scalar_one() == 0
    finally:
        await asyncio.to_thread(migrate.upgrade, migrated_url)
    async with engine.connect() as conn:
        assert (await conn.execute(has_column)).scalar_one() == 1
    await asyncio.to_thread(migrate.check, migrated_url)


async def test_the_column_is_not_null_and_defaults_to_false(engine: AsyncEngine) -> None:
    async with engine.connect() as conn:
        found = await conn.execute(
            text(
                "SELECT is_nullable, column_default, data_type FROM information_schema.columns"
                " WHERE table_schema = 'tristhana' AND table_name = 'teacher_link'"
                " AND column_name = 'quiet_note_agreed'"
            )
        )
        assert tuple(found.one()) == ("NO", "false", "boolean")


# Export: nothing changes


async def _export(engine: AsyncEngine, who: Account) -> tuple[dict[str, Any], str]:
    packer = FakePacker()
    t = FluentTranslator()
    use_case = SendMyExport(
        SqlExportRepository(engine, FieldCipher(KEYS)),
        packer,
        FakeNotifier(),
        t,
        PracticeLabels(t, catalog(), Track(catalog())),
        cities(),
        "cat-v1",
        FixedClock(NOW),
    )
    await use_case.execute(Principal(who))
    [(data, tables, readme)] = packer.packed
    return data, json.dumps({"data": data, "tables": tables, "readme": readme}, ensure_ascii=False)


@pytest.mark.parametrize("agreed", [True, False])
async def test_the_export_keeps_its_keys_and_holds_no_flag_on_either_side(
    world: World, agreed: bool
) -> None:
    student = await _person(world.engine, "Anna")
    await world.link(student.id, TODAY, agreed)

    for person, side in ((student, "teacher"), (world.teacher, "student")):
        data, everything = await _export(world.engine, person)

        assert data["schema"] == "tristhana.export/1"
        [link] = data["teacher_links"]
        assert set(link) == {"other_side", "primary", "linked_at", "announcements_muted"}
        assert link["other_side"] == side
        assert "quiet_note" not in everything


async def test_the_export_doesnt_even_read_the_flag(world: World) -> None:
    """Its column list is explicit, so the new column must not be added to it (spec §6)."""
    student = await _person(world.engine, "Anna")
    await world.link(student.id, TODAY, True)
    repo = SqlExportRepository(world.engine, FieldCipher(KEYS))

    with _statements(world.engine) as seen:
        assert await repo.snapshot(student.id, DEFAULTS, TODAY) is not None

    assert [s for s, _ in seen if "teacher_link" in s]
    assert not [s for s, _ in seen if "quiet_note_agreed" in s]


async def test_a_teachers_export_cant_show_who_confirmed_which_text(world: World) -> None:
    first, second = await _person(world.engine, "A"), await _person(world.engine, "B")
    await world.link(first.id, TODAY, True)
    await world.link(second.id, TODAY, False)

    data, _ = await _export(world.engine, world.teacher)

    without_instants = [
        {k: v for k, v in link.items() if k != "linked_at"} for link in data["teacher_links"]
    ]
    assert without_instants[0] == without_instants[1]


# Paging


async def test_the_order_is_by_name_then_id_with_no_name_last(world: World) -> None:
    await world.student("boris")
    await world.student(None)
    await world.student("Anna")
    twins = sorted([await world.student("Clara"), await world.student("clara")])

    found, total = await world.listing()

    assert total == 5
    assert [s.name.lower() if s.name else None for s in found] == [
        "anna",
        "boris",
        "clara",
        "clara",
        None,
    ]
    assert [s.id for s in found[2:4]] == twins


async def test_activity_never_moves_anyone(world: World) -> None:
    students = [await world.student(f"S{n}") for n in range(4)]
    before, _ = await world.listing()

    await world.practiced(students[3], TODAY)
    await world.log(students[1], TODAY, DayStatus.SICK)
    after, _ = await world.listing()

    assert [s.id for s in after] == [s.id for s in before]


async def test_pages_partition_the_list_and_carry_the_full_total(world: World) -> None:
    students = {await world.student(f"S{n:02d}") for n in range(7)}

    pages = [await world.listing(offset, 3) for offset in (0, 3, 6)]

    assert [len(found) for found, _ in pages] == [3, 3, 1]
    assert {total for _, total in pages} == {7}
    assert {s.id for found, _ in pages for s in found} == students


async def test_an_offset_past_the_end_is_empty_with_total_0(world: World) -> None:
    await world.student()

    assert await world.listing(5, 3) == ([], 0)


async def test_a_page_holds_only_the_callers_students(world: World) -> None:
    other = await _person(world.engine, "Boris")
    mine = await world.student("Mine")
    await world.student("Theirs", teacher=other.id)

    found, total = await world.listing()

    assert ([s.id for s in found], total) == ([mine], 1)


async def test_a_teacher_with_no_students_gets_an_empty_page(world: World) -> None:
    assert await world.listing() == ([], 0)


async def test_the_list_and_the_card_each_read_only_their_own_range(world: World) -> None:
    student = await world.student()
    await world.log(student, _ago(2), DayStatus.PRACTICED)

    page = await world.view.page(world.teacher.id, 0, 10, _ago(1), TODAY)
    detail = await world.view.student(world.teacher.id, student, _ago(21), TODAY)

    assert page.students[0].shown == {}
    assert detail is not None
    assert detail.log.shown == {_ago(2): P}


# Who can read


async def test_a_stranger_and_the_reverse_direction_get_none(world: World) -> None:
    student = await world.student()
    stranger = await _person(world.engine)

    assert await world.view.student(stranger.id, student, _ago(21), TODAY) is None
    assert await world.view.student(student, world.teacher.id, _ago(21), TODAY) is None


async def test_a_cycle_gives_each_side_its_own_link(world: World) -> None:
    student = await world.student(linked_on=_ago(1))
    await world.link(world.teacher.id, _ago(9), True, student)
    await world.log(student, _ago(2), DayStatus.PRACTICED)

    detail = await world.view.student(world.teacher.id, student, _ago(21), TODAY)

    assert detail is not None
    assert detail.log.link.linked_on == _ago(1)
    assert detail.log.shown == {}


async def test_unlink_removes_the_student_at_once_last_asana_included(world: World) -> None:
    student = await _seeded(world)

    assert await world.links.unlink(student, world.teacher.id)

    with pytest.raises(NotLinked):
        await world.card(student)
    assert await world.listing() == ([], 0)


async def test_deleting_the_student_removes_them_at_once(world: World) -> None:
    student = await _seeded(world)

    assert await SqlAccountRepository(world.engine).delete(student)

    with pytest.raises(NotLinked):
        await world.card(student)
    assert await world.listing() == ([], 0)


async def test_a_read_writes_nothing(world: World) -> None:
    """No read receipts, no view history, no cache table (spec §6)."""
    student = await _seeded(world)

    with _statements(world.engine) as seen:
        await world.card(student)
        await world.listing()

    verbs = {statement.lstrip().split()[0].upper() for statement, _ in seen}
    assert verbs <= {"SELECT", "WITH"}
    assert not any(
        word in statement.upper()
        for statement, _ in seen
        for word in ("INSERT ", "UPDATE ", "DELETE ")
    )


# Statement counts per tap (spec §6: they include the one from the middleware or auth)


@contextmanager
def _all_statements() -> Generator[list[str]]:
    """On the class: the app builds its own engine, inside the TestClient's event loop."""
    seen: list[str] = []

    def record(_conn: object, _cursor: object, statement: str, *_: object) -> None:
        if "tristhana." in statement:
            seen.append(statement)

    event.listen(Engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(Engine, "before_cursor_execute", record)


def _app(url: str) -> Any:
    settings = Settings(
        app_env="test",
        telegram_bot_token=SecretStr(TOKEN),
        telegram_webhook_secret=SecretStr(SECRET),
    )
    storage = PostgresStorage(
        url, ca_file=None, pool_size=2, max_overflow=0, cipher=FieldCipher(KEYS)
    )
    return create_app(settings, storage)


def _api_counts(url: str, telegram_id: int, student: UUID) -> list[int]:
    profile = {"id": telegram_id, "first_name": "Лена", "language_code": "en"}
    fields = {"user": json.dumps(profile), "auth_date": str(int(time.time()) - 60)}
    headers = {"Authorization": f"tma {sign(fields, TOKEN)}"}
    counts: list[int] = []
    with TestClient(_app(url)) as client:
        assert client.get("/api/v1/me", headers=headers).status_code == 200  # warm
        for path in ("/api/v1/me/students", f"/api/v1/me/students/{student}"):
            with _all_statements() as seen:
                assert client.get(path, headers=headers).status_code == 200
            counts.append(len(seen))
    return counts


def _bot_counts(url: str, telegram_id: int, taps: list[str]) -> list[int]:
    def update(n: int, data: str) -> dict[str, Any]:
        user = {"id": telegram_id, "is_bot": False, "first_name": "Лена", "language_code": "en"}
        chat = {"id": telegram_id, "type": "private"}
        message = {"message_id": 9, "date": 1_760_000_000, "chat": chat, "text": "…"}
        callback = {
            "id": f"cb{n}",
            "from": user,
            "chat_instance": "ci",
            "data": data,
            "message": message,
        }
        return {"update_id": n, "callback_query": callback}

    counts: list[int] = []
    headers = {"X-Telegram-Bot-Api-Secret-Token": SECRET}
    with TestClient(_app(url)) as client:
        client.post("/telegram/webhook", json=update(1, "t1:o"), headers=headers)  # warm
        for n, data in enumerate(taps, start=2):
            with _all_statements() as seen:
                assert client.post(
                    "/telegram/webhook", json=update(n, data), headers=headers
                ).is_success
            counts.append(len(seen))
    return counts


async def _telegram_world(engine: AsyncEngine) -> tuple[World, int, UUID]:
    telegram_id = next(_users)
    teacher = await SqlAccountRepository(engine).create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, str(telegram_id)),
        NewAccount(display_name="Лена", locale="en"),
    )
    world = World(engine, teacher)
    student = await _seeded(world)
    return world, telegram_id, student


async def test_each_api_read_is_two_statements(engine: AsyncEngine, migrated_url: str) -> None:
    _, telegram_id, student = await _telegram_world(engine)

    counts = await asyncio.to_thread(_api_counts, migrated_url, telegram_id, student)

    assert counts == [2, 2]


async def test_each_bot_tap_is_two_statements_and_a_stale_page_three(
    engine: AsyncEngine, migrated_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def sent(self: AiohttpSession, bot: object, method: Any, **_: object) -> bool:
        return True

    monkeypatch.setattr(AiohttpSession, "make_request", sent)
    _, telegram_id, student = await _telegram_world(engine)
    taps = ["t1:s:0", f"t1:v:{student}:0", "t1:s:9"]

    counts = await asyncio.to_thread(_bot_counts, migrated_url, telegram_id, taps)

    assert counts == [2, 2, 3]


# 500 students: every read is covered by an index that already exists (spec §7)


async def _seed_500(world: World) -> UUID:
    async with world.engine.connect() as conn:
        await conn.execute(
            text(
                "WITH s AS ("
                " INSERT INTO tristhana.account (display_name, locale, timezone)"
                " SELECT 'Student ' || g, 'en', 'Asia/Almaty' FROM generate_series(1, 500) g"
                " RETURNING id)"
                " INSERT INTO tristhana.teacher_link"
                " (student_id, teacher_id, linked_on, quiet_note_agreed)"
                " SELECT id, :t, :on, true FROM s"
            ),
            {"t": world.teacher.id, "on": LONG_AGO},
        )
        await conn.execute(
            text(
                "INSERT INTO tristhana.day_log (account_id, local_date, status)"
                " SELECT l.student_id, CAST(:today AS date) - n, 'practiced'"
                " FROM tristhana.teacher_link l,"
                " generate_series(0, 39) n"
            ),
            {"today": TODAY},
        )
        await conn.execute(
            text(
                "INSERT INTO tristhana.practice (account_id, local_date, series)"
                " SELECT account_id, local_date, ARRAY['primary'] FROM tristhana.day_log"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO tristhana.rest_period"
                " (account_id, start_date, end_date, sealed_kind)"
                " SELECT l.student_id, CAST(:today AS date) - 60, CAST(:today AS date) - 50,"
                " decode(repeat('00', 42), 'hex')"
                " FROM tristhana.teacher_link l"
            ),
            {"today": TODAY},
        )
        await conn.execute(
            text(
                "INSERT INTO tristhana.progression (account_id, series, last_key)"
                " SELECT student_id, 'primary', 'navasana' FROM tristhana.teacher_link"
            )
        )
        for table in (
            "account",
            "teacher_link",
            "day_log",
            "practice",
            "rest_period",
            "progression",
        ):
            await conn.execute(text(f"ANALYZE tristhana.{table}"))
        found = await conn.execute(text("SELECT student_id FROM tristhana.teacher_link LIMIT 1"))
        return found.scalar_one()


def _nodes(plan: dict[str, Any]) -> Iterator[dict[str, Any]]:
    yield plan
    for child in plan.get("Plans", []):
        yield from _nodes(child)


async def _plan(engine: AsyncEngine, statement: str, parameters: Any) -> list[dict[str, Any]]:
    async with engine.connect() as conn:
        await conn.exec_driver_sql("SET enable_seqscan = off")
        try:
            result = await conn.exec_driver_sql(f"EXPLAIN (FORMAT JSON) {statement}", parameters)
            found = result.scalar_one()
            [plan] = json.loads(found) if isinstance(found, str) else found
        finally:
            await conn.exec_driver_sql("RESET enable_seqscan")
    return list(_nodes(plan["Plan"]))


@pytest.mark.parametrize("read", ["list", "card"])
async def test_no_table_needs_a_sequential_scan_on_500_students(world: World, read: str) -> None:
    """With seq scans priced out, one still appears only where no index can serve the read."""
    student = await _seed_500(world)
    with _statements(world.engine) as seen:
        if read == "list":
            found, total = await world.listing(0, 50)
            assert (len(found), total) == (50, 500)
        else:
            await world.card(student)
    [(statement, parameters)] = seen

    nodes = await _plan(world.engine, statement, parameters)

    scans = [n["Relation Name"] for n in nodes if n["Node Type"] == "Seq Scan"]
    assert scans == []
    assert {n.get("Relation Name") for n in nodes} >= {"teacher_link", "day_log", "rest_period"}
