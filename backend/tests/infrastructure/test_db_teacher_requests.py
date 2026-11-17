"""`TeacherRequestRepository` on real Postgres (ID-07 spec §3, §6, §8; ADR-0046): the CHECKs
and the key; one statement per call; the approval as one atomic statement, also under two
taps, a withdrawal and a personal link at the same moment; validity as a join (leave and
rejoin, the role removed and returned, a student turned staff); the 30-day row and its
recycling; the cascades; the 23503 mapping; that a request grants nothing a link grants; the
closing notes' read; the guard against the policy over every membership; the export; the app
role; and 0029 up, down, up with no drift.

`created_at` is the database's clock, so time passes here by moving the `now` argument, never
by rewriting rows (a backdated request would be older than its own memberships). Races are
forced: `_holding` keeps a transaction open and the call under test is released only once
Postgres shows it waiting."""

import asyncio
import base64
import itertools
import json
from collections.abc import AsyncGenerator, Awaitable, Generator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from tests.domain.test_practice import catalog
from tests.fakes import FakeNotifier, FakePacker, FixedClock, cities
from tristhana.application.export import SendMyExport
from tristhana.application.labels import PracticeLabels
from tristhana.application.policies import Principal, can_ask_teacher
from tristhana.application.ports.export import AccountGone
from tristhana.application.ports.shalas import NewShala, ShalaCaps
from tristhana.application.ports.teacher_links import Caps
from tristhana.application.ports.teacher_requests import (
    Answer,
    Answered,
    ApprovedAll,
    AskedTeacher,
    TeacherChoice,
    Withdrawn,
)
from tristhana.domain.accounts import Account, IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.progression import Track
from tristhana.domain.shalas import (
    MAX_OWNED,
    MAX_PENDING_STAFF_INVITES,
    MAX_STAFF,
    MAX_STAFF_OF,
    MAX_STUDENT_OF,
    MAX_STUDENTS,
    Membership,
    ShalaRole,
)
from tristhana.domain.teacher_links import MAX_STUDENTS as LINK_STUDENTS
from tristhana.domain.teacher_links import MAX_TEACHERS
from tristhana.domain.teacher_requests import (
    ANSWER_WITHIN,
    CAPS,
    KEEP,
    AskState,
    Closing,
    RequestCaps,
    RequestState,
    ask_state,
    request_key,
)
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.export import SqlExportRepository
from tristhana.infrastructure.db.notifications import SqlNotificationRepository
from tristhana.infrastructure.db.progression import SqlProgressionRepository
from tristhana.infrastructure.db.shalas import SqlShalaRepository, every_membership
from tristhana.infrastructure.db.teacher_links import SqlTeacherLinkRepository
from tristhana.infrastructure.db.teacher_requests import SqlTeacherRequestRepository
from tristhana.infrastructure.db.teacher_view import SqlTeacherViewRepository
from tristhana.infrastructure.i18n.fluent import FluentTranslator

pytestmark = pytest.mark.db

ON = date(2026, 11, 17)
IN_A_WEEK = datetime.now(UTC) + timedelta(days=7)  # staff invites expire on the real clock
SHALA_CAPS = ShalaCaps(
    owned=MAX_OWNED,
    staff=MAX_STAFF,
    students=MAX_STUDENTS,
    staff_of=MAX_STAFF_OF,
    student_of=MAX_STUDENT_OF,
    pending_invites=MAX_PENDING_STAFF_INVITES,
)
LINK_CAPS = Caps(teachers=MAX_TEACHERS, students=LINK_STUDENTS)
KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()
TEACHER, ASSISTANT, OFFICE, ADMIN = (
    ShalaRole.TEACHER,
    ShalaRole.ASSISTANT,
    ShalaRole.OFFICE,
    ShalaRole.ADMIN,
)
WAITING, DECLINED, WITHDRAWN, APPROVED = (s.value for s in RequestState)
_users = itertools.count(120_000)
_codes = itertools.count(1)


def _now(later: timedelta = timedelta(0)) -> datetime:
    """The real clock, a few seconds ahead so a slow test host can't land before a row."""
    return datetime.now(UTC) + timedelta(seconds=5) + later


def _code(prefix: str) -> str:
    return f"{prefix}{next(_codes):0{16 - len(prefix)}d}"


async def _person(engine: AsyncEngine, name: str | None = "Person", locale: str = "en") -> Account:
    repo = SqlAccountRepository(engine)
    account = await repo.create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, str(next(_users))),
        NewAccount(display_name=name, locale=locale),  # type: ignore[arg-type]
    )
    return await repo.set_timezone_if_unset(account.id, "Asia/Almaty")


