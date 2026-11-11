"""SC-01 on real Postgres (spec §3, §6, §7, §8; ADR-0033): the CHECKs; the cascades (shala,
owner, member); single use under a double tap; staff/student exclusivity under a race; the
account load carrying the main shala identically from every method, with `teacher_on_staff`
and the Q108 order changing on the next read with no write; the tick candidates; statement
counts; the plan on 1000 students; the app role; 0021 up/down/up; the export; and the SQL
guards matching `application/policies.py` over the role matrix."""

import asyncio
import base64
import itertools
import json
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.domain.test_practice import catalog
from tests.fakes import FakeNotifier, FakePacker, FixedClock, cities
from tristhana.application.export import SendMyExport
from tristhana.application.labels import PracticeLabels
from tristhana.application.policies import (
    Principal,
    can_remove_staff,
    can_set_roles,
)
from tristhana.application.ports.shalas import NewShala, ShalaCaps
from tristhana.application.ports.teacher_links import Caps
from tristhana.domain.accounts import (
    Account,
    IdentityKey,
    IdentityProvider,
    NewAccount,
    ProfileChange,
    ProfileUpdate,
    moon_follow_of,
)
from tristhana.domain.moon import FOLLOW_SHALA, MoonSource, ShalaMoon, moon_follow
from tristhana.domain.notifications import DEFAULTS
from tristhana.domain.progression import Track
from tristhana.domain.rest_days import DayOff
from tristhana.domain.shalas import (
    MAX_OWNED,
    MAX_PENDING_STAFF_INVITES,
    MAX_STAFF,
    MAX_STAFF_OF,
    MAX_STUDENT_OF,
    MAX_STUDENTS,
    Membership,
    ShalaPatch,
    ShalaRole,
)
from tristhana.domain.teacher_links import MAX_STUDENTS as LINK_STUDENTS
from tristhana.domain.teacher_links import MAX_TEACHERS
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.export import SqlExportRepository
from tristhana.infrastructure.db.notifications import SqlNotificationRepository
from tristhana.infrastructure.db.shalas import SqlShalaRepository
from tristhana.infrastructure.db.teacher_links import SqlTeacherLinkRepository
from tristhana.infrastructure.i18n.fluent import FluentTranslator

pytestmark = pytest.mark.db

ON = date(2026, 11, 7)
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
CAPS = ShalaCaps(
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
_users = itertools.count(80_000)
_codes = itertools.count(1)


def _code(prefix: str = "c") -> str:
    return f"{prefix}{next(_codes):0{16 - len(prefix)}d}"


def _key(tg: str) -> IdentityKey:
    return IdentityKey(IdentityProvider.TELEGRAM, tg)


async def _person(
    engine: AsyncEngine, name: str | None = "Person", moon: str | None = None
) -> tuple[Account, IdentityKey]:
    repo = SqlAccountRepository(engine)
    key = _key(str(next(_users)))
    account = await repo.create_with_identity(key, NewAccount(display_name=name, locale="en"))
    await repo.set_timezone_if_unset(account.id, "Asia/Almaty")
    if moon is not None:
        await repo.set_moon_location(account.id, moon)
    return account, key


async def _find(engine: AsyncEngine, key: IdentityKey) -> Account:
    found = await SqlAccountRepository(engine).find_by_identity(key)
    assert found is not None
    return found


async def _shala(
    engine: AsyncEngine,
    owner: UUID,
    city: str = "almaty",
    name: str = "Ashtanga Almaty",
    roles: frozenset[ShalaRole] = frozenset({TEACHER}),
) -> UUID:
    card = await SqlShalaRepository(engine).create(
        owner, NewShala(name, city, False, roles, _code("J")), CAPS, ON
    )
    assert card is not None
    return card.id


async def _staff(engine: AsyncEngine, shala: UUID, owner: UUID, who: UUID, role: ShalaRole) -> None:
    repo = SqlShalaRepository(engine)
    code = _code("S")
    invited = await repo.invite_staff(shala, owner, role, code, NOW + timedelta(days=7), CAPS)
    assert invited.done
    accepted = await repo.accept_staff(code, who, CAPS, ON)
    assert accepted is not None
    assert accepted.created


async def _student(engine: AsyncEngine, shala: UUID, owner: UUID, who: UUID) -> None:
    repo = SqlShalaRepository(engine)
    link = await repo.join_link(shala, owner)
    assert link.value is not None
    joined = await repo.join(link.value, who, CAPS, ON)
    assert joined is not None
    assert joined.created


async def _link(engine: AsyncEngine, student: UUID, teacher: UUID) -> None:
    repo = SqlTeacherLinkRepository(engine)
    accepted = await repo.accept(await repo.invite(teacher, _code("T")), student, LINK_CAPS, ON)
    assert accepted is not None
    assert accepted.created


async def _sql(engine: AsyncEngine, statement: str, **params: Any) -> Any:
    async with engine.connect() as conn:
        result = await conn.execute(text(statement), params)
        await conn.commit()
        return result


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


# CHECKs


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("name", ""),
        ("name", "x" * 65),
        ("city", "-shala"),
        ("city", "-teacher"),
        ("city", "Almaty"),
        ("moon_city", "-shala"),
        ("join_code", "short"),
        ("join_code", "aB3dE6gH9jK2mN5-"),
    ],
)
async def test_the_shala_checks(engine: AsyncEngine, column: str, value: str) -> None:
    owner, _ = await _person(engine)
    values = {
        "name": "Shala",
        "city": "almaty",
        "moon_city": None,
        "join_code": _code("J"),
    } | {column: value}

    with pytest.raises((IntegrityError, DBAPIError)):
        await _sql(
            engine,
            "INSERT INTO tristhana.shala (name, city, moon_city, owner_id, join_code)"
            " VALUES (:name, :city, :moon_city, :owner, :join_code)",
            owner=owner.id,
            **values,
        )


