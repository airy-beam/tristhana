"""Migration 0022 and the storage wiring (SC-02 spec §6), without a database. The CHECKs,
cascades, the composite teacher FK, up/down and `alembic check` run on Postgres in
`test_db_classes.py`."""

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

NEW_TABLES = ("shala_class", "shala_class_override", "shala_closure", "shala_swap")


def _table(name: str) -> Any:
    table = tables.metadata.tables.get(f"tristhana.{name}")
    assert table is not None, name
    return table


def test_0022_follows_0021() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql://unused"))
    revision = script.get_revision("0022")

    assert revision is not None  # the head is checked by the newest migration's test
    assert revision.down_revision == "0021"


@pytest.mark.parametrize("name", NEW_TABLES)
def test_the_tables_exist(name: str) -> None:
    assert _table(name) is not None


def test_the_shala_gains_its_day_off_and_moon_policy() -> None:
    shala = _table("shala")

    assert shala.c.days_off.nullable is True
    assert shala.c.moon_policy.nullable is False
    assert "closed" in str(shala.c.moon_policy.server_default.arg)


def test_the_class_columns() -> None:
    cls = _table("shala_class")

    assert set(cls.c.keys()) == {
        "id",
        "shala_id",
        "type",
        "title",
        "online",
        "city",
        "teacher_id",
        "start_time",
        "minutes",
        "weekdays",
        "every",
        "starts_on",
        "ends_on",
        "created_at",
        "updated_at",
    }
    for name in ("title", "city", "teacher_id", "ends_on"):
        assert cls.c[name].nullable is True, name
    for name in ("type", "online", "start_time", "minutes", "weekdays", "every", "starts_on"):
        assert cls.c[name].nullable is False, name
    # `shala_id` is also in the composite teacher FK to `shala_staff`.
    [fk] = [f for f in cls.c.shala_id.foreign_keys if f.column.table.name == "shala"]
    assert fk.ondelete == "CASCADE"
    assert any([c.name for c in i.columns] == ["shala_id", "starts_on"] for i in cls.indexes)


@pytest.mark.parametrize("name", ["shala_class", "shala_class_override"])
def test_the_teacher_is_a_composite_staff_fk_set_null(name: str) -> None:
    table = _table(name)
    [fk] = [
        c
        for c in table.foreign_key_constraints
        if {col.name for col in c.columns} == {"shala_id", "teacher_id"}
    ]

    assert fk.referred_table.name == "shala_staff"
    assert fk.ondelete is not None
    assert "SET NULL" in fk.ondelete
    assert "teacher_id" in fk.ondelete  # only the teacher column, not shala_id (PG >= 15)


def test_the_override_key_is_the_rule_date() -> None:
    override = _table("shala_class_override")

    assert [c.name for c in override.primary_key.columns] == ["class_id", "on_date"]
    [fk] = list(override.c.class_id.foreign_keys)
    assert (fk.column.table.name, fk.ondelete) == ("shala_class", "CASCADE")
    assert any([c.name for c in i.columns] == ["shala_id", "on_date"] for i in override.indexes)


def test_the_closure_and_swap_keys() -> None:
    closure, swap = _table("shala_closure"), _table("shala_swap")

    assert [c.name for c in closure.primary_key.columns] == ["id"]
    assert any([c.name for c in i.columns] == ["shala_id", "end_date"] for i in closure.indexes)
    assert [c.name for c in swap.primary_key.columns] == ["shala_id", "from_date"]
    for table in (closure, swap):
        [fk] = list(table.c.shala_id.foreign_keys)
        assert (fk.column.table.name, fk.ondelete) == ("shala", "CASCADE")


def test_no_new_table_points_at_an_account() -> None:
    """Classes belong to the shala, not to a person (spec §6, §7): no account FK (the teacher
    goes through `shala_staff`), so `is_account_gone` is unchanged. They reach `account` through
    `shala`, so the export lists them as excluded on purpose, like `shala`: nothing is exported."""
    for name in NEW_TABLES:
        targets = {fk.column.table.name for fk in _table(name).foreign_keys}
        assert "account" not in targets, name
        assert name not in EXPORTED_TABLES
        assert name in EXCLUDED_TABLES


async def test_unconfigured_storage_has_an_unavailable_schedule() -> None:
    schedule = UnconfiguredStorage().schedule  # pyright: ignore[reportAttributeAccessIssue]

    with pytest.raises(StorageUnavailable):
        await schedule.window(uuid4(), uuid4(), date(2026, 11, 9), date(2026, 11, 15))
