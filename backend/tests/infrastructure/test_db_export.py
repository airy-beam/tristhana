"""Export and delete on real Postgres (ST-09, ADR-0027): the snapshot opens seals for the owner
(🌸 day, sick period, diary text) and keeps unreadable ones (rest, never 🌸; null kind/text),
never shows another account's rows, reads in one transaction; the 10-minute claim (two at
once → exactly one wins; release frees it); delete removes the account's rows in every table,
leaves a second account intact and NULLs others' `marked_by`; a tick claim after a delete is
False; the coverage guard over the metadata; migration 0016."""

import asyncio
import base64
import hashlib
import itertools
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.ports.classes import ClassCaps, ClassDraft
from tristhana.application.ports.shalas import NewShala
from tristhana.application.ports.teacher_links import Caps
from tristhana.application.practice_patch import PracticePatch
from tristhana.application.shalas import CAPS
from tristhana.domain.accounts import IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.classes import ClassType, Override, OverrideStatus, Swap
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.export import MarkedBy
from tristhana.domain.notifications import DEFAULTS
from tristhana.domain.practice import PracticeContext, PracticeLength
from tristhana.domain.progression import Change, EventKind, Position, Progression
from tristhana.domain.rest_periods import RestPeriod
from tristhana.domain.shalas import ShalaRole
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db import migrate, tables
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.classes import SqlScheduleRepository
from tristhana.infrastructure.db.days import SqlDayLogRepository
from tristhana.infrastructure.db.diary import SqlDiaryRepository
from tristhana.infrastructure.db.export import (
    EXCLUDED_TABLES,
    EXPORTED_TABLES,
    SqlExportRepository,
)
from tristhana.infrastructure.db.notifications import SqlNotificationRepository
from tristhana.infrastructure.db.practice import SqlPracticeRepository
from tristhana.infrastructure.db.progression import SqlProgressionRepository
from tristhana.infrastructure.db.rest_periods import SqlRestPeriodRepository
from tristhana.infrastructure.db.shalas import SqlShalaRepository
from tristhana.infrastructure.db.teacher_links import SqlTeacherLinkRepository
from tristhana.infrastructure.invite_codes import SecretCodes

pytestmark = pytest.mark.db

KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()
OTHER_KEYS = "2:" + base64.b64encode(b"\x08" * 32).decode()
ZONE = "Asia/Almaty"
MON, TUE, WED, THU = date(2026, 10, 19), date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)
NOW = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
NAVASANA, KURMASANA = Position("primary", "navasana"), Position("primary", "kurmasana")
_users = itertools.count(30_000)


def _repo(engine: AsyncEngine, keys: str = KEYS) -> SqlExportRepository:
    return SqlExportRepository(engine, FieldCipher(keys))


async def _account(engine: AsyncEngine) -> tuple[UUID, str]:
    tg = str(next(_users))
    account = await SqlAccountRepository(engine).create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, tg), NewAccount(display_name="A", locale="en")
    )
    return account.id, tg