async def _sql(engine: AsyncEngine, statement: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        return await conn.execute(text(statement), params)


async def _scalar(engine: AsyncEngine, statement: str, **params: Any) -> Any:
    return (await _sql(engine, statement, **params)).scalar_one_or_none()


async def _count(engine: AsyncEngine, table: str) -> int:
    return await _scalar(engine, f"SELECT count(*) FROM tristhana.{table}")  # noqa: S608


class World:
    """One shala with its owner (no role), ready for teachers and students."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.requests = SqlTeacherRequestRepository(engine)
        self.shalas = SqlShalaRepository(engine)
        self.links = SqlTeacherLinkRepository(engine)
        self.owner: Account
        self.shala: UUID

    @classmethod
    async def make(cls, engine: AsyncEngine) -> "World":
        world = cls(engine)
        world.owner = await _person(engine, "Olga")
        world.shala = await world.new_shala(world.owner)
        return world

    async def new_shala(self, owner: Account, name: str = "Ashtanga Almaty") -> UUID:
        card = await self.shalas.create(
            owner.id, NewShala(name, "almaty", False, frozenset(), _code("J")), SHALA_CAPS, ON
        )
        assert card is not None
        return card.id

    async def staff(
        self, role: ShalaRole = TEACHER, name: str = "Anna", locale: str = "ru"
    ) -> Account:
        account = await _person(self.engine, name, locale)
        await self.make_staff(account, role)
        return account

    async def make_staff(self, account: Account, role: ShalaRole = TEACHER) -> None:
        code = _code("S")
        invited = await self.shalas.invite_staff(
            self.shala, self.owner.id, role, code, IN_A_WEEK, SHALA_CAPS
        )
        assert invited.done
        accepted = await self.shalas.accept_staff(code, account.id, SHALA_CAPS, ON)
        assert accepted is not None
        assert accepted.created

    async def student(self, name: str | None = "Ash", shala: UUID | None = None) -> Account:
        account = await _person(self.engine, name)
        await self.join(account, shala)
        return account

    async def join(self, account: Account, shala: UUID | None = None) -> None:
        code = await _scalar(
            self.engine,
            "SELECT join_code FROM tristhana.shala WHERE id = :s",
            s=shala or self.shala,
        )
        joined = await self.shalas.join(code, account.id, SHALA_CAPS, ON)
        assert joined is not None
        assert joined.created

    async def roles(self, account: Account, *roles: ShalaRole) -> None:
        await _sql(
            self.engine,
            "UPDATE tristhana.shala_staff SET roles = :r WHERE shala_id = :s AND account_id = :a",
            r=sorted(r.value for r in roles),
            s=self.shala,
            a=account.id,
        )

    async def ask(
        self,
        student: Account,
        teacher: Account,
        *,
        caps: RequestCaps = CAPS,
        now: datetime | None = None,
        agreed: bool = True,
        asked_on: date = ON,
        shala: UUID | None = None,
    ) -> AskState | None:
        guarded = await self.requests.ask(
            shala or self.shala, student.id, teacher.id, asked_on, agreed, caps, now or _now()
        )
        return guarded.value.state if guarded.value else None

    async def asked(self, student: Account, teacher: Account, **kw: Any) -> None:
        assert await self.ask(student, teacher, **kw) is AskState.CREATED

    async def link(self, student: Account, teacher: Account) -> None:
        code = await self.links.invite(teacher.id, _code("T"))
        accepted = await self.links.accept(code, student.id, LINK_CAPS, date(2026, 11, 20))
        assert accepted is not None
        assert accepted.created

    async def state(self, student: Account, teacher: Account) -> str | None:
        return await _scalar(
            self.engine,
            "SELECT state FROM tristhana.teacher_request WHERE student_id = :s AND teacher_id = :t",
            s=student.id,
            t=teacher.id,
        )

    async def link_row(self, student: Account, teacher: Account) -> Any:
        found = await _sql(
            self.engine,
            "SELECT linked_on, quiet_note_agreed, is_primary, created_at"
            " FROM tristhana.teacher_link WHERE student_id = :s AND teacher_id = :t",
            s=student.id,
            t=teacher.id,
        )
        return found.one_or_none()


@pytest.fixture
async def world(engine: AsyncEngine) -> World:
    return await World.make(engine)


@contextmanager
def _statements(engine: AsyncEngine) -> Generator[list[str]]:
    seen: list[str] = []

    def record(_conn: object, _cursor: object, statement: str, *_: object) -> None:
        if "tristhana." in statement:
            seen.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)


@asynccontextmanager
async def _holding(engine: AsyncEngine) -> AsyncGenerator[AsyncConnection]:
    """An open transaction on its own connection. `COMMIT` is the test's to send; the
    `ROLLBACK` after it is only a warning in Postgres."""
    async with engine.connect() as conn:
        await conn.execute(text("BEGIN"))
        try:
            yield conn
        finally:
            await conn.execute(text("ROLLBACK"))


async def _blocked[T](engine: AsyncEngine, work: Awaitable[T]) -> "asyncio.Future[T]":
    """Starts `work` and returns once Postgres shows it waiting on a lock."""
    task = asyncio.ensure_future(work)
    query = text(
        "SELECT count(*) FROM pg_stat_activity"
        " WHERE datname = current_database() AND wait_event_type = 'Lock'"
    )
    for _ in range(200):
        async with engine.connect() as conn:
            if (await conn.execute(query)).scalar_one() > 0:
                return task
        if task.done():
            break
        await asyncio.sleep(0.01)
    raise AssertionError("the call never waited on the open transaction")


# The CHECKs and the key

_INSERT = (
    "INSERT INTO tristhana.teacher_request"
    " (student_id, teacher_id, shala_id, state, asked_on, quiet_note_agreed)"
    " VALUES (:s, :t, :h, :state, :on, true)"
)


async def test_the_checks_and_the_pair_as_the_key(world: World) -> None:
    teacher, student = await world.staff(), await world.student()
    row = {"s": student.id, "t": teacher.id, "h": world.shala, "state": WAITING, "on": ON}

    for bad in ({"state": "expired"}, {"state": "pending"}, {"t": student.id}):
        with pytest.raises(IntegrityError, match="teacher_request"):
            await _sql(world.engine, _INSERT, **(row | bad))
    await _sql(world.engine, _INSERT, **row)
    with pytest.raises(IntegrityError, match="teacher_request_pkey"):  # one row per pair
        await _sql(world.engine, _INSERT, **(row | {"state": DECLINED}))
    for state in (DECLINED, WITHDRAWN, APPROVED):
        await _sql(world.engine, "UPDATE tristhana.teacher_request SET state = :x", x=state)


async def test_the_consent_and_the_date_have_no_default(world: World) -> None:
    teacher, student = await world.staff(), await world.student()

    for columns in ("asked_on", "quiet_note_agreed"):
        value = ":on" if columns == "asked_on" else "true"
        with pytest.raises(IntegrityError):
            await _sql(
                world.engine,
                "INSERT INTO tristhana.teacher_request"  # noqa: S608
                f" (student_id, teacher_id, shala_id, {columns}) VALUES (:s, :t, :h, {value})",
                s=student.id,
                t=teacher.id,
                h=world.shala,
                **({"on": ON} if columns == "asked_on" else {}),
            )


# One statement per call (spec §7)


async def test_each_call_is_one_statement(world: World) -> None:
    teacher, other = await world.staff(), await world.staff(name="Boris")
    student, second = await world.student(), await world.student("Bea")
    repo, engine = world.requests, world.engine
    calls: list[tuple[str, Any]] = [
        ("choices", lambda: repo.choices(world.shala, student.id, _now())),
        ("ask", lambda: repo.ask(world.shala, student.id, teacher.id, ON, True, CAPS, _now())),
        ("ask2", lambda: repo.ask(world.shala, second.id, teacher.id, ON, True, CAPS, _now())),
        ("ask3", lambda: repo.ask(world.shala, student.id, other.id, ON, True, CAPS, _now())),
        ("mine", lambda: repo.mine(student.id, _now())),
        ("waiting", lambda: repo.waiting(teacher.id, _now(), 0, 10)),
        ("decline", lambda: repo.decline(teacher.id, student.id, _now())),
        ("reopen", lambda: repo.reopen(teacher.id, student.id, _now())),
        ("approve", lambda: repo.approve(teacher.id, student.id, CAPS, _now())),
        ("approve_all", lambda: repo.approve_all(teacher.id, _now(), CAPS, _now())),
        ("withdraw", lambda: repo.withdraw(student.id, other.id)),
        ("due", lambda: repo.due(_now(), 100)),
        ("prune", lambda: repo.prune(_now(-KEEP))),
        ("unlink", lambda: world.links.unlink(student.id, teacher.id)),
    ]

    for name, call in calls:
        with _statements(engine) as seen:
            await call()
        assert len(seen) == 1, name

    assert await _count(engine, "teacher_link") == 1  # `second`, by Confirm all
    assert await world.state(student, teacher) == WITHDRAWN  # closed by the unlink


# The question


async def test_choices_offer_the_teacher_role_and_list_who_i_wait_for(world: World) -> None:
    anna, boris = await world.staff(name="Anna"), await world.staff(name="Boris")
    linked = await world.staff(name="Linked")
    await world.staff(ASSISTANT, "Assistant")
    await world.staff(OFFICE, "Desk")
    student = await world.student()
    await world.link(student, linked)
    await world.asked(student, boris)

    found = await world.requests.choices(world.shala, student.id, _now())

    assert found is not None
    assert (found.shala_id, found.shala_name) == (world.shala, "Ashtanga Almaty")
    assert found.offer == (TeacherChoice(anna.id, "Anna"),)
    assert found.waiting == (TeacherChoice(boris.id, "Boris"),)


async def test_choices_are_none_for_everyone_but_a_student_of_the_shala(world: World) -> None:
    teacher, stranger = await world.staff(), await _person(world.engine)
    student = await world.student()

    for who in (teacher, world.owner, stranger):
        assert await world.requests.choices(world.shala, who.id, _now()) is None
    assert await world.requests.choices(uuid4(), student.id, _now()) is None


# The ask


async def test_ask_inserts_the_row_and_returns_what_the_note_needs(world: World) -> None:
    teacher, student = await world.staff(name="Лена", locale="ru"), await world.student()
    before = datetime.now(UTC) - timedelta(seconds=5)

    guarded = await world.requests.ask(
        world.shala, student.id, teacher.id, date(2026, 11, 18), False, CAPS, _now()
    )

    assert guarded.me == Membership(world.shala, False, frozenset(), True)
    assert guarded.done
    asked = guarded.value
    assert asked is not None
    assert (asked.state, asked.teacher_name, asked.teacher_locale) == (
        AskState.CREATED,
        "Лена",
        "ru",
    )
    assert (asked.shala_name, asked.waiting) == ("Ashtanga Almaty", 1)
    assert asked.teacher_telegram_id is not None
    assert asked.teacher_telegram_id.isdigit()
    row = (await _sql(world.engine, "SELECT * FROM tristhana.teacher_request")).one()
    assert (row.student_id, row.teacher_id, row.shala_id) == (student.id, teacher.id, world.shala)
    assert (row.state, row.asked_on, row.quiet_note_agreed) == (WAITING, date(2026, 11, 18), False)
    assert before < row.created_at < datetime.now(UTC) + timedelta(seconds=5)  # the DB's clock


async def test_two_asks_at_once_make_one_row_and_one_created(world: World) -> None:
    teacher, student = await world.staff(), await world.student()

    first, second = await asyncio.gather(world.ask(student, teacher), world.ask(student, teacher))

    assert {first, second} == {AskState.CREATED, AskState.WAITING}
    assert await _count(world.engine, "teacher_request") == 1


async def test_the_refusals_in_their_order(world: World) -> None:
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)
    week, month = _now(ANSWER_WITHIN), _now(KEEP)

    assert await world.ask(student, teacher) is AskState.WAITING
    assert await world.ask(student, teacher, now=week) is AskState.RECENT
    await world.requests.decline(teacher.id, student.id, _now())
    assert await world.ask(student, teacher) is AskState.WAITING  # a quiet no: the same
    assert await world.ask(student, teacher, now=week) is AskState.RECENT
    await world.requests.withdraw(student.id, teacher.id)
    assert await world.ask(student, teacher) is AskState.RECENT
    await world.link(student, teacher)
    assert await world.ask(student, teacher) is AskState.LINKED
    assert await world.ask(student, teacher, now=month) is AskState.LINKED
    assert await _count(world.engine, "teacher_request") == 1


async def test_a_row_past_thirty_days_is_recycled_without_the_prune(world: World) -> None:
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher, agreed=False)
    await world.requests.decline(teacher.id, student.id, _now())
    old = await _scalar(world.engine, "SELECT id FROM tristhana.teacher_request")
    month = _now(KEEP)

    assert await world.ask(student, teacher, now=month - timedelta(minutes=1)) is AskState.RECENT
    again = await world.ask(student, teacher, now=month, agreed=True, asked_on=date(2026, 12, 17))
    twice = await world.ask(student, teacher)  # the new row is on today's clock

    assert (again, twice) == (AskState.CREATED, AskState.WAITING)
    row = (await _sql(world.engine, "SELECT * FROM tristhana.teacher_request")).one()
    assert (row.state, row.asked_on, row.quiet_note_agreed) == (WAITING, date(2026, 12, 17), True)
    assert row.id != old  # the first request's note in the ledger can't swallow the next
    assert row.created_at > datetime.now(UTC) - timedelta(minutes=1)
    assert (await world.requests.waiting(teacher.id, _now(), 0, 10)).total == 1


@pytest.mark.parametrize(
    ("caps", "mine", "theirs", "state"),
    [
        (RequestCaps(asking=2), 2, 0, AskState.TOO_MANY),
        (RequestCaps(asking=3), 2, 0, AskState.CREATED),
        (RequestCaps(teachers=3), 1, 0, AskState.CREATED),  # 1 link + 1 waiting < 3
        (RequestCaps(teachers=2), 1, 0, AskState.TOO_MANY),  # 1 link + 1 waiting
        (RequestCaps(waiting=2), 0, 2, AskState.FULL),
        (RequestCaps(waiting=3), 0, 2, AskState.CREATED),
        (RequestCaps(students=3), 0, 2, AskState.FULL),  # 1 link + 2 waiting
        (RequestCaps(students=4), 0, 2, AskState.CREATED),
    ],
)
async def test_every_cap_matches_the_domain_rule(
    world: World, caps: RequestCaps, mine: int, theirs: int, state: AskState
) -> None:
    """Waiting requests count toward the link caps on both sides (Q319)."""
    teacher, student = await world.staff(), await world.student()
    await world.link(student, await world.staff(name="Mine"))  # my one link
    await world.link(await _person(world.engine), teacher)  # their one student
    for n in range(mine):
        await world.asked(student, await world.staff(name=f"T{n}"))
    for n in range(theirs):
        await world.asked(await world.student(f"S{n}"), teacher)

    got = await world.ask(student, teacher, caps=caps)

    assert got is state
    assert got is ask_state(
        linked=False,
        earlier=None,
        now=_now(),
        my_waiting=mine,
        my_teachers=1,
        their_waiting=theirs,
        their_students=1,
        caps=caps,
    )
    assert (await world.state(student, teacher) == WAITING) is (state is AskState.CREATED)


async def test_a_quiet_no_frees_no_slot_for_the_student_and_one_for_the_teacher(
    world: World,
) -> None:
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)
    await world.requests.decline(teacher.id, student.id, _now())
    other_teacher, other_student = await world.staff(name="Boris"), await world.student("Bea")

    mine = await world.ask(student, other_teacher, caps=RequestCaps(asking=1))
    theirs = await world.ask(other_student, teacher, caps=RequestCaps(waiting=1))

    assert (mine, theirs) == (AskState.TOO_MANY, AskState.CREATED)


async def test_the_guard_matches_the_policy_over_every_membership(world: World) -> None:
    """Who can be asked: `ask`'s pair guard, the offer and the read-time validity join, each
    against `can_ask_teacher` for all 32 staff seats (the owner's and another's) and for a
    student and a stranger as the target; then who can ask."""
    staff, student = await world.staff(ASSISTANT, "Staff"), await world.student()
    asker = Membership(world.shala, False, frozenset(), True)
    repo = world.requests
    seen = 0

    for target in every_membership():
        if target.student:
            continue
        who = world.owner if target.owner else staff
        await world.roles(who, *target.roles)
        allowed = can_ask_teacher(asker, target)

        choices = await repo.choices(world.shala, student.id, _now())
        guarded = await repo.ask(world.shala, student.id, who.id, ON, True, CAPS, _now())
        listed = (await repo.waiting(who.id, _now(), 0, 10)).total

        assert choices is not None
        assert (who.id in {c.id for c in choices.offer}) is allowed, target
        assert guarded.me == asker
        assert guarded.done is allowed, target
        assert (guarded.value is not None) is allowed
        assert listed == (1 if allowed else 0), target
        if allowed:  # the validity join reads the role again: take it away and give it back
            await world.roles(who, *(target.roles - {TEACHER}))
            assert (await repo.waiting(who.id, _now(), 0, 10)).total == 0
            assert (await repo.approve(who.id, student.id, CAPS, _now())).outcome is Answered.GONE
            await world.roles(who, *target.roles)
            assert (await repo.waiting(who.id, _now(), 0, 10)).total == 1
        await _sql(world.engine, "DELETE FROM tristhana.teacher_request")
        seen += 1

    assert seen == 32
    other, stranger = await world.student("Other"), await _person(world.engine)
    teacher = await world.staff()
    for target in (other, stranger):  # a student or a non-member can't be asked
        refused = await repo.ask(world.shala, student.id, target.id, ON, True, CAPS, _now())
        assert (refused.me, refused.done) == (asker, False)
    for actor in (staff, world.owner, teacher):  # staff don't ask
        refused = await repo.ask(world.shala, actor.id, teacher.id, ON, True, CAPS, _now())
        assert refused.me is not None
        assert not refused.done
    nobody = await repo.ask(world.shala, stranger.id, teacher.id, ON, True, CAPS, _now())
    nowhere = await repo.ask(uuid4(), student.id, teacher.id, ON, True, CAPS, _now())
    assert (nobody.me, nobody.done, nowhere.me, nowhere.done) == (None, False, None, False)
    assert await _count(world.engine, "teacher_request") == 0


async def test_a_request_through_one_shala_blocks_the_pair_in_another(world: World) -> None:
    teacher, student = await world.staff(), await world.student()
    second = await world.new_shala(await _person(world.engine, "Other owner"), "Second Shala")
    code = _code("S")
    owner_id = await _scalar(
        world.engine, "SELECT owner_id FROM tristhana.shala WHERE id = :s", s=second
    )
    await world.shalas.invite_staff(second, owner_id, TEACHER, code, IN_A_WEEK, SHALA_CAPS)
    await world.shalas.accept_staff(code, teacher.id, SHALA_CAPS, ON)
    await world.join(student, second)
    await world.asked(student, teacher)

    assert await world.ask(student, teacher, shala=second) is AskState.WAITING
    there = await world.requests.choices(second, student.id, _now())
    assert there is not None
    assert (there.offer, there.waiting) == ((), ())  # asked through the first shala
    assert await _count(world.engine, "teacher_request") == 1


# The lists


async def test_mine_and_the_waiting_list(world: World) -> None:
    anna, boris = await world.staff(name="Anna"), await world.staff(name="Boris")
    students = [await world.student(f"S{n}") for n in range(4)]
    for student in students:
        await world.asked(student, anna)
    await world.asked(students[0], boris)
    await world.requests.decline(anna.id, students[3].id, _now())
    before = datetime.now(UTC) - timedelta(seconds=5)

    mine = await world.requests.mine(students[0].id, _now())
    declined = await world.requests.mine(students[3].id, _now())
    first = await world.requests.waiting(anna.id, _now(), 0, 2)
    rest = await world.requests.waiting(anna.id, _now(), 2, 2)
    one = await world.requests.waiting(anna.id, _now(), 0, 10, students[1].id)
    hidden = await world.requests.waiting(anna.id, _now(), 0, 10, students[3].id)

    assert mine.asked == (
        AskedTeacher(anna.id, "Anna", world.shala, "Ashtanga Almaty"),
        AskedTeacher(boris.id, "Boris", world.shala, "Ashtanga Almaty"),
    )
    assert mine.waiting == 0
    assert declined.asked == (AskedTeacher(anna.id, "Anna", world.shala, "Ashtanga Almaty"),)
    assert (await world.requests.mine(anna.id, _now())).waiting == 3
    assert [r.name for r in first.requests] == ["S0", "S1"]
    assert [r.name for r in rest.requests] == ["S2"]
    assert first.total == rest.total == one.total == hidden.total == 3
    assert [(r.student_id, r.shala_id, r.shala_name) for r in one.requests] == [
        (students[1].id, world.shala, "Ashtanga Almaty")
    ]
    assert hidden.requests == ()  # declined: off the list
    assert before < first.as_of < datetime.now(UTC) + timedelta(seconds=5)


async def test_after_seven_days_nothing_waits_and_nothing_was_written(world: World) -> None:
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)
    edge = _now(ANSWER_WITHIN)

    assert (await world.requests.waiting(teacher.id, edge - timedelta(minutes=1), 0, 10)).total == 1
    assert (await world.requests.waiting(teacher.id, edge, 0, 10)).total == 0
    assert (await world.requests.mine(student.id, edge)).asked == ()
    assert await world.requests.approve(teacher.id, student.id, CAPS, edge) == Answer(Answered.GONE)
    assert await world.requests.decline(teacher.id, student.id, edge) == Answer(Answered.GONE)
    assert await world.state(student, teacher) == WAITING  # expiry is a read-time rule
    assert await _count(world.engine, "teacher_link") == 0


# The approval


@pytest.mark.parametrize("agreed", [True, False])
async def test_approve_flips_the_state_and_inserts_the_link(world: World, agreed: bool) -> None:
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher, agreed=agreed, asked_on=date(2026, 11, 14))
    asked_at = await _scalar(world.engine, "SELECT created_at FROM tristhana.teacher_request")

    answer = await world.requests.approve(teacher.id, student.id, CAPS, _now(timedelta(days=3)))

    assert answer == Answer(Answered.DONE, "Ash", 0)
    assert await world.state(student, teacher) == APPROVED
    link = await world.link_row(student, teacher)
    assert link.linked_on == date(2026, 11, 14)  # the day the student asked
    assert link.quiet_note_agreed is agreed  # copied, never set
    assert link.is_primary is False
    assert link.created_at > asked_at  # the approval's instant


async def test_two_yes_taps_at_once_make_one_link_and_one_approved(world: World) -> None:
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)

    first, second = await asyncio.gather(
        world.requests.approve(teacher.id, student.id, CAPS, _now()),
        world.requests.approve(teacher.id, student.id, CAPS, _now()),
    )

    assert sorted([first.outcome, second.outcome]) == [Answered.ALREADY, Answered.DONE]
    assert await _count(world.engine, "teacher_link") == 1
    assert await world.state(student, teacher) == APPROVED


async def test_a_yes_held_behind_another_yes_says_already(world: World) -> None:
    """Forced: the second tap waits on the row and then decides against the first's result."""
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)

    async with _holding(world.engine) as other:
        await other.execute(
            text("UPDATE tristhana.teacher_request SET state = 'approved' WHERE teacher_id = :t"),
            {"t": teacher.id},
        )
        await other.execute(
            text(
                "INSERT INTO tristhana.teacher_link (student_id, teacher_id, linked_on,"
                " quiet_note_agreed) VALUES (:s, :t, :on, true)"
            ),
            {"s": student.id, "t": teacher.id, "on": ON},
        )
        tap = await _blocked(
            world.engine, world.requests.approve(teacher.id, student.id, CAPS, _now())
        )
        await other.execute(text("COMMIT"))

        assert (await tap).outcome is Answered.ALREADY

    assert await _count(world.engine, "teacher_link") == 1