async def test_the_role_checks(engine: AsyncEngine) -> None:
    owner, _ = await _person(engine)
    shala = await _shala(engine, owner.id)

    with pytest.raises((IntegrityError, DBAPIError)):
        await _sql(
            engine,
            "UPDATE tristhana.shala_staff SET roles = '{owner}' WHERE shala_id = :s",
            s=shala,
        )
    with pytest.raises((IntegrityError, DBAPIError)):
        await _sql(
            engine,
            "INSERT INTO tristhana.shala_staff_invite (code, shala_id, role, created_by,"
            " expires_at) VALUES (:c, :s, 'owner', :o, now())",
            c=_code("S"),
            s=shala,
            o=owner.id,
        )


async def test_the_owner_has_a_staff_row_with_the_ticked_roles(engine: AsyncEngine) -> None:
    owner, _ = await _person(engine, "Anna")

    shala = await _shala(engine, owner.id, roles=frozenset({TEACHER, ASSISTANT}))
    card = await SqlShalaRepository(engine).card(shala, owner.id)

    assert card is not None
    assert card.me == Membership(shala, True, frozenset({TEACHER, ASSISTANT}), False)
    assert [(s.id, s.owner) for s in card.staff] == [(owner.id, True)]


async def test_the_owned_cap_holds(engine: AsyncEngine) -> None:
    owner, _ = await _person(engine)
    for _ in range(MAX_OWNED):
        await _shala(engine, owner.id)

    refused = await SqlShalaRepository(engine).create(
        owner.id, NewShala("One more", "almaty", False, frozenset(), _code("J")), CAPS, ON
    )

    assert refused is None


# Cascades


async def _counts(engine: AsyncEngine, shala: UUID) -> tuple[int, int, int, int]:
    row = (
        await _sql(
            engine,
            "SELECT (SELECT count(*) FROM tristhana.shala WHERE id = :s),"
            " (SELECT count(*) FROM tristhana.shala_staff WHERE shala_id = :s),"
            " (SELECT count(*) FROM tristhana.shala_student WHERE shala_id = :s),"
            " (SELECT count(*) FROM tristhana.shala_staff_invite WHERE shala_id = :s)",
            s=shala,
        )
    ).one()
    return tuple(row)


async def _populated(engine: AsyncEngine) -> tuple[UUID, Account, Account, Account]:
    owner, _ = await _person(engine, "Anna")
    staff, _ = await _person(engine, "Boris")
    student, _ = await _person(engine, "Chandra")  # not a substring of the shala's name
    shala = await _shala(engine, owner.id)
    await _staff(engine, shala, owner.id, staff.id, TEACHER)
    await _student(engine, shala, owner.id, student.id)
    assert (
        await SqlShalaRepository(engine).invite_staff(
            shala, owner.id, OFFICE, _code("S"), NOW + timedelta(days=7), CAPS
        )
    ).done
    return shala, owner, staff, student


async def test_deleting_a_shala_takes_every_row(engine: AsyncEngine) -> None:
    shala, owner, _, _ = await _populated(engine)
    assert await _counts(engine, shala) == (1, 2, 1, 1)

    assert (await SqlShalaRepository(engine).delete(shala, owner.id)).done

    assert await _counts(engine, shala) == (0, 0, 0, 0)


