"""The API's login role on real Postgres (ADR-0014, infra/supabase/roles.sql): after the
migrations, `tristhana_app` can use every table and sequence of the schema, and the
progression writes work as that role (PR-08: 0014's identity sequence needed 0015's grant;
the other DB tests run as a superuser and can't see a missing grant).

The role is created here when the test database lacks it (as roles.sql does in Supabase),
then the migrations are re-run from 0013 so their guarded grants apply."""

import asyncio
import base64
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tristhana.application.practice_patch import PracticePatch
from tristhana.domain.accounts import IdentityKey, IdentityProvider, NewAccount
from tristhana.domain.days import DayLog, DayStatus
from tristhana.domain.practice import PracticeLength
from tristhana.domain.progression import Change, EventKind, Position, Progression
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.days import SqlDayLogRepository
from tristhana.infrastructure.db.engine import asyncpg_url
from tristhana.infrastructure.db.practice import SqlPracticeRepository
from tristhana.infrastructure.db.progression import SqlProgressionRepository

pytestmark = pytest.mark.db

ROLE = "tristhana_app"
KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()
ON = date(2026, 10, 27)
ROLES_SQL = Path(__file__).resolve().parents[3] / "infra" / "supabase" / "roles.sql"


@pytest.fixture
async def app_engine(migrated_url: str, engine: AsyncEngine) -> AsyncIterator[AsyncEngine]:
    async with engine.connect() as conn:
        exists = await conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": ROLE})
        if exists.scalar_one_or_none() is None:
            await conn.execute(text("CREATE ROLE tristhana_app NOLOGIN"))
        # The catch-up block of roles.sql (tables), as the owner runs it in Supabase.
        catch_up = ROLES_SQL.read_text().split("DO $$", 1)[1].rsplit("$$;", 1)[0]
        await conn.execute(text(f"DO $${catch_up}$$;"))
        # Production before 0015: roles.sql then granted tables only. Start from there, so
        # only the migrations can grant the sequences.
        await conn.execute(
            text(
                "ALTER DEFAULT PRIVILEGES IN SCHEMA tristhana"
                " REVOKE USAGE, SELECT ON SEQUENCES FROM tristhana_app"
            )
        )
        await conn.execute(
            text("REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA tristhana FROM tristhana_app")
        )
    # Re-run 0014-0015 so their guarded grants see the role (0015's downgrade revokes).
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0013")
    await asyncio.to_thread(migrate.upgrade, migrated_url)
    app = create_async_engine(
        asyncpg_url(migrated_url),
        connect_args={"server_settings": {"role": ROLE}},
        isolation_level="AUTOCOMMIT",
    )
    yield app
    await app.dispose()


async def test_the_app_role_can_use_every_table_and_sequence(
    engine: AsyncEngine, app_engine: AsyncEngine
) -> None:
    async with engine.connect() as conn:
        missing = await conn.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE n.nspname = 'tristhana' AND c.relname <> 'alembic_version' AND ("
                "  (c.relkind = 'r' AND NOT has_table_privilege("
                "    :r, c.oid, 'SELECT, INSERT, UPDATE, DELETE'))"
                "  OR (c.relkind = 'S' AND NOT has_sequence_privilege(:r, c.oid, 'USAGE')))"
            ),
            {"r": ROLE},
        )
        assert missing.scalars().all() == []


async def _account(engine: AsyncEngine, telegram_id: str = "7777") -> UUID:
    account = await SqlAccountRepository(engine).create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, telegram_id),
        NewAccount(display_name="A", locale="en"),
    )
    return account.id


async def test_progression_writes_work_as_the_app_role(app_engine: AsyncEngine) -> None:
    me = await _account(app_engine)
    repo = SqlProgressionRepository(app_engine)
    navasana, kurmasana = Position("primary", "navasana"), Position("primary", "kurmasana")
    start = Change(EventKind.START, ON, Progression(navasana), after=navasana)

    first = await repo.apply(me, start, None, me)
    assert first is not None
    given = Change(EventKind.GIVEN, ON, Progression(kurmasana), navasana, kurmasana)
    second = await repo.apply(me, given, first.id, me)
    assert second is not None
    await repo.dismiss_hint(me, Position("primary", "supta-kurmasana"))
    assert await repo.undo(me, second.id)
    view = await repo.get(me)
    assert view.progression is not None
    assert view.progression.position == navasana

    days = SqlDayLogRepository(app_engine, FieldCipher(KEYS))
    await days.upsert(me, DayLog(ON, DayStatus.PRACTICED), "Asia/Almaty")
    practices = SqlPracticeRepository(app_engine)
    saved = await practices.save(
        me, ON, PracticePatch.of(length=PracticeLength(("primary",), "kurmasana"))
    )
    assert saved is not None
    assert saved.progression is not None
    _, found = await practices.recent_with_progression(me, date(2026, 10, 28), 60)
    assert found is not None