async def test_a_yes_that_loses_to_a_withdrawal_makes_no_link(world: World) -> None:
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)

    async with _holding(world.engine) as other:
        await other.execute(
            text("UPDATE tristhana.teacher_request SET state = 'withdrawn' WHERE teacher_id = :t"),
            {"t": teacher.id},
        )
        tap = await _blocked(
            world.engine, world.requests.approve(teacher.id, student.id, CAPS, _now())
        )
        await other.execute(text("COMMIT"))

        assert (await tap).outcome is Answered.GONE

    assert await world.state(student, teacher) == WITHDRAWN
    assert await _count(world.engine, "teacher_link") == 0


async def test_a_withdrawal_that_loses_to_a_yes_leaves_the_link(world: World) -> None:
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)

    async with _holding(world.engine) as other:
        await other.execute(
            text("UPDATE tristhana.teacher_request SET state = 'approved' WHERE teacher_id = :t"),
            {"t": teacher.id},
        )
        await other.execute(
            text(
                "INSERT INTO tristhana.teacher_link (student_id, teacher_id, linked_on,"
                " quiet_note_agreed) VALUES (:s, :t, :on, true)"
            ),
            {"s": student.id, "t": teacher.id, "on": ON},
        )
        tap = await _blocked(world.engine, world.requests.withdraw(student.id, teacher.id))
        await other.execute(text("COMMIT"))

        withdrawn = await tap

    assert withdrawn.removed is False  # `linked` is from the tap's own snapshot
    assert await world.state(student, teacher) == APPROVED
    assert await _count(world.engine, "teacher_link") == 1


