"""Migration 0029 `teacher_request` (ID-07 spec §6; ADR-0046), without a database: the
revision, the columns, the key, the three cascades, the indexes, the wider delivery category, the
export coverage, the storage wiring and `is_account_gone`. CHECKs, up/down and
`alembic check` run on Postgres in `test_db_teacher_requests.py`."""

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.exc import DBAPIError

from tests.fakes import NOW
from tristhana.application.ports.storage import StorageUnavailable
from tristhana.domain.teacher_requests import RequestState
from tristhana.infrastructure.db import tables
from tristhana.infrastructure.db.engine import is_account_gone
from tristhana.infrastructure.db.export import EXCLUDED_TABLES, EXPORTED_TABLES
from tristhana.infrastructure.db.migrate import alembic_config
from tristhana.infrastructure.db.storage import UnconfiguredStorage


def _table() -> Any:
    return tables.metadata.tables["tristhana.teacher_request"]


def _checks(table: Any) -> list[str]:
    return [str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)]


def test_0029_follows_0028() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql://unused"))
    revision = script.get_revision("0029")
    assert revision is not None  # the head is checked by the newest migration's test
    assert revision.down_revision == "0028"


def test_the_columns_and_the_pair_as_the_key() -> None:
    t = _table()

    assert set(t.c.keys()) == {
        "id", "student_id", "teacher_id", "shala_id", "state", "asked_on",
        "quiet_note_agreed", "created_at",
    }  # fmt: skip
    assert [c.name for c in t.primary_key.columns] == ["student_id", "teacher_id"]
    assert {c.name for c in t.columns if c.nullable} == set()
    assert t.c.id.server_default is not None  # the ledger's key, made by the database
    assert t.c.state.server_default is not None
    assert t.c.created_at.server_default is not None  # the database's clock
    assert t.c.created_at.type.timezone is True
    # The consent of the tapped screen is always stated, never defaulted (ADR-0031).
    assert t.c.quiet_note_agreed.server_default is None
    assert t.c.asked_on.server_default is None
    assert any(
        isinstance(c, UniqueConstraint) and [col.name for col in c.columns] == ["id"]
        for c in t.constraints
    )


def test_the_three_foreign_keys_cascade_and_none_goes_to_a_membership() -> None:
    """A membership key would delete the row on leaving, and a rejoin could ask again at
    once (ADR-0046): validity is a read-time join instead."""
    keys = {fk.name: fk for fk in _table().foreign_key_constraints}

    assert {name: fk.referred_table.name for name, fk in keys.items()} == {
        "teacher_request_student_id_fkey": "account",
        "teacher_request_teacher_id_fkey": "account",
        "teacher_request_shala_id_fkey": "shala",
    }
    assert {fk.ondelete.upper() for fk in keys.values()} == {"CASCADE"}


def test_the_checks_hold_the_four_states_and_refuse_a_self_request() -> None:
    checks = _checks(_table())

    [states] = [c for c in checks if "state" in c]
    assert all(f"'{s.value}'" in states for s in RequestState)
    assert states.count("'") == 2 * len(RequestState)
    assert any("student_id <> teacher_id" in c for c in checks)


def test_the_indexes_serve_the_waiting_list_the_cascades_and_the_tick() -> None:
    indexes = {i.name: i for i in _table().indexes}

    assert set(indexes) == {
        "teacher_request_teacher_id_created_at_idx",
        "teacher_request_teacher_id_idx",
        "teacher_request_shala_id_idx",
        "teacher_request_created_at_idx",
    }
    waiting = indexes["teacher_request_teacher_id_created_at_idx"]
    assert [c.name for c in waiting.columns] == ["teacher_id", "created_at"]
    assert "state = 'waiting'" in str(waiting.dialect_options["postgresql"]["where"])
    # The waiting-list index is partial, so it can't serve a teacher's account delete (the
    # cascade looks up every row by `teacher_id`) or their export: a plain one does. The
    # student's side has the primary key.
    teacher = indexes["teacher_request_teacher_id_idx"]
    assert [c.name for c in teacher.columns] == ["teacher_id"]
    assert teacher.dialect_options["postgresql"]["where"] is None
    assert not teacher.unique
    assert [c.name for c in indexes["teacher_request_shala_id_idx"].columns] == ["shala_id"]
    assert [c.name for c in indexes["teacher_request_created_at_idx"].columns] == ["created_at"]


def test_the_delivery_ledger_takes_the_request_category() -> None:
    [category] = [
        c for c in _checks(tables.metadata.tables["tristhana.notification_delivery"])
        if "category" in c
    ]  # fmt: skip

    assert "'request'" in category
    assert all(f"'{c}'" in category for c in ("moon", "practice", "announcement"))


