"""Check-ins on real Postgres (PR-06, ADR-0024): the practiced-day EXISTS guard, per-field
upserts, atomic tag toggles, the lifecycle with status changes (same statement), the LEFT
JOIN in `_range`, unknown stored tags, `account.offer_check_in`, every CHECK, and 0012.

`SqlCheckInRepository` and the domain types are imported inside the tests (test-first)."""

import asyncio
import base64
import itertools
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tristhana.application.practice_patch import PracticePatch
from tristhana.domain.accounts import IdentityKey, IdentityProvider, NewAccount, ProfileChange
from tristhana.domain.days import DayLog, DayStatus
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.days import SqlDayLogRepository
from tristhana.infrastructure.db.practice import SqlPracticeRepository

pytestmark = pytest.mark.db

KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()
ZONE = "Asia/Almaty"
FRI, SAT, MON = date(2026, 10, 16), date(2026, 10, 17), date(2026, 10, 19)
_users = itertools.count(42)


def _repo(engine: AsyncEngine) -> Any:
    from tristhana.infrastructure.db.check_in import SqlCheckInRepository

    return SqlCheckInRepository(engine)


def _c(**values: Any) -> Any:
    from tristhana.domain.check_in import CheckIn, CheckInTag

    tags = values.pop("tags", ())
    return CheckIn(**values, tags=frozenset(CheckInTag(t) for t in tags))


def _of(**values: Any) -> Any:
    from tristhana.application.check_in_patch import CheckInPatch
    from tristhana.domain.check_in import CheckInTag

    if "tags" in values:
        values["tags"] = frozenset(CheckInTag(t) for t in values["tags"])
    return CheckInPatch.of(**values)


def _tag(key: str) -> Any:
    from tristhana.domain.check_in import CheckInTag

    return CheckInTag(key)


async def _setup(engine: AsyncEngine, *practiced: date) -> tuple[UUID, SqlDayLogRepository]:
    account = await SqlAccountRepository(engine).create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, str(next(_users))),
        NewAccount(display_name="A", locale="en"),
    )
    days = SqlDayLogRepository(engine, FieldCipher(KEYS))
    for day in practiced:
        await days.upsert(account.id, DayLog(day, DayStatus.PRACTICED), ZONE)
    return account.id, days


async def _rows(engine: AsyncEngine) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text("SELECT count(*) FROM tristhana.check_in"))).scalar_one()


@contextmanager
def _statements(engine: AsyncEngine) -> Generator[list[str]]:
    """The application statements sent while inside (pool pings and the like ignored)."""
    seen: list[str] = []

    def record(_conn: object, _cursor: object, statement: str, *_: object) -> None:
        if "tristhana." in statement:
            seen.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        yield seen
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)


# Writes


@pytest.mark.parametrize("status", [s for s in DayStatus if s is not DayStatus.PRACTICED])
async def test_no_check_in_on_a_day_that_is_not_practiced(
    engine: AsyncEngine, status: DayStatus
) -> None:
    me, days = await _setup(engine)
    await days.upsert(me, DayLog(MON, status), None)
    repo = _repo(engine)

    assert await repo.save(me, MON, _of(mood=3)) is None
    assert await repo.set_tag(me, MON, _tag("calm"), True) is None
    assert await _rows(engine) == 0


async def test_no_check_in_on_a_day_never_logged(engine: AsyncEngine) -> None:
    me, _ = await _setup(engine)
    repo = _repo(engine)

    assert await repo.save(me, MON, _of(mood=3)) is None
    assert await repo.set_tag(me, MON, _tag("calm"), True) is None
    assert await _rows(engine) == 0


async def test_patches_upsert_only_their_fields_in_one_statement(engine: AsyncEngine) -> None:
    me, _ = await _setup(engine, MON)
    repo = _repo(engine)

    await repo.save(me, MON, _of(mood=4))
    with _statements(engine) as seen:
        saved = await repo.save(me, MON, _of(energy=2))
    cleared = await repo.save(me, MON, _of(mood=None, effort=5))

    assert len(seen) == 1
    assert saved == _c(mood=4, energy=2)
    assert cleared == _c(energy=2, effort=5)