async def test_approve_and_withdraw_at_once_end_in_one_consistent_state(world: World) -> None:
    teacher = await world.staff()
    students = [await world.student(f"S{n}") for n in range(6)]
    for student in students:
        await world.asked(student, teacher)

    await asyncio.gather(
        *(world.requests.approve(teacher.id, s.id, CAPS, _now()) for s in students),
        *(world.requests.withdraw(s.id, teacher.id) for s in students),
    )

    for student in students:
        state, link = await world.state(student, teacher), await world.link_row(student, teacher)
        assert (state, link is not None) in {(APPROVED, True), (WITHDRAWN, False)}


async def test_a_yes_and_the_personal_link_at_once_make_one_link(world: World) -> None:
    """The student confirms the teacher's own link (ID-04) as the teacher taps Yes."""
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)
    code = await world.links.invite(teacher.id, _code("T"))

    async with _holding(world.engine) as other:
        await other.execute(
            text(
                "INSERT INTO tristhana.teacher_link (student_id, teacher_id, linked_on,"
                " quiet_note_agreed) VALUES (:s, :t, :on, true)"
            ),
            {"s": student.id, "t": teacher.id, "on": date(2026, 11, 20)},
        )
        tap = await _blocked(
            world.engine, world.requests.approve(teacher.id, student.id, CAPS, _now())
        )
        await other.execute(text("COMMIT"))

        assert (await tap).outcome is Answered.ALREADY

    assert await _count(world.engine, "teacher_link") == 1
    assert (await world.link_row(student, teacher)).linked_on == date(2026, 11, 20)
    assert await world.state(student, teacher) == APPROVED  # the teacher did say yes
    again = await world.links.accept(code, student.id, LINK_CAPS, ON)
    assert again is not None
    assert (again.created, again.already) == (False, True)