def test_teacher_link_gained_no_column() -> None:
    """ADR-0046: no pending state on the link, so no reader of links needs a filter."""
    link = tables.metadata.tables["tristhana.teacher_link"]

    assert set(link.c.keys()) == {
        "student_id", "teacher_id", "is_primary", "linked_on", "created_at",
        "quiet_note_agreed", "announcements_muted",
    }  # fmt: skip


def test_exported_as_the_persons_own_requests() -> None:
    assert "teacher_request" in EXPORTED_TABLES
    assert "teacher_request" not in EXCLUDED_TABLES


async def test_unconfigured_storage_has_unavailable_requests() -> None:
    requests = UnconfiguredStorage().teacher_requests

    with pytest.raises(StorageUnavailable):
        await requests.mine(uuid4(), NOW)
    with pytest.raises(StorageUnavailable):
        await requests.due(NOW, 10)


def _fk_violation(constraint: str) -> DBAPIError:
    cause = SimpleNamespace(constraint_name=constraint)
    orig = SimpleNamespace(sqlstate="23503", __cause__=cause, constraint_name=None)
    return DBAPIError("INSERT", {}, orig)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("constraint", "gone"),
    [
        ("teacher_request_student_id_fkey", True),  # the asking student is the caller
        ("teacher_request_teacher_id_fkey", False),  # the asked teacher: the repository's
        ("teacher_request_shala_id_fkey", False),
        ("teacher_link_student_id_fkey", True),  # ID-04's accept; `approve` catches it first
        ("teacher_link_teacher_id_fkey", False),
    ],
)
def test_is_account_gone_learns_the_asking_students_key(constraint: str, gone: bool) -> None:
    assert is_account_gone(_fk_violation(constraint)) is gone


# The 23503 mapping of the approval (spec §6), on a connection that fails as Postgres would


class _FailingEngine:
    """`engine.connect()` whose statement raises: the real `connection()` wraps it, so an
    error that escapes the repository is mapped as in production."""

    def __init__(self, error: DBAPIError) -> None:
        self._error = error

    def connect(self) -> "_FailingEngine":
        return self

    async def __aenter__(self) -> "_FailingEngine":
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def execute(self, _statement: object) -> Any:
        raise self._error


def _repo(constraint: str) -> Any:
    from tristhana.infrastructure.db.teacher_requests import SqlTeacherRequestRepository

    return SqlTeacherRequestRepository(_FailingEngine(_fk_violation(constraint)))  # type: ignore[arg-type]


async def test_a_vanished_student_is_gone_and_never_the_teachers_own_account() -> None:
    """`teacher_link_student_id_fkey` is in `is_account_gone` for ID-04's accept, where the
    student is the caller. In an approval the caller is the teacher, so the repository
    catches it inside the connection block; outside it, this would raise `AccountGone`."""
    from tristhana.application.ports.teacher_requests import Answer, Answered
    from tristhana.domain.teacher_requests import CAPS

    answer = await _repo("teacher_link_student_id_fkey").approve(uuid4(), uuid4(), CAPS, NOW)

    assert answer == Answer(Answered.GONE)


async def test_a_vanished_teacher_is_the_caller() -> None:
    from tristhana.application.ports.export import AccountGone
    from tristhana.domain.teacher_requests import CAPS

    repo = _repo("teacher_link_teacher_id_fkey")

    with pytest.raises(AccountGone):
        await repo.approve(uuid4(), uuid4(), CAPS, NOW)
    with pytest.raises(AccountGone):
        await repo.approve_all(uuid4(), NOW, CAPS, NOW)


async def test_confirm_all_tries_once_more_when_a_student_vanished() -> None:
    from tristhana.domain.teacher_requests import CAPS

    with pytest.raises(StorageUnavailable):  # twice in a row: a gentle "try again"
        await _repo("teacher_link_student_id_fkey").approve_all(uuid4(), NOW, CAPS, NOW)


async def test_any_other_constraint_is_not_swallowed() -> None:
    from tristhana.domain.teacher_requests import CAPS

    with pytest.raises(DBAPIError):
        await _repo("teacher_link_not_self_check").approve(uuid4(), uuid4(), CAPS, NOW)


async def test_ask_maps_a_vanished_teacher_and_a_vanished_shala() -> None:
    from tristhana.application.ports.export import AccountGone
    from tristhana.domain.teacher_requests import CAPS

    async def ask(constraint: str) -> Any:
        return await _repo(constraint).ask(uuid4(), uuid4(), uuid4(), NOW.date(), True, CAPS, NOW)

    teacher_gone = await ask("teacher_request_teacher_id_fkey")
    shala_gone = await ask("teacher_request_shala_id_fkey")

    assert (teacher_gone.me is not None, teacher_gone.done) == (True, False)  # `NotAllowed`
    assert (shala_gone.me, shala_gone.done) == (None, False)  # `NotFound`
    with pytest.raises(AccountGone):  # the asking student is the caller
        await ask("teacher_request_student_id_fkey")
