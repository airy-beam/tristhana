"""`TeacherLinkRepository` on real Postgres (ID-04, spec §3, §8, §10): one statement per call
(two for `set_primary`), the races (two accepts, two flips, a delete mid-tap), the cascades, the
constraints, the ordering MD-02 will copy, migration 0019 and the export of both directions.

Races are forced rather than hoped for: `_holding` keeps a transaction open on a second
connection, and the call under test is released only once Postgres shows it waiting."""

import asyncio
import base64
import itertools
import json
from collections.abc import AsyncGenerator, Awaitable, Generator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from tests.domain.test_practice import catalog
from tests.fakes import FakeNotifier, FakePacker, FixedClock, cities
from tristhana.application.export import SendMyExport
from tristhana.application.labels import PracticeLabels
from tristhana.application.policies import Principal
from tristhana.application.ports.export import AccountGone
from tristhana.application.ports.teacher_links import Caps, LinksChanged
from tristhana.domain.accounts import (
    Account,
    IdentityKey,
    IdentityProvider,
    NewAccount,
)
from tristhana.domain.moon import TeacherMoon
from tristhana.domain.notifications import DEFAULTS
from tristhana.domain.progression import Track
from tristhana.domain.teacher_links import MAX_STUDENTS, MAX_TEACHERS, effective_primary
from tristhana.infrastructure.crypto import FieldCipher
from tristhana.infrastructure.db import migrate
from tristhana.infrastructure.db.accounts import SqlAccountRepository
from tristhana.infrastructure.db.export import SqlExportRepository
from tristhana.infrastructure.db.teacher_links import SqlTeacherLinkRepository
from tristhana.infrastructure.i18n.fluent import FluentTranslator

pytestmark = pytest.mark.db

KEYS = "1:" + base64.b64encode(b"\x07" * 32).decode()
ON = date(2026, 11, 7)
NOW = datetime(2026, 11, 7, 12, 0, tzinfo=UTC)
CAPS = Caps(teachers=MAX_TEACHERS, students=MAX_STUDENTS)
CODE = "aB3dE6gH9jK2mN5p"
OTHER_CODE = "Zy8xW7vU6tS5rQ4p"
_users = itertools.count(40_000)
_codes = itertools.count(1)


def _code() -> str:
    return f"code{next(_codes):012d}"


async def _person(engine: AsyncEngine, name: str | None = "Person", locale: str = "en") -> Account:
    return await SqlAccountRepository(engine).create_with_identity(
        IdentityKey(IdentityProvider.TELEGRAM, str(next(_users))),
        NewAccount(display_name=name, locale=locale),  # type: ignore[arg-type]
    )


async def _account(engine: AsyncEngine) -> UUID:
    return (await _person(engine)).id


async def _accounts(engine: AsyncEngine, n: int) -> list[UUID]:
    return [await _account(engine) for _ in range(n)]


async def _link(repo: SqlTeacherLinkRepository, student: UUID, teacher: UUID) -> None:
    accepted = await repo.accept(await repo.invite(teacher, _code()), student, CAPS, ON)
    assert accepted is not None
    assert accepted.created


async def _main(repo: SqlTeacherLinkRepository, student: UUID) -> UUID | None:
    return effective_primary((await repo.overview(student)).teachers)


async def _flagged(engine: AsyncEngine, student: UUID) -> list[UUID]:
    async with engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT teacher_id FROM tristhana.teacher_link WHERE student_id = :s AND is_primary"
            ),
            {"s": student},
        )
        return list(rows.scalars())


async def _rows(engine: AsyncEngine, table: str) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text(f"SELECT count(*) FROM tristhana.{table}"))).scalar_one()  # noqa: S608


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


# One statement per call (spec §3, §9)


async def test_each_call_is_one_statement(engine: AsyncEngine) -> None:
    repo = SqlTeacherLinkRepository(engine)
    teacher, student = await _account(engine), await _account(engine)

    with _statements(engine) as seen:
        code = await repo.invite(teacher, CODE)
    assert len(seen) == 1

    with _statements(engine) as seen:
        preview = await repo.preview(code, student)
    assert len(seen) == 1
    assert preview is not None

    with _statements(engine) as seen:
        accepted = await repo.accept(code, student, CAPS, ON)
    assert len(seen) == 1
    assert accepted is not None

    with _statements(engine) as seen:
        await repo.overview(student)
    assert len(seen) == 1

    with _statements(engine) as seen:
        await repo.rotate(teacher, OTHER_CODE)
    assert len(seen) == 1

    with _statements(engine) as seen:
        assert (await repo.unlink(student, teacher)).removed
    assert len(seen) == 1