async def test_a_link_wins_in_every_read_and_a_no_never_removes_it(world: World) -> None:
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)
    await world.link(student, teacher)  # by the teacher's own link, meanwhile
    repo = world.requests

    assert (await repo.waiting(teacher.id, _now(), 0, 10)).total == 0
    assert (await repo.mine(student.id, _now())).asked == ()
    assert await repo.approve(teacher.id, student.id, CAPS, _now()) == Answer(
        Answered.ALREADY, "Ash", 0
    )
    assert (await repo.decline(teacher.id, student.id, _now())).outcome is Answered.ALREADY
    assert (await repo.reopen(teacher.id, student.id, _now())).outcome is Answered.ALREADY
    assert await repo.withdraw(student.id, teacher.id) == Withdrawn(removed=True, linked=True)

    assert (await world.link_row(student, teacher)).linked_on == date(2026, 11, 20)
    assert await repo.due(_now(ANSWER_WITHIN), 100) == []  # linked by that tap: no note


async def test_a_cap_keeps_the_request_waiting(world: World) -> None:
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)
    await world.link(await _person(world.engine), teacher)
    await world.link(student, await world.staff(name="Other"))
    repo = world.requests

    theirs = await repo.approve(teacher.id, student.id, RequestCaps(students=1), _now())
    mine = await repo.approve(teacher.id, student.id, RequestCaps(teachers=1), _now())

    assert theirs == mine == Answer(Answered.FULL, "Ash", 1)
    assert await world.state(student, teacher) == WAITING
    assert (await repo.approve(teacher.id, student.id, CAPS, _now())).outcome is Answered.DONE


async def test_a_forged_id_touches_nothing(world: World) -> None:
    teacher, colleague = await world.staff(), await world.staff(name="Colleague")
    student, bystander = await world.student(), await world.student("Bea")
    await world.asked(student, teacher)
    repo = world.requests

    for me, target in ((colleague, student), (world.owner, student), (teacher, bystander)):
        assert await repo.approve(me.id, target.id, CAPS, _now()) == Answer(Answered.GONE)
        assert await repo.decline(me.id, target.id, _now()) == Answer(Answered.GONE)
        assert await repo.reopen(me.id, target.id, _now()) == Answer(Answered.GONE)
        assert (await repo.waiting(me.id, _now(), 0, 10, target.id)).requests == ()
    assert await repo.approve(teacher.id, uuid4(), CAPS, _now()) == Answer(Answered.GONE)
    assert await repo.withdraw(bystander.id, teacher.id) == Withdrawn(False, False)

    assert await world.state(student, teacher) == WAITING
    assert await _count(world.engine, "teacher_link") == 0


# Decline, Undo, Confirm all