async def _fill(engine: AsyncEngine, me: UUID, keys: str = KEYS) -> None:
    """One of everything: 🌸 day, practice + check-in (its first practice: a milestone at a
    threshold of 1), a sick pause, a note, progression, notification settings and a
    delivery."""
    cipher = FieldCipher(keys)
    days = SqlDayLogRepository(engine, cipher)
    await days.upsert(me, DayLog(MON, DayStatus.LADIES), ZONE)
    assert (await days.upsert(me, DayLog(TUE, DayStatus.PRACTICED), ZONE, (1,))).reached == 1
    await days.upsert(me, DayLog(WED, DayStatus.SKIPPED), None)
    await SqlPracticeRepository(engine).save(
        me,
        TUE,
        PracticePatch.of(
            context=PracticeContext.MYSORE,
            length=PracticeLength(("primary",), "navasana"),
            start_time=time(6, 30),
            timezone=ZONE,
        ),
    )
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO tristhana.check_in (account_id, local_date, mood, tags)"
                " VALUES (:a, :d, 4, '{calm}')"
            ),
            {"a": me, "d": TUE},
        )
    await SqlRestPeriodRepository(engine, cipher).place(
        me, RestPeriod(date(2026, 10, 1), date(2026, 10, 3), DayStatus.SICK)
    )
    await SqlDiaryRepository(engine, cipher).save(me, THU, "Лёгкая практика\nи вторая строка")
    repo = SqlProgressionRepository(engine)
    first = await repo.apply(
        me,
        Change(EventKind.START, MON, Progression(NAVASANA), after=NAVASANA),
        None,
        me,
        before=None,
    )
    assert first is not None
    await repo.apply(
        me,
        Change(EventKind.GIVEN, TUE, Progression(KURMASANA), NAVASANA, KURMASANA),
        first.id,
        me,
        before=NAVASANA,
    )
    notifications = SqlNotificationRepository(engine)
    await notifications.patch(me, {"daily_cap": 5}, DEFAULTS)
    assert await notifications.claim(me, "moon:x", "moon", TUE)
    # SC-06: a calendar link (a secret: deleted with the account, never exported).
    from tristhana.infrastructure.db.calendar_feed import SqlCalendarFeedRepository

    token = hashlib.sha256(me.bytes).hexdigest()[:43]
    await SqlCalendarFeedRepository(engine, cipher).replace(
        me, hashlib.sha256(token.encode()).digest(), token
    )
    # NT-03: one I sent (exported as `announcements_sent`, deleted with the account).
    async with engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO tristhana.announcement (author_id, text, audience)"
                " VALUES (:a, 'Led class Sun 15 Nov, 7:00', 0)"
            ),
            {"a": me},
        )
        await conn.commit()


async def test_snapshot_opens_every_seal_for_the_owner(engine: AsyncEngine) -> None:
    me, tg = await _account(engine)
    await _fill(engine, me)

    owned = await _repo(engine).snapshot(me, DEFAULTS, date(2026, 9, 1))

    assert owned is not None
    assert owned.account.id == me
    assert [(i.provider, i.id) for i in owned.identities] == [("telegram", tg)]
    assert [(d.local_date, d.status, d.unreadable) for d in owned.days] == [
        (MON, DayStatus.LADIES, False),
        (TUE, DayStatus.PRACTICED, False),
        (WED, DayStatus.SKIPPED, False),
    ]
    assert owned.days[0].timezone == ZONE
    assert owned.days[2].timezone is None
    (period,) = owned.periods
    assert (period.start, period.end, period.kind) == (
        date(2026, 10, 1),
        date(2026, 10, 3),
        DayStatus.SICK,
    )
    (p,) = owned.practices
    assert p.local_date == TUE
    assert p.practice.context is PracticeContext.MYSORE
    assert p.practice.start_time == time(6, 30)
    (c,) = owned.check_ins
    assert c.check_in.mood == 4
    assert {t.value for t in c.check_in.tags} == {"calm"}
    (note,) = owned.notes
    assert note.text == "Лёгкая практика\nи вторая строка"
    assert owned.progression is not None
    assert owned.progression.position == KURMASANA
    assert [e.event.kind for e in owned.events] == [EventKind.START, EventKind.GIVEN]
    assert {e.marked_by for e in owned.events} == {MarkedBy.SELF}
    assert owned.settings.daily_cap == 5
    assert [(r.category, r.local_date, r.status) for r in owned.reminders] == [
        ("moon", TUE, "claimed")
    ]
    assert [(m.count, m.celebrated) for m in owned.milestones] == [(1, True)]


async def test_reminders_before_the_window_are_left_out(engine: AsyncEngine) -> None:
    me, _ = await _account(engine)
    await _fill(engine, me)

    owned = await _repo(engine).snapshot(me, DEFAULTS, WED)

    assert owned is not None
    assert owned.reminders == ()