async def test_an_empty_save_is_stored_as_a_row(engine: AsyncEngine) -> None:
    from tristhana.application.check_in_patch import CheckInPatch

    me, _ = await _setup(engine, MON)

    saved = await _repo(engine).save(me, MON, CheckInPatch.full(_c()))

    assert saved == _c()
    assert await _rows(engine) == 1  # read back as none by the use case


async def test_set_tag_is_absolute_idempotent_and_one_statement(engine: AsyncEngine) -> None:
    me, _ = await _setup(engine, MON)
    repo = _repo(engine)
    await repo.save(me, MON, _of(mood=3))

    with _statements(engine) as seen:
        first = await repo.set_tag(me, MON, _tag("light"), True)
    twice = await repo.set_tag(me, MON, _tag("light"), True)
    off = await repo.set_tag(me, MON, _tag("light"), False)
    off_again = await repo.set_tag(me, MON, _tag("light"), False)

    assert len(seen) == 1
    assert first == twice == _c(mood=3, tags=["light"])
    assert off == off_again == _c(mood=3)


async def test_a_first_tag_creates_the_row(engine: AsyncEngine) -> None:
    me, _ = await _setup(engine, MON)

    saved = await _repo(engine).set_tag(me, MON, _tag("sore"), True)

    assert saved == _c(tags=["sore"])


async def test_two_concurrent_tag_taps_both_land(engine: AsyncEngine) -> None:
    me, _ = await _setup(engine, MON)
    repo = _repo(engine)
    await repo.save(me, MON, _of(mood=4))

    await asyncio.gather(
        repo.set_tag(me, MON, _tag("stiff"), True),
        repo.set_tag(me, MON, _tag("calm"), True),
        repo.set_tag(me, MON, _tag("steady_breath"), True),
    )

    [day] = await SqlDayLogRepository(engine, FieldCipher(KEYS)).list_range(me, MON, MON)
    assert day.check_ins == (_c(mood=4, tags=["stiff", "calm", "steady_breath"]),)  # type: ignore[attr-defined]


async def test_concurrent_first_taps_on_a_new_row_both_land(engine: AsyncEngine) -> None:
    me, _ = await _setup(engine, MON)
    repo = _repo(engine)

    await asyncio.gather(
        repo.save(me, MON, _of(mood=2)),
        repo.set_tag(me, MON, _tag("heavy"), True),
    )

    [day] = await SqlDayLogRepository(engine, FieldCipher(KEYS)).list_range(me, MON, MON)
    assert day.check_ins == (_c(mood=2, tags=["heavy"]),)  # type: ignore[attr-defined]


async def test_delete_is_idempotent(engine: AsyncEngine) -> None:
    me, _ = await _setup(engine, MON)
    repo = _repo(engine)
    await repo.save(me, MON, _of(mood=3))

    await repo.delete(me, MON)
    await repo.delete(me, MON)
    await repo.delete(me, FRI)  # never had one

    assert await _rows(engine) == 0


# Lifecycle


async def test_a_status_change_deletes_the_check_in_in_the_same_statement(
    engine: AsyncEngine,
) -> None:
    me, days = await _setup(engine, MON)
    await _repo(engine).save(me, MON, _of(mood=4, tags=["calm"]))

    with _statements(engine) as seen:
        await days.upsert(me, DayLog(MON, DayStatus.REST), ZONE)

    assert len(seen) == 1
    assert await _rows(engine) == 0


async def test_practiced_again_after_rest_does_not_bring_it_back(engine: AsyncEngine) -> None:
    me, days = await _setup(engine, MON)
    await _repo(engine).save(me, MON, _of(mood=4))
    await days.upsert(me, DayLog(MON, DayStatus.REST), ZONE)

    await days.upsert(me, DayLog(MON, DayStatus.PRACTICED), ZONE)  # accepted (spec §2)

    [day] = await days.list_range(me, MON, MON)
    assert day.check_ins == ()  # type: ignore[attr-defined]