async def test_set_primary_is_two_updates_clear_then_set(engine: AsyncEngine) -> None:
    repo = SqlTeacherLinkRepository(engine)
    teacher, student = await _account(engine), await _account(engine)
    await _link(repo, student, teacher)

    with _statements(engine) as seen:
        assert await repo.set_primary(student, teacher)

    assert len(seen) == 2
    assert all(s.lstrip().upper().startswith("UPDATE") for s in seen)
    assert "teacher_id" not in seen[0].split("WHERE")[1]  # clear: the whole student
    assert "teacher_id" in seen[1].split("WHERE")[1]  # set: the one row


async def test_preview_gives_the_name_the_counts_and_never_writes(engine: AsyncEngine) -> None:
    repo = SqlTeacherLinkRepository(engine)
    teacher = await _person(engine, "Лена")
    student, other = await _account(engine), await _account(engine)
    await _link(repo, other, teacher.id)
    code = await repo.invite(teacher.id, CODE)

    preview = await repo.preview(code, student)

    assert preview is not None
    assert (preview.teacher_id, preview.teacher_name) == (teacher.id, "Лена")
    assert (preview.already, preview.my_teachers, preview.their_students) == (False, 0, 1)
    assert await repo.preview("unknownCode00000", student) is None
    assert await _rows(engine, "teacher_link") == 1


async def test_accept_returns_all_the_note_needs(engine: AsyncEngine) -> None:
    repo = SqlTeacherLinkRepository(engine)
    teacher = await _person(engine, "Лена", "ru")
    student = await _account(engine)
    code = await repo.invite(teacher.id, CODE)

    accepted = await repo.accept(code, student, CAPS, ON)
    again = await repo.accept(code, student, CAPS, ON)

    assert accepted is not None
    assert (accepted.created, accepted.already, accepted.my_teachers) == (True, False, 1)
    assert (accepted.teacher_id, accepted.teacher_name) == (teacher.id, "Лена")
    assert accepted.teacher_locale == "ru"
    assert accepted.teacher_telegram_id is not None
    assert accepted.teacher_telegram_id.isdigit()
    assert again is not None
    assert (again.created, again.already, again.my_teachers) == (False, True, 1)
    async with engine.connect() as conn:
        stored = await conn.execute(text("SELECT linked_on FROM tristhana.teacher_link"))
        assert stored.scalar_one() == ON


async def test_accept_is_gated_on_both_caps_and_on_self(engine: AsyncEngine) -> None:
    repo = SqlTeacherLinkRepository(engine)
    teacher, student, late = await _accounts(engine, 3)
    code = await repo.invite(teacher, CODE)
    await _link(repo, await _account(engine), teacher)

    own = await repo.accept(code, teacher, CAPS, ON)
    theirs_full = await repo.accept(code, student, Caps(teachers=20, students=1), ON)
    await _link(repo, late, await _account(engine))
    mine_full = await repo.accept(code, late, Caps(teachers=1, students=500), ON)

    for refused in (own, theirs_full, mine_full):
        assert refused is not None
        assert (refused.created, refused.already) == (False, False)
    assert await _rows(engine, "teacher_link") == 2


async def test_two_accepts_at_once_make_one_row_and_one_created(engine: AsyncEngine) -> None:
    repo = SqlTeacherLinkRepository(engine)
    teacher, student = await _account(engine), await _account(engine)
    code = await repo.invite(teacher, CODE)

    first, second = await asyncio.gather(
        repo.accept(code, student, CAPS, ON), repo.accept(code, student, CAPS, ON)
    )

    assert first is not None
    assert second is not None
    assert sorted([first.created, second.created]) == [False, True]
    loser = second if first.created else first
    assert not loser.full  # the bot says "already on your list", never "this link can't add"
    assert await _rows(engine, "teacher_link") == 1