async def test_deleting_the_owners_account_deletes_the_shala(engine: AsyncEngine) -> None:
    """Q102: no ownerless shala."""
    shala, owner, _, _ = await _populated(engine)

    assert await SqlAccountRepository(engine).delete(owner.id)

    assert await _counts(engine, shala) == (0, 0, 0, 0)


@pytest.mark.parametrize("who", ["staff", "student"])
async def test_deleting_a_members_account_takes_only_their_row(
    engine: AsyncEngine, who: str
) -> None:
    shala, _, staff, student = await _populated(engine)

    assert await SqlAccountRepository(engine).delete((staff if who == "staff" else student).id)

    assert await _counts(engine, shala) == ((1, 1, 1, 1) if who == "staff" else (1, 2, 0, 1))


# Single use and exclusivity under races


async def test_two_concurrent_staff_accepts_make_one_row(engine: AsyncEngine) -> None:
    owner, _ = await _person(engine)
    a, _ = await _person(engine)
    b, _ = await _person(engine)
    shala = await _shala(engine, owner.id)
    repo = SqlShalaRepository(engine)
    code = _code("S")
    assert (
        await repo.invite_staff(shala, owner.id, TEACHER, code, NOW + timedelta(days=7), CAPS)
    ).done

    results = await asyncio.gather(
        repo.accept_staff(code, a.id, CAPS, ON), repo.accept_staff(code, b.id, CAPS, ON)
    )

    assert sorted(r is None or not r.created for r in results) == [False, True]
    assert (await _counts(engine, shala))[1] == 2  # the owner and one winner
    assert (await _counts(engine, shala))[3] == 0  # the invite is spent


async def test_a_double_tap_by_the_same_person_accepts_once(engine: AsyncEngine) -> None:
    owner, _ = await _person(engine)
    me, _ = await _person(engine)
    shala = await _shala(engine, owner.id)
    repo = SqlShalaRepository(engine)
    code = _code("S")
    assert (
        await repo.invite_staff(shala, owner.id, TEACHER, code, NOW + timedelta(days=7), CAPS)
    ).done

    results = await asyncio.gather(
        repo.accept_staff(code, me.id, CAPS, ON), repo.accept_staff(code, me.id, CAPS, ON)
    )

    assert [r is not None and r.created for r in results].count(True) == 1


async def test_an_expired_invite_is_none_and_stays(engine: AsyncEngine) -> None:
    owner, _ = await _person(engine)
    me, _ = await _person(engine)
    shala = await _shala(engine, owner.id)
    repo = SqlShalaRepository(engine)
    code = _code("S")
    assert (
        await repo.invite_staff(shala, owner.id, TEACHER, code, NOW + timedelta(days=7), CAPS)
    ).done
    await _sql(
        engine,
        "UPDATE tristhana.shala_staff_invite SET expires_at = now() - interval '1 second'"
        " WHERE code = :c",
        c=code,
    )

    assert await repo.preview_staff(code, me.id) is None
    assert await repo.accept_staff(code, me.id, CAPS, ON) is None
    assert (await _counts(engine, shala))[1] == 1


async def test_a_demoted_inviters_link_is_dead(engine: AsyncEngine) -> None:
    """Review fix: the SQL guard checks the inviter's rights at preview and accept."""
    owner, _ = await _person(engine)
    manager, _ = await _person(engine)
    me, _ = await _person(engine)
    shala = await _shala(engine, owner.id)
    await _staff(engine, shala, owner.id, manager.id, ADMIN)
    repo = SqlShalaRepository(engine)
    code = _code("S")
    invited = await repo.invite_staff(
        shala, manager.id, TEACHER, code, NOW + timedelta(days=7), CAPS
    )
    assert invited.done
    assert (await repo.set_roles(shala, owner.id, manager.id, frozenset({TEACHER}))).done

    assert await repo.preview_staff(code, me.id) is None
    assert await repo.accept_staff(code, me.id, CAPS, ON) is None
    assert (await _counts(engine, shala))[1:] == (2, 0, 1)  # nobody added, the row stays


async def test_a_student_accepting_staff_loses_the_student_row(engine: AsyncEngine) -> None:
    owner, _ = await _person(engine)
    me, _ = await _person(engine)
    shala = await _shala(engine, owner.id)
    await _student(engine, shala, owner.id, me.id)

    await _staff(engine, shala, owner.id, me.id, ASSISTANT)

    assert await _counts(engine, shala) == (1, 2, 0, 0)