async def test_decline_and_undo(world: World) -> None:
    teacher, student, other = await world.staff(), await world.student(), await world.student("Bea")
    await world.asked(student, teacher)
    await world.asked(other, teacher)
    repo = world.requests

    assert await repo.decline(teacher.id, student.id, _now()) == Answer(Answered.DONE, "Ash", 1)
    assert await repo.decline(teacher.id, student.id, _now()) == Answer(Answered.DONE, "Ash", 1)
    assert await world.state(student, teacher) == DECLINED
    assert await repo.reopen(teacher.id, student.id, _now()) == Answer(Answered.DONE, "Ash", 2)
    assert await repo.reopen(teacher.id, student.id, _now()) == Answer(Answered.DONE, "Ash", 2)
    assert await world.state(student, teacher) == WAITING

    await repo.decline(teacher.id, student.id, _now())
    late = _now(ANSWER_WITHIN)
    assert await repo.reopen(teacher.id, student.id, late) == Answer(Answered.GONE)
    assert (await repo.approve(teacher.id, student.id, CAPS, _now())).outcome is Answered.DONE


async def test_confirm_all_takes_the_oldest_that_fit_and_were_on_the_list(world: World) -> None:
    teacher = await world.staff()
    first, second, declined, third = [await world.student(n) for n in ("A", "B", "No", "C")]
    for student in (first, second, declined, third):
        await world.asked(student, teacher, agreed=student is first)
    await world.requests.decline(teacher.id, declined.id, _now())
    as_of = (await world.requests.waiting(teacher.id, _now(), 0, 10)).as_of
    late = await world.student("Late")
    await world.asked(late, teacher)  # after the list was drawn

    done = await world.requests.approve_all(teacher.id, as_of, RequestCaps(students=2), _now())

    assert done == ApprovedAll(approved=2, left=2)
    assert [await world.state(s, teacher) for s in (first, second, declined, third, late)] == [
        APPROVED,
        APPROVED,
        DECLINED,
        WAITING,
        WAITING,
    ]
    assert (await world.link_row(first, teacher)).quiet_note_agreed is True
    assert (await world.link_row(second, teacher)).quiet_note_agreed is False
    assert (await world.link_row(first, teacher)).linked_on == ON
    assert await _count(world.engine, "teacher_link") == 2

    rest = await world.requests.approve_all(teacher.id, _now(), CAPS, _now())
    assert rest == ApprovedAll(approved=2, left=0)  # never the declined one
    assert await world.state(declined, teacher) == DECLINED


async def test_confirm_all_skips_a_student_at_their_own_cap(world: World) -> None:
    teacher, full, free = await world.staff(), await world.student("Full"), await world.student()
    await world.asked(full, teacher)
    await world.asked(free, teacher)
    await world.link(full, await world.staff(name="Other"))

    done = await world.requests.approve_all(teacher.id, _now(), RequestCaps(teachers=1), _now())

    assert done == ApprovedAll(approved=1, left=1)
    assert await world.state(full, teacher) == WAITING


# Validity is a join


async def test_a_student_who_left_is_gone_and_a_rejoin_revives_nothing(world: World) -> None:
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)
    repo = world.requests

    await world.shalas.remove_student(world.shala, student.id, student.id)
    assert (await repo.waiting(teacher.id, _now(), 0, 10)).total == 0
    assert (await repo.mine(student.id, _now())).asked == ()

    await world.join(student)  # by the wall QR again
    assert (await repo.waiting(teacher.id, _now(), 0, 10)).total == 0
    assert (await repo.mine(student.id, _now())).asked == ()
    assert await repo.approve(teacher.id, student.id, CAPS, _now()) == Answer(Answered.GONE)
    assert await world.ask(student, teacher) is AskState.RECENT  # no way around the 30 days
    choices = await repo.choices(world.shala, student.id, _now())
    assert choices is not None
    assert (choices.offer, choices.waiting) == ((), ())
    assert await repo.due(_now(ANSWER_WITHIN), 100) == []  # and no note
    assert await world.state(student, teacher) == WAITING  # nothing was written


async def test_a_student_turned_staff_is_gone(world: World) -> None:
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)

    await world.make_staff(student, ASSISTANT)

    assert (await world.requests.waiting(teacher.id, _now(), 0, 10)).total == 0
    assert await world.requests.approve(teacher.id, student.id, CAPS, _now()) == Answer(
        Answered.GONE
    )


async def test_a_teacher_who_left_and_came_back_has_an_empty_list(world: World) -> None:
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)
    repo = world.requests

    await world.shalas.remove_staff(world.shala, teacher.id, teacher.id)
    assert [a.teacher_id for a in (await repo.mine(student.id, _now())).asked] == [teacher.id]
    await world.make_staff(teacher)  # a newer staff row than the request

    assert (await repo.waiting(teacher.id, _now(), 0, 10)).total == 0
    assert await repo.approve(teacher.id, student.id, CAPS, _now()) == Answer(Answered.GONE)
    # The student still "waits", and gets the gentle note with everyone else.
    assert [a.teacher_id for a in (await repo.mine(student.id, _now())).asked] == [teacher.id]
    assert [d.closing for d in await repo.due(_now(ANSWER_WITHIN), 100)] == [Closing.NO_ANSWER]


# A removed link closes the request


async def test_unlink_closes_the_pairs_request_whatever_its_state(world: World) -> None:
    teacher = await world.staff()
    approved, personal = await world.student("Approved"), await world.student("Personal")
    never = await world.student("Never")
    for student in (approved, personal, never):
        await world.asked(student, teacher)
    await world.requests.approve(teacher.id, approved.id, CAPS, _now())
    await world.link(personal, teacher)

    for student in (approved, personal):
        assert (await world.links.unlink(student.id, teacher.id)).removed
    assert not (await world.links.unlink(never.id, teacher.id)).removed  # no link, no close

    assert [await world.state(s, teacher) for s in (approved, personal, never)] == [
        WITHDRAWN,
        WITHDRAWN,
        WAITING,
    ]
    for student in (approved, personal):  # an old "Yes" can't bring the link back
        answer = await world.requests.approve(teacher.id, student.id, CAPS, _now())
        assert answer == Answer(Answered.GONE, None, 1)  # `never` still waits
    assert await _count(world.engine, "teacher_link") == 0
    assert await world.ask(approved, teacher) is AskState.RECENT


# Cascades and deletes mid-tap


@pytest.mark.parametrize("gone", ["student", "teacher", "shala", "owner"])
async def test_one_delete_statement_takes_the_requests(world: World, gone: str) -> None:
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)
    accounts = SqlAccountRepository(world.engine)

    with _statements(world.engine) as seen:
        if gone == "shala":
            assert (await world.shalas.delete(world.shala, world.owner.id)).done
        else:
            who = {"student": student, "teacher": teacher, "owner": world.owner}[gone]
            assert await accounts.delete(who.id)

    assert len(seen) == 1
    assert await _count(world.engine, "teacher_request") == 0
    assert await world.requests.approve(teacher.id, student.id, CAPS, _now()) == Answer(
        Answered.GONE
    )
    assert (await world.requests.mine(student.id, _now())).asked == ()