async def test_two_invites_at_once_agree_on_one_code(engine: AsyncEngine) -> None:
    repo = SqlTeacherLinkRepository(engine)
    me = await _account(engine)

    first, second = await asyncio.gather(repo.invite(me, CODE), repo.invite(me, OTHER_CODE))

    assert first == second
    assert await repo.invite(me, _code()) == first  # and it's kept
    assert await _rows(engine, "teacher_invite") == 1


async def test_rotating_resets_the_date_and_kills_the_old_code(engine: AsyncEngine) -> None:
    repo = SqlTeacherLinkRepository(engine)
    teacher, student = await _account(engine), await _account(engine)
    old = await repo.invite(teacher, CODE)
    async with engine.connect() as conn:
        await conn.execute(
            text("UPDATE tristhana.teacher_invite SET created_at = '2020-01-01T00:00:00Z'")
        )

    fresh = await repo.rotate(teacher, OTHER_CODE)

    assert fresh == OTHER_CODE
    assert await repo.preview(old, student) is None
    assert await repo.preview(fresh, student) is not None
    async with engine.connect() as conn:
        created = await conn.execute(text("SELECT created_at FROM tristhana.teacher_invite"))
        assert created.scalar_one().year > 2020


async def test_two_flips_at_once_flag_at_most_one(engine: AsyncEngine) -> None:
    repo = SqlTeacherLinkRepository(engine)
    student = await _account(engine)
    first, second = await _account(engine), await _account(engine)
    await _link(repo, student, first)
    await _link(repo, student, second)

    results = await asyncio.gather(
        repo.set_primary(student, first),
        repo.set_primary(student, second),
        return_exceptions=True,
    )

    assert all(isinstance(r, TeacherMoon | LinksChanged) for r in results), results
    assert len(await _flagged(engine, student)) == 1


async def test_the_loser_of_a_flip_gets_links_changed(engine: AsyncEngine) -> None:
    """Nothing flagged yet: the second writer waits on the unique index, then gets 23505."""
    repo = SqlTeacherLinkRepository(engine)
    student = await _account(engine)
    winner, loser = await _account(engine), await _account(engine)
    await _link(repo, student, winner)
    await _link(repo, student, loser)

    async with _holding(engine) as other:
        await other.execute(
            text(
                "UPDATE tristhana.teacher_link SET is_primary = true"
                " WHERE student_id = :s AND teacher_id = :t"
            ),
            {"s": student, "t": winner},
        )
        flip = await _blocked(engine, repo.set_primary(student, loser))
        await other.execute(text("COMMIT"))

        with pytest.raises(LinksChanged):
            await flip

    assert await _flagged(engine, student) == [winner]


async def test_the_loser_of_a_flip_over_a_chosen_main_gets_links_changed(
    engine: AsyncEngine,
) -> None:
    """A main is flagged: the second writer waits on that row, its clear then finds nothing,
    and its set hits the winner's committed flag."""
    repo = SqlTeacherLinkRepository(engine)
    student = await _account(engine)
    old, winner, loser = await _accounts(engine, 3)
    for teacher in (old, winner, loser):
        await _link(repo, student, teacher)
    assert await repo.set_primary(student, old)

    async with _holding(engine) as other:
        await other.execute(
            text("UPDATE tristhana.teacher_link SET is_primary = false WHERE student_id = :s"),
            {"s": student},
        )
        await other.execute(
            text(
                "UPDATE tristhana.teacher_link SET is_primary = true"
                " WHERE student_id = :s AND teacher_id = :t"
            ),
            {"s": student, "t": winner},
        )
        flip = await _blocked(engine, repo.set_primary(student, loser))
        await other.execute(text("COMMIT"))

        with pytest.raises(LinksChanged):
            await flip

    assert await _flagged(engine, student) == [winner]


@pytest.mark.parametrize("flip_to", [0, 1])
async def test_a_flip_works_whichever_row_comes_first(engine: AsyncEngine, flip_to: int) -> None:
    """A one-statement flip fails or not depending on the physical row order; clear-then-set
    must not care. The later row's flag moves to the earlier one, and the other way round."""
    repo = SqlTeacherLinkRepository(engine)
    student = await _account(engine)
    teachers = [await _account(engine), await _account(engine)]
    for teacher in teachers:
        await _link(repo, student, teacher)
    target, other = teachers[flip_to], teachers[1 - flip_to]

    assert await repo.set_primary(student, other)
    assert await repo.set_primary(student, target)
    assert await repo.set_primary(student, target)  # the same choice again is fine

    assert await _flagged(engine, student) == [target]
    assert await _main(repo, student) == target