async def test_practiced_again_on_a_practiced_day_keeps_it(engine: AsyncEngine) -> None:
    me, days = await _setup(engine, MON)
    await _repo(engine).save(me, MON, _of(energy=5))

    await days.upsert(me, DayLog(MON, DayStatus.PRACTICED), ZONE)

    [day] = await days.list_range(me, MON, MON)
    assert day.check_ins == (_c(energy=5),)  # type: ignore[attr-defined]


async def test_remove_details_keeps_the_check_in(engine: AsyncEngine) -> None:
    me, days = await _setup(engine, MON)
    practices = SqlPracticeRepository(engine)
    await practices.save(me, MON, PracticePatch.of(duration_min=90))
    await _repo(engine).save(me, MON, _of(effort=2))

    await practices.delete(me, MON)

    [day] = await days.list_range(me, MON, MON)
    assert day.practices == ()
    assert day.check_ins == (_c(effort=2),)  # type: ignore[attr-defined]


async def test_clearing_the_day_cascades(engine: AsyncEngine) -> None:
    me, days = await _setup(engine, MON)
    await _repo(engine).save(me, MON, _of(mood=1))

    await days.delete(me, MON)

    assert await _rows(engine) == 0


async def test_deleting_the_account_cascades(engine: AsyncEngine) -> None:
    me, _ = await _setup(engine, MON)
    await _repo(engine).save(me, MON, _of(mood=5))

    async with engine.connect() as conn:
        await conn.execute(text("DELETE FROM tristhana.account WHERE id = :id"), {"id": me})

    assert await _rows(engine) == 0


# Reads


async def test_range_joins_check_ins_of_practiced_days_in_one_statement(
    engine: AsyncEngine,
) -> None:
    me, days = await _setup(engine, FRI, MON)
    await days.upsert(me, DayLog(SAT, DayStatus.REST), ZONE)
    await _repo(engine).save(me, MON, _of(mood=4, energy=3, tags=["light", "calm"]))

    with _statements(engine) as seen:
        logged = await days.list_range(me, FRI, MON)

    assert len(seen) == 1
    assert [(d.local_date, d.check_ins) for d in logged] == [  # type: ignore[attr-defined]
        (FRI, ()),
        (SAT, ()),
        (MON, (_c(mood=4, energy=3, tags=["light", "calm"]),)),
    ]


async def test_range_with_moon_and_history_carry_check_ins_too(engine: AsyncEngine) -> None:
    me, days = await _setup(engine, MON)
    await _repo(engine).save(me, MON, _of(mood=2))

    with _statements(engine) as seen:
        view = await days.range_with_moon(me, FRI, MON, "mysuru")

    assert len(seen) == 1
    assert [d.check_ins for d in view.days] == [(_c(mood=2),)]  # type: ignore[attr-defined]


async def test_a_leftover_on_a_day_no_longer_practiced_is_never_read(
    engine: AsyncEngine,
) -> None:
    me, days = await _setup(engine, MON)
    await _repo(engine).save(me, MON, _of(mood=3))
    # Simulate a race / old revision: the day changed but its check-in stayed behind.
    async with engine.connect() as conn:
        await conn.execute(
            text("UPDATE tristhana.day_log SET status = 'skipped' WHERE local_date = :d"),
            {"d": MON},
        )

    [day] = await days.list_range(me, MON, MON)

    assert day.status is DayStatus.SKIPPED
    assert day.check_ins == ()  # type: ignore[attr-defined]


async def test_unknown_stored_tags_are_dropped_on_read(engine: AsyncEngine) -> None:
    me, days = await _setup(engine, MON)
    await _repo(engine).save(me, MON, _of(mood=3, tags=["calm"]))
    async with engine.connect() as conn:  # a tag a later release removed
        await conn.execute(text("UPDATE tristhana.check_in SET tags = '{calm,sleepy}'"))

    [day] = await days.list_range(me, MON, MON)
    toggled = await _repo(engine).set_tag(me, MON, _tag("light"), True)

    assert day.check_ins == (_c(mood=3, tags=["calm"]),)  # type: ignore[attr-defined]
    assert toggled == _c(mood=3, tags=["calm", "light"])