async def test_unreadable_seals_stay_in_and_never_guess_ladies(engine: AsyncEngine) -> None:
    me, _ = await _account(engine)
    await _fill(engine, me, OTHER_KEYS)  # written with a key the reader doesn't have

    owned = await _repo(engine, KEYS).snapshot(me, DEFAULTS, date(2026, 9, 1))

    assert owned is not None
    assert (owned.days[0].status, owned.days[0].unreadable) == (DayStatus.REST, True)
    assert owned.days[1].unreadable is False  # plain rows need no key
    assert owned.periods[0].kind is None
    assert owned.notes[0].text is None


async def test_another_accounts_rows_never_appear(engine: AsyncEngine) -> None:
    me, _ = await _account(engine)
    other, _ = await _account(engine)
    await _fill(engine, other)

    owned = await _repo(engine).snapshot(me, DEFAULTS, date(2026, 9, 1))

    assert owned is not None
    assert (owned.days, owned.periods, owned.practices, owned.check_ins, owned.notes) == (
        (),
        (),
        (),
        (),
        (),
    )
    assert owned.progression is None
    assert owned.events == ()
    assert owned.reminders == ()
    assert len(owned.identities) == 1


async def test_snapshot_of_a_missing_account_is_none(engine: AsyncEngine) -> None:
    assert await _repo(engine).snapshot(UUID(int=1), DEFAULTS, MON) is None


async def test_claim_release_and_the_window(engine: AsyncEngine) -> None:
    me, _ = await _account(engine)
    repo = _repo(engine)
    window = timedelta(minutes=10)

    assert await repo.claim(me, NOW, NOW - window) is None
    later = NOW + timedelta(minutes=3)
    assert await repo.claim(me, later, later - window) == NOW
    await repo.release(me)
    assert await repo.claim(me, later, later - window) is None
    after = later + window
    assert await repo.claim(me, after, after - window) is None  # exactly 10 min: allowed


async def test_two_claims_at_once_exactly_one_wins(engine: AsyncEngine) -> None:
    me, _ = await _account(engine)
    repo = _repo(engine)

    results = await asyncio.gather(
        *(repo.claim(me, NOW, NOW - timedelta(minutes=10)) for _ in range(4))
    )

    assert results.count(None) == 1
    assert all(r == NOW for r in results if r is not None)


async def _counts(engine: AsyncEngine, account_id: UUID) -> dict[str, int]:
    found: dict[str, int] = {}
    async with engine.connect() as conn:
        for name in sorted(_account_tables()):
            mine = {
                "teacher_link": "student_id = :a OR teacher_id = :a",
                "shala": "owner_id = :a",  # SC-01
                "shala_staff_invite": "created_by = :a",
                "announcement": "author_id = :a",  # NT-03
                **dict.fromkeys(_SCHEDULE_TABLES, _OWNED_SHALA),  # SC-02: with my shala
            }.get(name, "account_id = :a")
            n = await conn.execute(
                text(f"SELECT count(*) FROM tristhana.{name} WHERE {mine}"),  # noqa: S608
                {"a": account_id},
            )
            found[name] = n.scalar_one()
    return found


_SCHEDULE_TABLES = ("shala_class", "shala_class_override", "shala_closure", "shala_swap")
_OWNED_SHALA = "shala_id IN (SELECT id FROM tristhana.shala WHERE owner_id = :a)"


async def _schedule(engine: AsyncEngine, shala: UUID, me: UUID) -> None:
    """SC-02: a class with a cancelled date, a closure and a swap in my shala."""
    repo = SqlScheduleRepository(engine)
    caps = ClassCaps(classes=40, closures=20, swaps=20)
    draft = ClassDraft(
        ClassType.MYSORE, None, False, None, None, time(6), 210, frozenset({1}), 1, MON, None
    )
    created = await repo.create(shala, me, draft, caps, MON)
    assert created.value is not None
    cancel = Override(MON, OverrideStatus.CANCELLED)
    assert (await repo.set_override(shala, me, created.value.id, cancel)).value
    assert (await repo.add_closure(shala, me, MON, MON, caps, MON)).value is not None
    swap = Swap(MON + timedelta(days=1), MON + timedelta(days=2))
    assert (await repo.add_swap(shala, me, swap, caps, MON)).value is not None