async def test_set_primary_on_a_stranger_rolls_back_and_keeps_the_main(
    engine: AsyncEngine,
) -> None:
    repo = SqlTeacherLinkRepository(engine)
    student, chosen = await _account(engine), await _account(engine)
    oldest, stranger = await _account(engine), await _account(engine)
    await _link(repo, student, oldest)
    await _link(repo, student, chosen)
    assert await repo.set_primary(student, chosen)

    assert await repo.set_primary(student, stranger) is None

    assert await _flagged(engine, student) == [chosen]


async def test_unlink_is_idempotent_and_keyed_on_the_pair(engine: AsyncEngine) -> None:
    repo = SqlTeacherLinkRepository(engine)
    teacher, student, other = await _accounts(engine, 3)
    await _link(repo, student, teacher)
    await _link(repo, other, teacher)

    assert (await repo.unlink(student, teacher)).removed is True
    assert (await repo.unlink(student, teacher)).removed is False

    assert [s.id for s in (await repo.overview(teacher)).students] == [other]


async def test_a_student_row_never_says_whether_they_chose_this_teacher(
    engine: AsyncEngine,
) -> None:
    repo = SqlTeacherLinkRepository(engine)
    teacher = await _person(engine, "Лена")
    student = await _person(engine, "Ash")
    await _link(repo, student.id, teacher.id)
    assert await repo.set_primary(student.id, teacher.id)

    links = await repo.overview(teacher.id)

    assert [(s.id, s.name, s.chosen_primary) for s in links.students] == [
        (student.id, "Ash", False)
    ]
    assert links.teachers == ()


async def test_deleting_a_teacher_cascades_and_moves_the_main(engine: AsyncEngine) -> None:
    repo = SqlTeacherLinkRepository(engine)
    accounts = SqlAccountRepository(engine)
    student, other_student = await _account(engine), await _account(engine)
    next_oldest, leaving = await _account(engine), await _account(engine)
    await _link(repo, student, next_oldest)
    await _link(repo, student, leaving)
    await _link(repo, other_student, next_oldest)
    code = await repo.invite(leaving, _code())  # the one `_link` made
    assert await repo.set_primary(student, leaving)

    assert await accounts.delete(leaving)

    assert await _main(repo, student) == next_oldest
    assert await _flagged(engine, student) == []  # no promotion write: read-time default
    assert [t.id for t in (await repo.overview(other_student)).teachers] == [next_oldest]
    assert await repo.preview(code, student) is None
    assert await _rows(engine, "teacher_invite") == 1  # next_oldest's


async def test_deleting_a_student_cascades_and_leaves_the_rest(engine: AsyncEngine) -> None:
    repo = SqlTeacherLinkRepository(engine)
    accounts = SqlAccountRepository(engine)
    teacher, leaving, staying = await _accounts(engine, 3)
    await _link(repo, leaving, teacher)
    await _link(repo, staying, teacher)

    assert await accounts.delete(leaving)

    assert [s.id for s in (await repo.overview(teacher)).students] == [staying]
    assert await _rows(engine, "teacher_link") == 1


async def test_a_student_deleted_mid_tap_is_account_gone(engine: AsyncEngine) -> None:
    repo = SqlTeacherLinkRepository(engine)
    teacher, student = await _account(engine), await _account(engine)
    code = await repo.invite(teacher, CODE)

    async with _holding(engine) as other:
        await other.execute(text("DELETE FROM tristhana.account WHERE id = :a"), {"a": student})
        tap = await _blocked(engine, repo.accept(code, student, CAPS, ON))
        await other.execute(text("COMMIT"))

        with pytest.raises(AccountGone):
            await tap

    assert await _rows(engine, "teacher_link") == 0


