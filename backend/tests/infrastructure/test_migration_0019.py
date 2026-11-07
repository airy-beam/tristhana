"""Migration 0019 and the `teacher_link`/`teacher_invite` metadata (ID-04, spec §8), the export
lists, the storage wiring and `is_account_gone`, without a database."""

from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.exc import DBAPIError

from tristhana.application.ports.storage import StorageUnavailable
from tristhana.infrastructure.db import tables
from tristhana.infrastructure.db.engine import is_account_gone
from tristhana.infrastructure.db.export import EXCLUDED_TABLES, EXPORTED_TABLES
from tristhana.infrastructure.db.migrate import alembic_config
from tristhana.infrastructure.db.storage import UnconfiguredStorage


def _table(name: str) -> Any:
    table = tables.metadata.tables.get(f"tristhana.{name}")
    assert table is not None, name
    return table


def test_0019_follows_0018_and_is_the_head() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql://unused"))
    revision = script.get_revision("0019")

    assert revision is not None
    assert revision.down_revision == "0018"
    assert script.get_current_head() == "0019"


def test_teacher_link_columns_and_key() -> None:
    table = _table("teacher_link")

    assert [c.name for c in table.primary_key.columns] == ["student_id", "teacher_id"]
    assert {c.name for c in table.columns} == {
        "student_id",
        "teacher_id",
        "is_primary",
        "linked_on",
        "created_at",
    }
    assert {c.name for c in table.columns if c.nullable} == set()
    assert table.c.is_primary.server_default is not None
    assert table.c.created_at.server_default is not None
    assert table.c.created_at.type.timezone is True


def test_both_foreign_keys_cascade_under_the_names_is_account_gone_reads() -> None:
    table = _table("teacher_link")

    keys = {fk.name: fk for fk in table.foreign_key_constraints}

    assert set(keys) == {"teacher_link_student_id_fkey", "teacher_link_teacher_id_fkey"}
    for fk in keys.values():
        assert fk.referred_table.name == "account"
        assert fk.ondelete.upper() == "CASCADE"


def test_the_indexes_serve_a_teachers_list_and_one_primary_per_student() -> None:
    table = _table("teacher_link")

    indexes = {i.name: i for i in table.indexes}

    assert any([c.name for c in i.columns] == ["teacher_id", "student_id"] for i in table.indexes)
    primary = indexes["teacher_link_one_primary"]
    assert primary.unique is True
    assert [c.name for c in primary.columns] == ["student_id"]
    assert "is_primary" in str(primary.dialect_options["postgresql"]["where"])


def test_a_self_link_is_refused_by_a_check() -> None:
    checks = [c for c in _table("teacher_link").constraints if isinstance(c, CheckConstraint)]

    assert any("student_id" in str(c.sqltext) and "teacher_id" in str(c.sqltext) for c in checks)


def test_teacher_invite_is_one_unique_code_per_account() -> None:
    table = _table("teacher_invite")

    assert [c.name for c in table.primary_key.columns] == ["account_id"]
    assert {c.name for c in table.columns} == {"account_id", "code", "created_at"}
    assert {c.name for c in table.columns if c.nullable} == set()
    [fk] = list(table.foreign_key_constraints)
    assert fk.referred_table.name == "account"
    assert fk.ondelete.upper() == "CASCADE"
    unique = table.c.code.unique or any(
        isinstance(c, UniqueConstraint) and [col.name for col in c.columns] == ["code"]
        for c in table.constraints
    )
    assert unique
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert any("^[A-Za-z0-9]{16}$" in str(c.sqltext) for c in checks)


def test_the_export_lists_choose_on_purpose() -> None:
    assert "teacher_link" in EXPORTED_TABLES
    assert "teacher_invite" not in EXPORTED_TABLES
    assert "credential" in EXCLUDED_TABLES["teacher_invite"]


async def test_unconfigured_storage_has_unavailable_links() -> None:
    links = UnconfiguredStorage().teacher_links

    with pytest.raises(StorageUnavailable):
        await links.overview(uuid4())


def _fk_violation(constraint: str, state: str = "23503") -> DBAPIError:
    cause = SimpleNamespace(constraint_name=constraint)
    orig = SimpleNamespace(sqlstate=state, __cause__=cause, constraint_name=None)
    return DBAPIError("INSERT", {}, orig)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("constraint", "gone"),
    [
        ("teacher_link_student_id_fkey", True),  # the caller is the one deleted mid-write
        ("teacher_link_teacher_id_fkey", False),  # the other person: `accept` returns None
        ("day_log_account_id_fkey", True),  # as before
        ("progression_event_marked_by_fkey", False),
    ],
)
def test_is_account_gone_knows_the_students_key(constraint: str, gone: bool) -> None:
    assert is_account_gone(_fk_violation(constraint)) is gone


def test_is_account_gone_reads_only_foreign_key_violations() -> None:
    assert is_account_gone(_fk_violation("teacher_link_student_id_fkey", "23505")) is False