async def test_check_ins_are_per_account(engine: AsyncEngine) -> None:
    me, days = await _setup(engine, MON)
    other, _ = await _setup(engine, MON)
    await _repo(engine).save(me, MON, _of(mood=5))

    [theirs] = await days.list_range(other, MON, MON)

    assert theirs.check_ins == ()  # type: ignore[attr-defined]


# Schema


async def test_offer_check_in_defaults_to_on_and_is_its_own_field_group(
    engine: AsyncEngine,
) -> None:
    me, _ = await _setup(engine)
    repo = SqlAccountRepository(engine)
    account = await repo.set_timezone_if_unset(me, "UTC")
    assert account.offer_check_in is True  # type: ignore[attr-defined]

    off = await repo.update_settings(
        me,
        ProfileChange(
            "X",
            True,
            "ru",
            True,
            None,
            offer_check_in=False,  # type: ignore[call-arg]
            fields=frozenset({"offer_check_in"}),
        ),
    )

    assert off.offer_check_in is False  # type: ignore[attr-defined]
    assert (off.display_name, off.locale) == ("A", "en")  # only the sent group is written


@pytest.mark.parametrize(
    "bad",
    [
        "UPDATE tristhana.check_in SET slot = 2",
        "UPDATE tristhana.check_in SET mood = 0",
        "UPDATE tristhana.check_in SET mood = 6",
        "UPDATE tristhana.check_in SET energy = 0",
        "UPDATE tristhana.check_in SET energy = 6",
        "UPDATE tristhana.check_in SET effort = 0",
        "UPDATE tristhana.check_in SET effort = 6",
        "UPDATE tristhana.check_in SET tags = NULL",
        "UPDATE tristhana.check_in SET tags = array_fill('calm'::text, ARRAY[17])",
        "UPDATE tristhana.check_in SET local_date = '2026-10-18'",  # no day_log row there
    ],
)
async def test_database_checks(engine: AsyncEngine, bad: str) -> None:
    me, _ = await _setup(engine, MON)
    await _repo(engine).save(me, MON, _of(mood=3))

    with pytest.raises(IntegrityError):
        async with engine.connect() as conn:
            await conn.execute(text(bad))


async def test_sixteen_stored_tags_are_still_allowed(engine: AsyncEngine) -> None:
    me, _ = await _setup(engine, MON)
    await _repo(engine).save(me, MON, _of(mood=3))

    async with engine.connect() as conn:
        await conn.execute(
            text("UPDATE tristhana.check_in SET tags = array_fill('calm'::text, ARRAY[16])")
        )

    assert await _rows(engine) == 1


# Migration 0012 (expand-only)


async def _exists(engine: AsyncEngine, sql: str) -> bool:
    async with engine.connect() as conn:
        return (await conn.execute(text(sql))).scalar_one() > 0


_HAS_TABLE = (
    "SELECT count(*) FROM information_schema.tables"
    " WHERE table_schema = 'tristhana' AND table_name = 'check_in'"
)
_HAS_COLUMN = (
    "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'tristhana'"
    " AND table_name = 'account' AND column_name = 'offer_check_in'"
)


async def test_0012_adds_check_in_and_the_setting_and_downgrade_drops_them(
    migrated_url: str, engine: AsyncEngine
) -> None:
    me, _ = await _setup(engine)
    assert await _exists(engine, _HAS_TABLE)
    assert await _exists(engine, _HAS_COLUMN)
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0011")
    try:
        assert not await _exists(engine, _HAS_TABLE)
        assert not await _exists(engine, _HAS_COLUMN)
    finally:
        await asyncio.to_thread(migrate.upgrade, migrated_url)
    assert await _exists(engine, _HAS_TABLE)
    account = await SqlAccountRepository(engine).set_timezone_if_unset(me, "UTC")
    assert account.offer_check_in is True  # type: ignore[attr-defined]  # existing rows: on


def test_0012_tables_match_the_metadata(migrated_url: str) -> None:
    migrate.check(migrated_url)