async def test_a_teacher_deleted_mid_tap_is_an_invalid_invite(engine: AsyncEngine) -> None:
    """23503 on `teacher_link_teacher_id_fkey`: `accept` returns None, the bot says
    `invite-invalid`."""
    repo = SqlTeacherLinkRepository(engine)
    teacher, student = await _account(engine), await _account(engine)
    code = await repo.invite(teacher, CODE)

    async with _holding(engine) as other:
        await other.execute(text("DELETE FROM tristhana.account WHERE id = :a"), {"a": teacher})
        tap = await _blocked(engine, repo.accept(code, student, CAPS, ON))
        await other.execute(text("COMMIT"))

        assert await tap is None

    assert await _rows(engine, "teacher_link") == 0


async def test_a_deleted_student_gets_account_gone_without_a_race(engine: AsyncEngine) -> None:
    repo = SqlTeacherLinkRepository(engine)
    teacher, gone = await _account(engine), await _account(engine)
    code = await repo.invite(teacher, CODE)
    await SqlAccountRepository(engine).delete(gone)

    with pytest.raises(AccountGone):
        await repo.accept(code, gone, CAPS, ON)


async def test_constraints(engine: AsyncEngine) -> None:
    student, first, second = await _accounts(engine, 3)
    insert = text(
        "INSERT INTO tristhana.teacher_link (student_id, teacher_id, is_primary, linked_on)"
        " VALUES (:s, :t, :p, :on)"
    )
    async with engine.connect() as conn:
        with pytest.raises(IntegrityError, match="teacher_link"):
            await conn.execute(insert, {"s": student, "t": student, "p": False, "on": ON})
        await conn.execute(insert, {"s": student, "t": first, "p": True, "on": ON})
        with pytest.raises(IntegrityError, match="teacher_link_one_primary"):
            await conn.execute(insert, {"s": student, "t": second, "p": True, "on": ON})
        await conn.execute(insert, {"s": student, "t": second, "p": False, "on": ON})  # unflagged
        with pytest.raises(IntegrityError):  # the pair is the key
            await conn.execute(insert, {"s": student, "t": first, "p": False, "on": ON})


@pytest.mark.parametrize(
    "code",
    ["short", "aB3dE6gH9jK2mN5pX", "aB3dE6gH9jK2mN5-", "абвгдежзийклмноп", "aB3dE6gH9jK2mN5\n"],
)
async def test_the_code_check_refuses_anything_but_16_alphanumerics(
    engine: AsyncEngine, code: str
) -> None:
    me = await _account(engine)

    async with engine.connect() as conn:
        with pytest.raises(IntegrityError):
            await conn.execute(
                text("INSERT INTO tristhana.teacher_invite (account_id, code) VALUES (:a, :c)"),
                {"a": me, "c": code},
            )


async def test_one_code_cant_be_two_peoples(engine: AsyncEngine) -> None:
    repo = SqlTeacherLinkRepository(engine)
    await repo.invite(await _account(engine), CODE)
    other = await _account(engine)

    async with engine.connect() as conn:
        with pytest.raises(IntegrityError):
            await conn.execute(
                text("INSERT INTO tristhana.teacher_invite (account_id, code) VALUES (:a, :c)"),
                {"a": other, "c": CODE},
            )


async def test_the_sql_ordering_matches_effective_primary(engine: AsyncEngine) -> None:
    """The query MD-02 will use for the tick (spec §11) and the domain rule give one answer,
    down to a tie on `created_at`, where uuid order must agree with Python's."""
    repo = SqlTeacherLinkRepository(engine)
    student = await _account(engine)
    teachers = [await _account(engine) for _ in range(4)]
    for teacher in teachers:
        await _link(repo, student, teacher)
    batch = text(
        "SELECT DISTINCT ON (student_id) teacher_id FROM tristhana.teacher_link"
        " WHERE student_id = :s ORDER BY student_id, is_primary DESC, created_at, teacher_id"
    )
    async with engine.connect() as conn:
        await conn.execute(
            text("UPDATE tristhana.teacher_link SET created_at = :at WHERE student_id = :s"),
            {"at": NOW, "s": student},
        )

    async def from_sql() -> UUID:
        async with engine.connect() as conn:
            return (await conn.execute(batch, {"s": student})).scalar_one()

    assert await from_sql() == await _main(repo, student) == min(teachers)

    assert await repo.set_primary(student, max(teachers))
    assert await from_sql() == await _main(repo, student) == max(teachers)