async def _shalas(engine: AsyncEngine, me: UUID, teacher: UUID) -> None:
    """SC-01: a shala I own with a pending staff link (and SC-02 classes), and a student row
    in the teacher's."""
    repo = SqlShalaRepository(engine)
    codes = SecretCodes()
    mine = await repo.create(
        me, NewShala("Mine", "almaty", False, frozenset(), codes.new()), CAPS, MON
    )
    assert mine is not None
    staff_invite = await repo.invite_staff(
        mine.id, me, ShalaRole.TEACHER, codes.new(), datetime.now(UTC) + timedelta(days=7), CAPS
    )
    assert staff_invite.done
    await _schedule(engine, mine.id, me)
    theirs = await repo.create(
        teacher, NewShala("Theirs", "almaty", False, frozenset(), codes.new()), CAPS, MON
    )
    assert theirs is not None
    link = await repo.join_link(theirs.id, teacher)
    assert link.value is not None
    assert await repo.join(link.value, me, CAPS, MON)


async def _link(engine: AsyncEngine, student: UUID, teacher: UUID) -> None:
    """A teacher link and the student's own invite (ID-04)."""
    links = SqlTeacherLinkRepository(engine)
    code = await links.invite(teacher, SecretCodes().new())
    assert await links.accept(code, student, Caps(20, 500), MON)
    await links.invite(student, SecretCodes().new())


async def test_delete_removes_every_row_and_nothing_else(engine: AsyncEngine) -> None:
    me, tg = await _account(engine)
    other, _ = await _account(engine)
    teacher, _ = await _account(engine)
    await _fill(engine, me)
    await _fill(engine, other)
    await _link(engine, me, teacher)
    await _link(engine, other, teacher)
    await _shalas(engine, me, teacher)
    await _shalas(engine, other, teacher)
    before = await _counts(engine, me)
    assert all(before[t] > 0 for t in _account_tables())  # the fill covers every table
    others = await _counts(engine, other)
    accounts = SqlAccountRepository(engine)

    assert await accounts.delete(me)

    assert set((await _counts(engine, me)).values()) == {0}
    assert await _counts(engine, other) == others
    assert await accounts.find_by_identity(IdentityKey(IdentityProvider.TELEGRAM, tg)) is None
    assert not await accounts.delete(me)  # already gone


async def test_delete_nulls_marked_by_on_other_accounts(engine: AsyncEngine) -> None:
    teacher, _ = await _account(engine)
    student, _ = await _account(engine)
    repo = SqlProgressionRepository(engine)
    await repo.apply(
        student,
        Change(EventKind.START, MON, Progression(NAVASANA), after=NAVASANA),
        None,
        teacher,
        before=None,
    )

    await SqlAccountRepository(engine).delete(teacher)

    owned = await _repo(engine).snapshot(student, DEFAULTS, MON)
    assert owned is not None
    assert [e.marked_by for e in owned.events] == [MarkedBy.UNKNOWN]


async def test_tick_claim_after_delete_is_false(engine: AsyncEngine) -> None:
    me, _ = await _account(engine)
    notifications = SqlNotificationRepository(engine)
    await SqlAccountRepository(engine).delete(me)

    assert not await notifications.claim(me, "moon:y", "moon", TUE)
    await notifications.mark_unreachable(me, NOW)  # no error, nothing written


def _account_tables() -> set[str]:
    """Every table whose rows belong to an account: an FK to `account`, directly or through
    another such table (`practice` → `day_log` → `account`)."""
    found: set[str] = set()
    changed = True
    while changed:
        changed = False
        for t in tables.metadata.sorted_tables:
            if t.name in found:
                continue
            if any(
                fk.column.table is tables.account or fk.column.table.name in found
                for fk in t.foreign_keys
            ):
                found.add(t.name)
                changed = True
    return found