async def test_join_and_staff_accept_racing_stay_exclusive(engine: AsyncEngine) -> None:
    owner, _ = await _person(engine)
    me, _ = await _person(engine)
    shala = await _shala(engine, owner.id)
    repo = SqlShalaRepository(engine)
    link = await repo.join_link(shala, owner.id)
    assert link.value is not None
    code = _code("S")
    assert (
        await repo.invite_staff(shala, owner.id, TEACHER, code, NOW + timedelta(days=7), CAPS)
    ).done

    for _ in range(5):
        await asyncio.gather(
            repo.join(link.value, me.id, CAPS, ON),
            repo.accept_staff(code, me.id, CAPS, ON),
            return_exceptions=True,
        )

    both = (
        await _sql(
            engine,
            "SELECT count(*) FROM tristhana.shala_staff st JOIN tristhana.shala_student su"
            " USING (shala_id, account_id) WHERE st.shala_id = :s",
            s=shala,
        )
    ).scalar_one()
    assert both == 0


# The account load: `Account.shala`, same statement


async def test_no_membership_is_no_shala(engine: AsyncEngine) -> None:
    me, key = await _person(engine)

    assert me.shala is None
    assert (await _find(engine, key)).shala is None


async def test_every_method_returning_an_account_carries_the_same_shala(
    engine: AsyncEngine,
) -> None:
    owner, _ = await _person(engine, "Anna")
    me, key = await _person(engine, "Ash")
    shala = await _shala(engine, owner.id, "moscow", "Moscow Shala")
    await _student(engine, shala, owner.id, me.id)
    repo = SqlAccountRepository(engine)
    expected = ShalaMoon(shala, "Moscow Shala", "moscow", False, False, "moscow")

    returned = [
        await _find(engine, key),
        await repo.update_profile(me.id, ProfileUpdate("Ash", "en"), NOW),
        await repo.update_settings(
            me.id, ProfileChange("Ash", False, "en", False, "Asia/Almaty", frozenset({"name"}))
        ),
        await repo.set_moon_location(me.id, FOLLOW_SHALA),
        await repo.set_timezone_if_unset(me.id, "Europe/Moscow"),
        await repo.set_day_off(me.id, DayOff(frozenset({6}), ON)),
    ]
    await _sql(engine, "UPDATE tristhana.account SET moon_location = NULL WHERE id = :i", i=me.id)
    kept = await repo.set_moon_location_if_unset(me.id, "almaty")
    assert kept is not None
    returned.append(kept)

    assert [a.shala for a in returned] == [expected] * len(returned)


async def test_the_moon_city_column_wins_over_the_city(engine: AsyncEngine) -> None:
    owner, key = await _person(engine, "Anna")
    shala = await _shala(engine, owner.id, "almaty")
    await _sql(engine, "UPDATE tristhana.shala SET moon_city = 'mysuru' WHERE id = :s", s=shala)

    found = await _find(engine, key)

    assert found.shala is not None
    assert (found.shala.moon_city, found.shala.staff) == ("mysuru", True)


async def test_staff_memberships_come_first(engine: AsyncEngine) -> None:
    other, _ = await _person(engine)
    me, key = await _person(engine, "Ash")
    older = await _shala(engine, other.id, "moscow", "Older")
    await _student(engine, older, other.id, me.id)
    mine = await _shala(engine, me.id, "kyiv", "Mine")

    found = await _find(engine, key)

    assert found.shala is not None
    assert (found.shala.id, found.shala.staff) == (mine, True)