async def test_0019_down_up_and_no_drift(migrated_url: str, engine: AsyncEngine) -> None:
    has_tables = (
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'tristhana'"
        " AND table_name IN ('teacher_link', 'teacher_invite')"
    )

    await asyncio.to_thread(migrate.downgrade, migrated_url, "0018")
    async with engine.connect() as conn:
        assert (await conn.execute(text(has_tables))).scalar_one() == 0
    await asyncio.to_thread(migrate.upgrade, migrated_url)
    async with engine.connect() as conn:
        assert (await conn.execute(text(has_tables))).scalar_one() == 2
    await asyncio.to_thread(migrate.check, migrated_url)


# Export (ST-09, Q14): both directions, and no trace of the other person.


async def _export(engine: AsyncEngine, who: Account) -> tuple[dict[str, Any], str]:
    packer = FakePacker()
    t = FluentTranslator()
    repo = SqlExportRepository(engine, FieldCipher(KEYS))
    use_case = SendMyExport(
        repo,
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


async def _both_directions(engine: AsyncEngine) -> tuple[Account, Account, Account]:
    """`me` has a teacher and a student; both have names no export should print."""
    repo = SqlTeacherLinkRepository(engine)
    me = await _person(engine, "Ash")
    teacher, student = await _person(engine, "Лена"), await _person(engine, "Boris")
    await repo.invite(teacher.id, CODE)
    await repo.invite(me.id, OTHER_CODE)
    assert await repo.accept(CODE, me.id, CAPS, ON) is not None
    assert await repo.accept(OTHER_CODE, student.id, CAPS, ON) is not None
    return me, teacher, student


async def test_the_export_has_both_directions(engine: AsyncEngine) -> None:
    me, _, _ = await _both_directions(engine)

    data, _ = await _export(engine, me)

    links = sorted(data["teacher_links"], key=lambda link: link["other_side"])
    assert data["schema"] == "tristhana.export/1"  # additive, as GM-01
    assert [(link["other_side"], link["primary"]) for link in links] == [
        ("student", None),  # a teacher's own rows never say whether they're main
        ("teacher", True),  # the effective main, with nothing flagged
    ]
    assert all(
        set(link) == {"other_side", "primary", "linked_at", "announcements_muted"} for link in links
    )
    assert all(link["linked_at"].endswith("Z") for link in links)


async def test_the_export_marks_only_the_effective_main_teacher(engine: AsyncEngine) -> None:
    repo = SqlTeacherLinkRepository(engine)
    me = await _person(engine, "Ash")
    first, second = await _account(engine), await _account(engine)
    await _link(repo, me.id, first)
    await _link(repo, me.id, second)
    assert await repo.set_primary(me.id, second)

    data, _ = await _export(engine, me)

    assert sorted(link["primary"] for link in data["teacher_links"]) == [False, True]


@pytest.mark.parametrize("who", [0, 1, 2], ids=["both", "the-teacher", "the-student"])
async def test_no_export_names_the_other_person(engine: AsyncEngine, who: int) -> None:
    people = await _both_directions(engine)
    me = people[who]
    others = [p for p in people if p.id != me.id]

    _, everything = await _export(engine, me)

    for other in others:
        assert other.display_name is not None
        assert str(other.id) not in everything
        assert other.display_name not in everything


async def test_no_export_holds_a_code(engine: AsyncEngine) -> None:
    people = await _both_directions(engine)

    for person in people:
        _, everything = await _export(engine, person)

        assert CODE not in everything
        assert OTHER_CODE not in everything


async def test_the_links_cost_the_snapshot_one_statement(engine: AsyncEngine) -> None:
    me, _, _ = await _both_directions(engine)
    repo = SqlExportRepository(engine, FieldCipher(KEYS))

    with _statements(engine) as seen:
        owned = await repo.snapshot(me.id, DEFAULTS, ON)

    assert owned is not None
    # The account load also reads `teacher_link` for MD-02's inputs; the links are one more.
    assert len([s for s in seen if "teacher_link" in s and "main_teacher" not in s]) == 1
    assert not [s for s in seen if "teacher_invite" in s]


async def test_the_readme_explains_the_links(engine: AsyncEngine) -> None:
    me, _, _ = await _both_directions(engine)

    _, everything = await _export(engine, me)

    assert "your teachers and students, without names" in everything