def test_every_account_table_is_exported_or_excluded_on_purpose() -> None:
    assert _account_tables() == EXPORTED_TABLES | EXCLUDED_TABLES.keys()
    assert not EXPORTED_TABLES & EXCLUDED_TABLES.keys()


def test_every_fk_to_an_account_table_cascades_or_nulls() -> None:
    owned = _account_tables() | {"account"}
    for t in tables.metadata.sorted_tables:
        for fk in t.foreign_keys:
            if fk.column.table.name in owned:
                # SC-02: `SET NULL (teacher_id)` nulls one column of a composite FK.
                action = (fk.ondelete or "").upper().split(" (")[0]
                assert action in {"CASCADE", "SET NULL"}, t.name


def test_0016_follows_0015() -> None:
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(migrate.alembic_config("postgresql://unused"))
    revision = script.get_revision("0016")
    assert revision is not None
    assert revision.down_revision == "0015"


async def test_0016_down_and_up(migrated_url: str, engine: AsyncEngine) -> None:
    has_column = (
        "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'tristhana'"
        " AND table_name = 'account' AND column_name = 'export_claimed_at'"
    )
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0015")
    async with engine.connect() as conn:
        assert (await conn.execute(text(has_column))).scalar_one() == 0
    await asyncio.to_thread(migrate.upgrade, migrated_url)
    async with engine.connect() as conn:
        assert (await conn.execute(text(has_column))).scalar_one() == 1
    await asyncio.to_thread(migrate.check, migrated_url)


async def test_a_write_racing_the_delete_is_account_gone(engine: AsyncEngine) -> None:
    from tristhana.application.ports.export import AccountGone

    me, _ = await _account(engine)
    await SqlAccountRepository(engine).delete(me)

    with pytest.raises(AccountGone):
        await SqlDayLogRepository(engine, FieldCipher(KEYS)).upsert(
            me, DayLog(MON, DayStatus.PRACTICED), ZONE
        )
    with pytest.raises(AccountGone):
        await SqlDiaryRepository(engine, FieldCipher(KEYS)).save(me, MON, "late")


async def test_a_claim_that_waited_on_the_lock_loses_with_a_stale_instant(
    engine: AsyncEngine,
) -> None:
    """READ COMMITTED: a claim blocked by another claim re-checks the WHERE and loses, but
    its `earlier` CTE saw the old value. The use case must then wait the whole window."""
    from tristhana.application.export import ExportTooSoon, SendMyExport
    from tristhana.application.policies import Principal
    from tristhana.infrastructure.db.accounts import SqlAccountRepository as Accounts

    me, tg = await _account(engine)
    repo = _repo(engine)
    old = NOW - timedelta(minutes=30)
    assert await repo.claim(me, old, old - timedelta(minutes=10)) is None
    async with engine.connect() as other:
        await other.execute(text("BEGIN"))
        await other.execute(
            text("UPDATE tristhana.account SET export_claimed_at = :t WHERE id = :a"),
            {"t": NOW, "a": me},
        )
        waiting = asyncio.create_task(repo.claim(me, NOW, NOW - timedelta(minutes=10)))
        await asyncio.sleep(0.3)
        assert not waiting.done()  # blocked on the row lock
        await other.execute(text("COMMIT"))
    earlier = await waiting

    assert earlier == old  # stale: the snapshot's value
    account = await Accounts(engine).find_by_identity(IdentityKey(IdentityProvider.TELEGRAM, tg))
    assert account is not None

    class Clock:
        def now(self) -> datetime:
            return NOW

    class Repo:
        async def claim(self, *_: object) -> datetime | None:
            return earlier

    use_case = SendMyExport(Repo(), None, None, None, None, None, "", Clock())  # type: ignore[arg-type]
    with pytest.raises(ExportTooSoon) as e:
        await use_case.execute(Principal(account))
    assert e.value.wait == timedelta(minutes=10)