async def test_q108_order_and_changes_on_the_next_read_with_no_write(engine: AsyncEngine) -> None:
    """A student in two shalas; the main teacher (Almaty) staffs the newer one. Making another
    teacher main, removing the teacher from staff, unlinking: each changes the next read."""
    anna, _ = await _person(engine, "Anna", "almaty")
    guru, _ = await _person(engine, "Guru", "minsk")
    owner, _ = await _person(engine, "Owner")
    me, key = await _person(engine, "Ash")
    older = await _shala(engine, owner.id, "moscow", "Older")
    newer = await _shala(engine, owner.id, "kyiv", "Newer")
    await _student(engine, older, owner.id, me.id)
    await _student(engine, newer, owner.id, me.id)
    await _staff(engine, newer, owner.id, anna.id, TEACHER)
    await _link(engine, me.id, anna.id)
    links, shalas = SqlTeacherLinkRepository(engine), SqlShalaRepository(engine)

    first = await _find(engine, key)
    assert first.shala == ShalaMoon(newer, "Newer", "kyiv", False, True, "kyiv")
    assert moon_follow_of(first, cities()).source is MoonSource.SHALA

    await _link(engine, me.id, guru.id)
    await links.set_primary(me.id, guru.id)  # Guru isn't on any staff
    second = await _find(engine, key)
    assert second.shala == ShalaMoon(older, "Older", "moscow", False, False, "moscow")
    assert (
        moon_follow_of(second, cities()).city.slug,
        moon_follow_of(second, cities()).source,
    ) == (
        "minsk",
        MoonSource.TEACHER,
    )

    await links.set_primary(me.id, anna.id)
    assert (await _find(engine, key)).shala == ShalaMoon(
        newer, "Newer", "kyiv", False, True, "kyiv"
    )

    assert (await shalas.remove_staff(newer, owner.id, anna.id)).done
    third = await _find(engine, key)
    assert third.shala == ShalaMoon(older, "Older", "moscow", False, False, "moscow")

    await _staff(engine, newer, owner.id, anna.id, TEACHER)
    await links.unlink(me.id, anna.id)
    await links.unlink(me.id, guru.id)
    fourth = await _find(engine, key)
    assert fourth.shala == ShalaMoon(older, "Older", "moscow", False, False, "moscow")
    assert moon_follow_of(fourth, cities()).city.slug == "moscow"


async def test_the_account_load_stays_one_statement(engine: AsyncEngine) -> None:
    owner, _ = await _person(engine)
    me, key = await _person(engine)
    shala = await _shala(engine, owner.id)
    await _student(engine, shala, owner.id, me.id)
    repo = SqlAccountRepository(engine)

    with _statements(engine) as seen:
        await repo.find_by_identity(key)
        await repo.set_moon_location(me.id, FOLLOW_SHALA)

    assert len(seen) == 2


# Statement counts per §7: one repository call, one statement


async def test_every_shala_interaction_is_one_statement(engine: AsyncEngine) -> None:
    owner, _ = await _person(engine, "Anna")
    me, _ = await _person(engine, "Ash")
    staff, _ = await _person(engine, "Boris")
    repo = SqlShalaRepository(engine)
    shala = await _shala(engine, owner.id)
    link = await repo.join_link(shala, owner.id)
    assert link.value is not None
    code = _code("S")
    calls = [
        lambda: repo.mine(owner.id),
        lambda: repo.card(shala, owner.id),
        lambda: repo.member(shala, owner.id, me.id),
        lambda: repo.preview(link.value, me.id),  # type: ignore[arg-type]
        lambda: repo.join(link.value, me.id, CAPS, ON),  # type: ignore[arg-type]
        lambda: repo.students(shala, owner.id, 0, 10),
        lambda: repo.invite_staff(shala, owner.id, TEACHER, code, NOW + timedelta(days=7), CAPS),
        lambda: repo.preview_staff(code, staff.id),
        lambda: repo.accept_staff(code, staff.id, CAPS, ON),
        lambda: repo.set_roles(shala, owner.id, staff.id, frozenset({TEACHER, OFFICE})),
        lambda: repo.rotate_join(shala, owner.id, _code("J")),
        lambda: repo.remove_student(shala, owner.id, me.id),
        lambda: repo.remove_staff(shala, staff.id, staff.id),
    ]

    for call in calls:
        with _statements(engine) as seen:
            await call()
        assert len(seen) == 1, seen


# Policy parity: the SQL guards say what `application/policies.py` says


@pytest.mark.parametrize(
    ("actor_roles", "target_roles", "roles"),
    [
        ((ADMIN,), (TEACHER,), (TEACHER, OFFICE)),
        ((ADMIN,), (TEACHER,), (ADMIN,)),
        ((ADMIN,), (ADMIN,), (TEACHER,)),
        ((TEACHER,), (ASSISTANT,), (TEACHER,)),
        ((OFFICE,), (TEACHER,), ()),
    ],
)
async def test_set_roles_guard_matches_the_policy(
    engine: AsyncEngine,
    actor_roles: tuple[ShalaRole, ...],
    target_roles: tuple[ShalaRole, ...],
    roles: tuple[ShalaRole, ...],
) -> None:
    owner, _ = await _person(engine)
    actor, _ = await _person(engine)
    target, _ = await _person(engine)
    shala = await _shala(engine, owner.id)
    for who, held in ((actor, actor_roles), (target, target_roles)):
        await _staff(engine, shala, owner.id, who.id, held[0])
        await SqlShalaRepository(engine).set_roles(shala, owner.id, who.id, frozenset(held))
    a = Membership(shala, False, frozenset(actor_roles), False)
    t = Membership(shala, False, frozenset(target_roles), False)

    result = await SqlShalaRepository(engine).set_roles(
        shala, actor.id, target.id, frozenset(roles)
    )

    assert result.done is can_set_roles(a, t, frozenset(roles))


