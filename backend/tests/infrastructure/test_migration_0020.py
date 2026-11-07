"""Migration 0020 and the storage wiring (ST-06, spec §3, §7), without a database. The up, down
and old-image behaviour runs on Postgres in `test_db_teacher_view.py`."""

from datetime import date
from typing import Any
from uuid import uuid4

import pytest
from alembic.script import ScriptDirectory

from tristhana.application.ports.storage import StorageUnavailable
from tristhana.infrastructure.db import tables
from tristhana.infrastructure.db.export import EXCLUDED_TABLES, EXPORTED_TABLES
from tristhana.infrastructure.db.migrate import alembic_config
from tristhana.infrastructure.db.storage import UnconfiguredStorage

ON = date(2026, 11, 7)


def _table(name: str) -> Any:
    table = tables.metadata.tables.get(f"tristhana.{name}")
    assert table is not None, name
    return table


def test_0020_follows_0019_and_is_the_head() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql://unused"))
    revision = script.get_revision("0020")

    assert revision is not None
    assert revision.down_revision == "0019"
    assert script.get_current_head() == "0020"


def test_the_flag_is_a_not_null_boolean_defaulting_to_false() -> None:
    column = _table("teacher_link").c.quiet_note_agreed

    assert column.nullable is False
    assert str(column.server_default.arg) == "false"
    assert column.type.python_type is bool


def test_no_new_index_comes_with_the_column() -> None:
    table = _table("teacher_link")

    assert {i.name for i in table.indexes} == {
        "teacher_link_teacher_id_student_id_idx",
        "teacher_link_one_primary",
    }


def test_the_export_lists_still_export_the_table_per_table() -> None:
    assert "teacher_link" in EXPORTED_TABLES
    assert "teacher_link" not in EXCLUDED_TABLES


async def test_unconfigured_storage_has_an_unavailable_teacher_view() -> None:
    view = UnconfiguredStorage().teacher_view

    with pytest.raises(StorageUnavailable):
        await view.page(uuid4(), 0, 10, ON, ON)
    with pytest.raises(StorageUnavailable):
        await view.student(uuid4(), uuid4(), ON, ON)