async def test_a_student_deleted_mid_yes_is_gone_not_the_teachers_account(world: World) -> None:
    """The request cascades with the student, so the tap that waited on it finds no row. The
    23503 on the link's student key is the second line (`test_migration_0029.py`)."""
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)

    async with _holding(world.engine) as other:
        await other.execute(text("DELETE FROM tristhana.account WHERE id = :a"), {"a": student.id})
        tap = await _blocked(
            world.engine, world.requests.approve(teacher.id, student.id, CAPS, _now())
        )
        await other.execute(text("COMMIT"))

        assert await tap == Answer(Answered.GONE)

    assert await _count(world.engine, "teacher_link") == 0
    assert await _count(world.engine, "teacher_request") == 0


async def test_a_student_deleted_mid_ask_is_account_gone(world: World) -> None:
    teacher, student = await world.staff(), await world.student()

    async with _holding(world.engine) as other:
        await other.execute(text("DELETE FROM tristhana.account WHERE id = :a"), {"a": student.id})
        tap = await _blocked(
            world.engine,
            world.requests.ask(world.shala, student.id, teacher.id, ON, True, CAPS, _now()),
        )
        await other.execute(text("COMMIT"))

        with pytest.raises(AccountGone):
            await tap

    assert await _count(world.engine, "teacher_request") == 0


async def test_a_teacher_deleted_mid_ask_is_a_refusal(world: World) -> None:
    teacher, student = await world.staff(), await world.student()

    async with _holding(world.engine) as other:
        await other.execute(text("DELETE FROM tristhana.account WHERE id = :a"), {"a": teacher.id})
        tap = await _blocked(
            world.engine,
            world.requests.ask(world.shala, student.id, teacher.id, ON, True, CAPS, _now()),
        )
        await other.execute(text("COMMIT"))

        guarded = await tap

    assert (guarded.me is not None, guarded.done, guarded.value) == (True, False, None)
    assert await _count(world.engine, "teacher_request") == 0


# A request is not a link


@pytest.mark.parametrize("state", [WAITING, DECLINED])
async def test_with_a_request_the_teachers_reads_return_nothing(world: World, state: str) -> None:
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)
    await _sql(world.engine, "UPDATE tristhana.teacher_request SET state = :x", x=state)
    engine, today = world.engine, date.today()
    view = SqlTeacherViewRepository(engine)
    since, until = today - timedelta(days=30), today + timedelta(days=1)

    page = await view.page(teacher.id, 0, 20, since, until)
    links = await world.links.overview(teacher.id)

    assert (page.students, page.total) == ((), 0)
    assert await view.student(teacher.id, student.id, since, until) is None
    assert links.students == ()
    assert (await world.links.overview(student.id)).teachers == ()
    assert await SqlProgressionRepository(engine).for_teacher(teacher.id, student.id) is None
    assert await _count(engine, "teacher_link") == 0
    for who in (teacher, student):  # the account load: no `teaches`, no main teacher, no moon
        loaded = await _loaded(engine, who)
        assert (loaded.teaches, loaded.main_teacher) == (False, None)


async def _loaded(engine: AsyncEngine, who: Account) -> Account:
    telegram_id = await _scalar(
        engine, "SELECT provider_user_id FROM tristhana.identity WHERE account_id = :a", a=who.id
    )
    found = await SqlAccountRepository(engine).find_by_identity(
        IdentityKey(IdentityProvider.TELEGRAM, telegram_id)
    )
    assert found is not None
    return found


# The closing notes' read


async def test_confirmed_is_due_at_once_with_what_the_note_needs(world: World) -> None:
    teacher, student = await world.staff(name="Лена"), await world.student()
    await world.link(student, await world.staff(name="First"))
    await world.asked(student, teacher)
    assert await world.requests.due(_now(), 100) == []

    await world.requests.approve(teacher.id, student.id, CAPS, _now())
    [due] = await world.requests.due(_now(), 100)

    id = await _scalar(world.engine, "SELECT id FROM tristhana.teacher_request")
    assert (due.id, due.closing, due.student_id) == (id, Closing.CONFIRMED, student.id)
    assert (due.locale, due.zone, due.telegram_id.isdigit()) == ("en", "Asia/Almaty", True)
    assert (due.teacher_id, due.teacher_name, due.shala_id) == (teacher.id, "Лена", world.shala)
    assert due.my_teachers == 2  # not their first teacher: "Make main" is offered


async def test_a_quiet_no_and_silence_fall_due_in_the_same_run_and_never_twice(
    world: World,
) -> None:
    teacher = await world.staff()
    silent, declined, withdrawn = [await world.student(n) for n in ("Silent", "No", "Back")]
    for student in (silent, declined, withdrawn):
        await world.asked(student, teacher)
    await world.requests.decline(teacher.id, declined.id, _now())  # on day 0
    await world.requests.withdraw(withdrawn.id, teacher.id)
    repo, ledger = world.requests, SqlNotificationRepository(world.engine)
    edge = _now(ANSWER_WITHIN)

    assert await repo.due(edge - timedelta(minutes=1), 100) == []
    due = await repo.due(edge, 100)

    assert [(d.student_id, d.closing) for d in due] == [
        (silent.id, Closing.NO_ANSWER),
        (declined.id, Closing.NO_ANSWER),
    ]
    assert len(await repo.due(edge, 1)) == 1  # the limit
    first, second = due
    assert await ledger.claim(first.student_id, request_key(first.id), "request", ON)
    assert [d.id for d in await repo.due(edge, 100)] == [second.id]  # in flight: not read again
    await ledger.finish(first.student_id, request_key(first.id), "sent")
    assert await ledger.claim(second.student_id, request_key(second.id), "request", ON)
    await ledger.finish(second.student_id, request_key(second.id), "blocked")
    assert await repo.due(edge, 100) == []  # neither a second time
    assert await repo.due(_now(KEEP), 100) == []


async def test_a_failed_note_comes_back_and_an_unreachable_student_gets_none(
    world: World,
) -> None:
    teacher, student, blocked = await world.staff(), await world.student(), await world.student("B")
    await world.asked(student, teacher)
    await world.asked(blocked, teacher)
    ledger, edge = SqlNotificationRepository(world.engine), _now(ANSWER_WITHIN)
    await ledger.mark_unreachable(blocked.id, datetime.now(UTC) + timedelta(days=1))

    [due] = await world.requests.due(edge, 100)
    assert due.student_id == student.id
    assert await ledger.claim(student.id, request_key(due.id), "request", ON)
    await ledger.finish(student.id, request_key(due.id), "failed")

    assert [d.id for d in await world.requests.due(edge, 100)] == [due.id]  # a later tick retries


async def test_prune_takes_rows_past_thirty_days(world: World) -> None:
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)

    assert await world.requests.prune(_now(-KEEP)) == 0
    assert await world.requests.prune(_now()) == 1

    assert await _count(world.engine, "teacher_request") == 0
    assert await world.ask(student, teacher) is AskState.CREATED