@pytest.mark.parametrize(
    ("actor_roles", "target_roles"),
    [
        ((ADMIN,), (TEACHER,)),
        ((ADMIN,), (ADMIN,)),
        ((TEACHER,), (OFFICE,)),
        ((OFFICE,), (TEACHER,)),
    ],
)
async def test_remove_staff_guard_matches_the_policy(
    engine: AsyncEngine, actor_roles: tuple[ShalaRole, ...], target_roles: tuple[ShalaRole, ...]
) -> None:
    owner, _ = await _person(engine)
    actor, _ = await _person(engine)
    target, _ = await _person(engine)
    shala = await _shala(engine, owner.id)
    await _staff(engine, shala, owner.id, actor.id, actor_roles[0])
    await _staff(engine, shala, owner.id, target.id, target_roles[0])
    a = Membership(shala, False, frozenset(actor_roles), False)
    t = Membership(shala, False, frozenset(target_roles), False)

    result = await SqlShalaRepository(engine).remove_staff(shala, actor.id, target.id)

    assert result.done is can_remove_staff(a, t, own=False)
    assert ((await _counts(engine, shala))[1] == 2) is result.done


async def test_the_owner_cannot_leave_in_sql_either(engine: AsyncEngine) -> None:
    owner, _ = await _person(engine)
    shala = await _shala(engine, owner.id)

    result = await SqlShalaRepository(engine).remove_staff(shala, owner.id, owner.id)

    assert result.done is False
    assert (await _counts(engine, shala))[:2] == (1, 1)


async def test_a_non_member_reads_nothing_and_writes_nothing(engine: AsyncEngine) -> None:
    owner, _ = await _person(engine)
    mallory, _ = await _person(engine)
    shala = await _shala(engine, owner.id)
    repo = SqlShalaRepository(engine)

    assert await repo.card(shala, mallory.id) is None
    for result in (
        await repo.students(shala, mallory.id, 0, 10),
        await repo.join_link(shala, mallory.id),
        await repo.rotate_join(shala, mallory.id, _code("J")),
        await repo.delete(shala, mallory.id),
        await repo.remove_staff(shala, mallory.id, owner.id),
    ):
        assert (result.me, result.done) == (None, False)
    assert await _counts(engine, shala) == (1, 1, 0, 0)


# The tick


async def test_the_tick_candidates_match_the_domain_for_a_q108_mix(engine: AsyncEngine) -> None:
    owner, _ = await _person(engine, "Owner")
    anna, anna_key = await _person(engine, "Anna", "almaty")  # staffs Moscow
    boris, boris_key = await _person(engine, "Boris", "almaty")  # on no staff
    moscow = await _shala(engine, owner.id, "moscow", "Moscow")
    kyiv = await _shala(engine, owner.id, "kyiv", "Kyiv")
    await _staff(engine, moscow, owner.id, anna.id, TEACHER)
    people = [await _person(engine, n) for n in ("A", "B", "C", "D", "E")]
    (a, _), (b, _), (c, _), (d, _), (e, _) = people
    await _student(engine, moscow, owner.id, a.id)
    await _link(engine, a.id, anna.id)  # Q108: Moscow
    await _student(engine, moscow, owner.id, b.id)
    await _link(engine, b.id, boris.id)  # not on staff: Boris's Almaty
    await _student(engine, kyiv, owner.id, c.id)
    await _link(engine, c.id, anna.id)  # Anna staffs another shala: Almaty
    await _student(engine, kyiv, owner.id, d.id)  # no teacher: Kyiv
    await _student(engine, kyiv, owner.id, e.id)
    await _student(engine, moscow, owner.id, e.id)
    await _link(engine, e.id, anna.id)  # two shalas, the teacher on the newer one: Moscow
    expected = {
        a.id: "moscow",
        b.id: "almaty",
        c.id: "almaty",
        d.id: "kyiv",
        e.id: "moscow",
        anna.id: "almaty",  # she chose
        boris.id: "almaty",
        owner.id: "moscow",  # staff of both, the older first
    }
    found = {
        cand.account_id: cand
        for cand in await SqlNotificationRepository(engine).candidates(
            NOW - timedelta(days=12), NOW.date(), DEFAULTS
        )
    }

    for account_id, slug in expected.items():
        cand = found[account_id]
        rule = moon_follow(cand.location, cand.teaches, cand.teacher, cand.shala, cities())
        assert rule.city.slug == slug, account_id
    for account, key in [(anna, anna_key), (boris, boris_key), *people]:
        loaded = moon_follow_of(await _find(engine, key), cities())
        assert loaded.city.slug == expected[account.id]