async def test_the_teacher_view_reads_work_as_the_app_role(app_engine: AsyncEngine) -> None:
    """ST-06: both statements, the new column included, under the app role's table grants."""
    from tristhana.domain.teacher_view import SharedDay
    from tristhana.infrastructure.db.teacher_view import SqlTeacherViewRepository

    teacher, student = await _account(app_engine), await _account(app_engine, "7778")
    async with app_engine.connect() as conn:
        await conn.execute(
            text(
                "INSERT INTO tristhana.teacher_link"
                " (student_id, teacher_id, linked_on, quiet_note_agreed)"
                " VALUES (:s, :t, :on, true)"
            ),
            {"s": student, "t": teacher, "on": ON},
        )
    await SqlDayLogRepository(app_engine, FieldCipher(KEYS)).upsert(
        student, DayLog(ON, DayStatus.LADIES), "Asia/Almaty"
    )
    repo = SqlTeacherViewRepository(app_engine)

    page = await repo.page(teacher, 0, 10, ON, ON)
    detail = await repo.student(teacher, student, ON, ON)

    assert page.total == 1
    assert page.students[0].shown == {ON: SharedDay.REST}
    assert detail is not None
    assert detail.quiet_note_agreed is True


async def test_export_and_delete_work_as_the_app_role(app_engine: AsyncEngine) -> None:
    """ST-09: the claim, the read-only snapshot transaction and the account delete."""
    from datetime import UTC, datetime, timedelta

    from tristhana.domain.notifications import DEFAULTS
    from tristhana.infrastructure.db.export import SqlExportRepository

    me = await _account(app_engine)
    days = SqlDayLogRepository(app_engine, FieldCipher(KEYS))
    await days.upsert(me, DayLog(ON, DayStatus.LADIES), "Asia/Almaty")
    export = SqlExportRepository(app_engine, FieldCipher(KEYS))
    now = datetime(2026, 10, 27, 12, tzinfo=UTC)

    assert await export.claim(me, now, now - timedelta(minutes=10)) is None
    owned = await export.snapshot(me, DEFAULTS, ON)
    assert owned is not None
    assert owned.days[0].status is DayStatus.LADIES
    await export.release(me)
    assert await SqlAccountRepository(app_engine).delete(me)


async def test_teacher_link_writes_work_as_the_app_role(app_engine: AsyncEngine) -> None:
    """ID-04: accept, set primary, rotate, unlink and the export read, as `tristhana_app`. The
    0019 tables take their grants from the schema defaults (0001)."""
    from datetime import UTC, datetime, timedelta

    from tristhana.application.ports.teacher_links import Caps
    from tristhana.domain.notifications import DEFAULTS
    from tristhana.domain.teacher_links import MAX_STUDENTS, MAX_TEACHERS
    from tristhana.infrastructure.db.export import SqlExportRepository
    from tristhana.infrastructure.db.teacher_links import SqlTeacherLinkRepository

    teacher, student = await _account(app_engine, "7001"), await _account(app_engine, "7002")
    repo = SqlTeacherLinkRepository(app_engine)
    caps = Caps(teachers=MAX_TEACHERS, students=MAX_STUDENTS)

    code = await repo.invite(teacher, "aB3dE6gH9jK2mN5p")
    accepted = await repo.accept(code, student, caps, ON)
    assert accepted is not None
    assert accepted.created
    assert await repo.set_primary(student, teacher)
    assert await repo.rotate(teacher, "Zy8xW7vU6tS5rQ4p") == "Zy8xW7vU6tS5rQ4p"

    export = SqlExportRepository(app_engine, FieldCipher(KEYS))
    now = datetime(2026, 10, 27, 12, tzinfo=UTC)
    assert await export.claim(student, now, now - timedelta(minutes=10)) is None
    owned = await export.snapshot(student, DEFAULTS, ON)
    assert owned is not None
    assert len(owned.links) == 1

    assert (await repo.unlink(student, teacher)).removed
    assert (await repo.overview(student)).teachers == ()


async def test_the_moon_follow_reads_and_keep_work_as_the_app_role(app_engine: AsyncEngine) -> None:
    """MD-02: the account load with `teaches` and the main teacher, the conditional Keep
    write and the tick's candidates, as `tristhana_app`."""
    from datetime import UTC, datetime, timedelta

    from tristhana.application.ports.teacher_links import Caps
    from tristhana.domain.moon import TeacherMoon
    from tristhana.domain.notifications import DEFAULTS
    from tristhana.domain.teacher_links import MAX_STUDENTS, MAX_TEACHERS
    from tristhana.infrastructure.db.notifications import SqlNotificationRepository
    from tristhana.infrastructure.db.teacher_links import SqlTeacherLinkRepository

    teacher, student = await _account(app_engine, "7101"), await _account(app_engine, "7102")
    accounts = SqlAccountRepository(app_engine)
    await accounts.set_moon_location(teacher, "almaty")
    links = SqlTeacherLinkRepository(app_engine)
    caps = Caps(teachers=MAX_TEACHERS, students=MAX_STUDENTS)
    accepted = await links.accept(
        await links.invite(teacher, "aB3dE6gH9jK2mN5p"), student, caps, ON
    )
    assert accepted is not None

    found = await accounts.find_by_identity(IdentityKey(IdentityProvider.TELEGRAM, "7102"))
    assert found is not None
    assert found.main_teacher is not None
    assert found.main_teacher == TeacherMoon(teacher, found.main_teacher.name, "almaty")
    kept = await accounts.set_moon_location_if_unset(student, "almaty")
    assert kept is not None
    assert kept.moon_location == "almaty"
    now = datetime(2026, 10, 27, 12, tzinfo=UTC)
    await accounts.set_timezone_if_unset(student, "Asia/Almaty")
    candidates = await SqlNotificationRepository(app_engine).candidates(
        now - timedelta(days=12), now.date(), DEFAULTS
    )
    assert {c.account_id: c.teacher_location for c in candidates}.get(student) == "almaty"