async def test_the_tick_sends_each_closing_note_once_and_prunes(world: World) -> None:
    """The tick's step on the real `due`, the real ledger (category `request`) and the real
    prune: a yes at once, a quiet "no" and silence together at day 7, each note once."""
    from tests.fakes import FakeCalculator, InMemoryMoon
    from tristhana.application.ports.notifications import RequestClosed
    from tristhana.application.tick import RunTick

    teacher = await world.staff(name="Лена")
    yes, silent, declined = [await world.student(n) for n in ("Yes", "Silent", "No")]
    for student in (yes, silent, declined):
        await world.asked(student, teacher)
    await world.requests.approve(teacher.id, yes.id, CAPS, _now())
    await world.requests.decline(teacher.id, declined.id, _now())
    clock, notifier = FixedClock(_now()), FakeNotifier()
    tick = RunTick(
        clock,
        cities(),
        InMemoryMoon(),
        FakeCalculator(),
        SqlNotificationRepository(world.engine),
        notifier,
        requests=world.requests,
    )

    rows = await _sql(world.engine, "SELECT provider_user_id, account_id FROM tristhana.identity")
    names = {a.id: a.display_name for a in (yes, silent, declined, teacher)}
    name_of = {telegram_id: names.get(account) for telegram_id, account in rows}

    def closed() -> list[tuple[str | None, Closing]]:
        return [
            (name_of[r.telegram_id], n.closing)
            for r, n in notifier.delivered
            if isinstance(n, RequestClosed)
        ]

    await tick.execute(timedelta(seconds=30))
    await tick.execute(timedelta(seconds=30))
    assert closed() == [("Yes", Closing.CONFIRMED)]

    clock.instant = _now(ANSWER_WITHIN)
    await tick.execute(timedelta(seconds=30))
    await tick.execute(timedelta(seconds=30))

    assert closed() == [
        ("Yes", Closing.CONFIRMED),
        ("Silent", Closing.NO_ANSWER),
        ("No", Closing.NO_ANSWER),
    ]
    ledger = await _sql(
        world.engine,
        "SELECT category, status, count(*) FROM tristhana.notification_delivery"
        " WHERE dedupe_key LIKE 'req:%' GROUP BY 1, 2",
    )
    assert ledger.all() == [("request", "sent", 3)]
    assert await _count(world.engine, "teacher_request") == 3

    clock.instant = _now(KEEP)
    result = await tick.execute(timedelta(seconds=30))

    assert await _count(world.engine, "teacher_request") == 0
    assert result.pruned >= 3


# Export (ST-09): both directions, projected, and no trace of the other person


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
        FixedClock(datetime.now(UTC)),
    )
    await use_case.execute(Principal(who))
    [(data, tables, readme)] = packer.packed
    return data, json.dumps({"data": data, "tables": tables, "readme": readme}, ensure_ascii=False)


async def test_the_export_projects_the_state_for_each_side(world: World) -> None:
    student = await world.student("Ash Student")
    teachers = {
        state: await world.staff(name=f"Teacher {state}")
        for state in (WAITING, DECLINED, WITHDRAWN, APPROVED)
    }
    for teacher in teachers.values():
        await world.asked(student, teacher, caps=RequestCaps(asking=9), asked_on=date(2026, 11, 16))
    await world.requests.decline(teachers[DECLINED].id, student.id, _now())
    await world.requests.withdraw(student.id, teachers[WITHDRAWN].id)
    await world.requests.approve(teachers[APPROVED].id, student.id, CAPS, _now())

    mine, everything = await _export(world.engine, student)

    assert mine["teacher_requests"] == [
        {"other_side": "teacher", "asked_on": "2026-11-16", "state": state}
        for state in ("waiting", "waiting", "withdrawn", "confirmed")  # never "declined"
    ]
    assert "declined" not in json.dumps(mine["teacher_requests"])
    for other in (*teachers.values(), world.owner):
        assert str(other.id) not in everything
        assert str(other.display_name) not in everything
    assert str(world.shala) not in everything
    for state, word in ((WAITING, "waiting"), (DECLINED, "declined"), (APPROVED, "confirmed")):
        theirs, held = await _export(world.engine, teachers[state])
        assert theirs["teacher_requests"] == [
            {"other_side": "student", "asked_on": "2026-11-16", "state": word}
        ]
        assert str(student.id) not in held
        assert "Ash Student" not in held
    closed, _ = await _export(world.engine, teachers[WITHDRAWN])
    assert [r["state"] for r in closed["teacher_requests"]] == ["closed"]


async def test_the_students_export_is_the_same_for_a_quiet_no_and_for_silence(
    world: World,
) -> None:
    """The leak test of ADR-0046: swap `declined` for `waiting`, expect equal output."""
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)

    async def exported() -> list[Any]:
        await _sql(world.engine, "UPDATE tristhana.account SET export_claimed_at = NULL")
        return [(await _export(world.engine, student))[0]["teacher_requests"]]

    waiting = await exported()
    await world.requests.decline(teacher.id, student.id, _now())
    assert await exported() == waiting

    # Past the seven days both read "no_answer" (the row is aged with its memberships).
    for table in ("teacher_request", "shala_student", "shala_staff"):
        await _sql(
            world.engine,
            f"UPDATE tristhana.{table} SET created_at = created_at - interval '8 days'",  # noqa: S608
        )
    declined_later = await exported()
    await _sql(world.engine, "UPDATE tristhana.teacher_request SET state = 'waiting'")
    assert await exported() == declined_later
    assert declined_later[0][0]["state"] == "no_answer"


# The app role and the migration


async def test_the_table_is_usable_by_the_app_role(engine: AsyncEngine) -> None:
    """The table takes its grants from the schema defaults (0001)."""
    missing = await _sql(
        engine,
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
        " WHERE n.nspname = 'tristhana' AND c.relname = 'teacher_request' AND c.relkind = 'r'"
        " AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tristhana_app')"
        " AND NOT has_table_privilege('tristhana_app', c.oid, 'SELECT, INSERT, UPDATE, DELETE')",
    )
    assert missing.scalars().all() == []


async def test_0029_up_down_up_and_no_drift(migrated_url: str, world: World) -> None:
    engine = world.engine
    teacher, student = await world.staff(), await world.student()
    await world.asked(student, teacher)
    await SqlNotificationRepository(engine).claim(student.id, "req:x", "request", ON)
    table = (
        "SELECT count(*) FROM information_schema.tables"
        " WHERE table_schema = 'tristhana' AND table_name = 'teacher_request'"
    )
    request_rows = "SELECT count(*) FROM tristhana.notification_delivery WHERE category = 'request'"
    insert = (
        "INSERT INTO tristhana.notification_delivery"
        " (account_id, dedupe_key, category, local_date, status)"
        " VALUES (:a, 'req:y', 'request', :on, 'claimed')"
    )

    await asyncio.to_thread(migrate.downgrade, migrated_url, "0028")
    try:
        assert await _scalar(engine, table) == 0
        assert await _scalar(engine, request_rows) == 0  # deleted before the CHECK narrows
        with pytest.raises(IntegrityError, match="notification_delivery_category_check"):
            await _sql(engine, insert, a=student.id, on=ON)
    finally:
        await asyncio.to_thread(migrate.upgrade, migrated_url)
    assert await _scalar(engine, table) == 1
    await _sql(engine, insert, a=student.id, on=ON)
    assert await _count(engine, "teacher_request") == 0  # no backfill
    await asyncio.to_thread(migrate.check, migrated_url)