async def test_the_tick_candidates_keep_their_statements(engine: AsyncEngine) -> None:
    owner, _ = await _person(engine)
    shala = await _shala(engine, owner.id)
    for _ in range(3):
        student, _ = await _person(engine)
        await _student(engine, shala, owner.id, student.id)
    repo = SqlNotificationRepository(engine)

    with _statements(engine) as seen:
        await repo.candidates(NOW - timedelta(days=12), NOW.date(), DEFAULTS)

    assert len(seen) == 3


async def test_pruning_deletes_only_expired_staff_invites(engine: AsyncEngine) -> None:
    """The tick's pruning step calls `prune_invites` (spec §6)."""
    owner, _ = await _person(engine)
    shala = await _shala(engine, owner.id)
    repo = SqlShalaRepository(engine)
    live, dead = _code("S"), _code("S")
    for code in (live, dead):
        assert (
            await repo.invite_staff(shala, owner.id, TEACHER, code, NOW + timedelta(days=7), CAPS)
        ).done
    await _sql(
        engine,
        "UPDATE tristhana.shala_staff_invite SET expires_at = now() - interval '1 day'"
        " WHERE code = :c",
        c=dead,
    )

    assert await repo.prune_invites(datetime.now(UTC)) == 1

    codes = (await _sql(engine, "SELECT code FROM tristhana.shala_staff_invite")).scalars().all()
    assert codes == [live]


# The plan on 1000 students


async def test_the_account_load_uses_the_membership_indexes(engine: AsyncEngine) -> None:
    owner, _ = await _person(engine)
    shala = await _shala(engine, owner.id)
    await _sql(
        engine,
        "INSERT INTO tristhana.account (display_name, locale)"
        " SELECT 'p' || g, 'en' FROM generate_series(1, 1000) g",
    )
    await _sql(
        engine,
        "INSERT INTO tristhana.shala_student (shala_id, account_id, joined_on)"
        " SELECT :s, id, DATE '2026-11-01' FROM tristhana.account WHERE id <> :o",
        s=shala,
        o=owner.id,
    )
    await _sql(engine, "ANALYZE tristhana.shala_student")
    await _sql(engine, "ANALYZE tristhana.shala_staff")
    student = (
        await _sql(engine, "SELECT account_id FROM tristhana.shala_student LIMIT 1")
    ).scalar_one()
    await _sql(
        engine,
        "INSERT INTO tristhana.identity (provider, provider_user_id, account_id)"
        " VALUES ('telegram', 'plan-shala', :s)",
        s=student,
    )
    loads: list[tuple[str, Any]] = []

    def record(_conn: object, _cursor: object, statement: str, params: Any, *_: object) -> None:
        loads.append((statement, params))

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        found = await SqlAccountRepository(engine).find_by_identity(_key("plan-shala"))
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)
    assert found is not None
    assert found.shala is not None
    [(statement, params)] = loads
    async with engine.connect() as conn:
        await conn.exec_driver_sql("SET enable_seqscan = off")
        plan = "\n".join(
            str(row[0]) for row in await conn.exec_driver_sql("EXPLAIN " + statement, params)
        )
    assert "Seq Scan on shala_student" not in plan, plan
    assert "Seq Scan on shala_staff" not in plan, plan


# Migration 0021


async def test_0021_up_down_up_and_no_drift(migrated_url: str, engine: AsyncEngine) -> None:
    tables = text(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'tristhana'"
        " AND table_name IN ('shala', 'shala_staff', 'shala_student', 'shala_staff_invite')"
    )
    await asyncio.to_thread(migrate.downgrade, migrated_url, "0020")
    try:
        async with engine.connect() as conn:
            assert (await conn.execute(tables)).scalar_one() == 0
    finally:
        await asyncio.to_thread(migrate.upgrade, migrated_url)
    async with engine.connect() as conn:
        assert (await conn.execute(tables)).scalar_one() == 4
    await asyncio.to_thread(migrate.check, migrated_url)


# The app role


async def test_shala_writes_work_as_the_app_role(migrated_url: str, engine: AsyncEngine) -> None:
    """The four tables take their grants from the schema defaults (0001)."""
    async with engine.connect() as conn:
        missing = await conn.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE n.nspname = 'tristhana' AND c.relname LIKE 'shala%' AND c.relkind = 'r'"
                " AND EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tristhana_app')"
                " AND NOT has_table_privilege('tristhana_app', c.oid,"
                " 'SELECT, INSERT, UPDATE, DELETE')"
            )
        )
        assert missing.scalars().all() == []


# Export: my memberships, no other person's name or id, no code


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


@pytest.mark.parametrize("side", ["owner", "staff", "student"])
async def test_the_export_holds_my_memberships_only(engine: AsyncEngine, side: str) -> None:
    shala, owner, staff, student = await _populated(engine)
    who = {"owner": owner, "staff": staff, "student": student}[side]
    others = [p for p in (owner, staff, student) if p.id != who.id]
    codes = (
        (
            await _sql(
                engine,
                "SELECT join_code FROM tristhana.shala WHERE id = :s"
                " UNION ALL SELECT code FROM tristhana.shala_staff_invite WHERE shala_id = :s",
                s=shala,
            )
        )
        .scalars()
        .all()
    )

    data, everything = await _export(engine, who)

    [row] = data["shalas"]
    assert set(row) == {
        "name",
        "city",
        "moon_city",
        "online",
        "side",
        "owner",
        "roles",
        "joined_on",
        "announcements_muted",  # NT-03
    }
    assert (row["name"], row["side"], row["owner"]) == (
        "Ashtanga Almaty",
        "student" if side == "student" else "staff",
        side == "owner",
    )
    for other in others:
        assert str(other.id) not in everything
        assert str(other.display_name) not in everything
    for code in codes:
        assert code not in everything
    assert str(shala) not in everything


# The card's staff list stays inside its own shala (privacy, ADR-0033)


async def test_a_card_lists_only_its_own_staff_oldest_first(engine: AsyncEngine) -> None:
    anna, _ = await _person(engine, "Anna")
    boris, _ = await _person(engine, "Boris")
    vera, _ = await _person(engine, "Vera")
    first = await _shala(engine, anna.id, name="First")
    second = await _shala(engine, boris.id, name="Second")
    await _staff(engine, second, boris.id, vera.id, ASSISTANT)
    repo = SqlShalaRepository(engine)

    one = await repo.card(first, anna.id)
    two = await repo.card(second, boris.id)

    assert one is not None
    assert two is not None
    assert [(s.id, s.name, s.owner, s.roles) for s in one.staff] == [
        (anna.id, "Anna", True, frozenset({TEACHER}))
    ]
    assert [(s.id, s.name, s.owner, s.roles) for s in two.staff] == [
        (boris.id, "Boris", True, frozenset({TEACHER})),
        (vera.id, "Vera", False, frozenset({ASSISTANT})),
    ]


async def test_the_staff_order_is_by_joining_time_not_by_row_order(engine: AsyncEngine) -> None:
    anna, _ = await _person(engine, "Anna")
    vera, _ = await _person(engine, "Vera")
    gleb, _ = await _person(engine, "Gleb")
    shala = await _shala(engine, anna.id)
    await _staff(engine, shala, anna.id, vera.id, ASSISTANT)
    await _staff(engine, shala, anna.id, gleb.id, OFFICE)
    await _sql(
        engine,
        "UPDATE tristhana.shala_staff SET created_at = created_at - interval '1 day'"
        " WHERE account_id = :who",
        who=gleb.id,
    )

    card = await SqlShalaRepository(engine).card(shala, anna.id)

    assert card is not None
    assert [s.name for s in card.staff] == ["Gleb", "Anna", "Vera"]


async def test_an_updated_card_lists_only_its_own_staff(engine: AsyncEngine) -> None:
    anna, _ = await _person(engine, "Anna")
    boris, _ = await _person(engine, "Boris")
    first = await _shala(engine, anna.id, name="First")
    await _shala(engine, boris.id, name="Second")

    changed = await SqlShalaRepository(engine).update(first, anna.id, ShalaPatch(name="Renamed"))

    assert changed.value is not None
    assert [s.name for s in changed.value.staff] == ["Anna"]


async def test_a_new_account_starts_with_no_one_elses_teacher_or_shala(
    engine: AsyncEngine,
) -> None:
    anna, _ = await _person(engine, "Anna")
    sam, _ = await _person(engine, "Sam")
    await _shala(engine, anna.id)
    await _link(engine, sam.id, anna.id)

    fresh, key = await _person(engine, "Fresh")
    loaded = await _find(engine, key)

    assert (fresh.teaches, fresh.main_teacher, fresh.shala) == (False, None, None)
    assert (loaded.teaches, loaded.main_teacher, loaded.shala) == (False, None, None)
