"""Migration 0021 and the storage wiring (SC-01 spec §6, §7), without a database. The CHECKs,
cascades, up/down and `alembic check` run on Postgres in `test_db_shalas.py`."""

from typing import Any
from uuid import uuid4

import pytest
from alembic.script import ScriptDirectory

from tristhana.application.ports.storage import StorageUnavailable
from tristhana.infrastructure.db import tables
from tristhana.infrastructure.db.export import EXCLUDED_TABLES, EXPORTED_TABLES
from tristhana.infrastructure.db.migrate import alembic_config
from tristhana.infrastructure.db.storage import UnconfiguredStorage

NEW_TABLES = ("shala", "shala_staff", "shala_student", "shala_staff_invite")


def _table(name: str) -> Any:
    table = tables.metadata.tables.get(f"tristhana.{name}")
    assert table is not None, name
    return table


def test_0021_follows_0020_and_is_the_head() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql://unused"))
    revision = script.get_revision("0021")

    assert revision is not None
    assert revision.down_revision == "0020"
    assert script.get_current_head() == "0021"


@pytest.mark.parametrize("name", NEW_TABLES)
def test_the_tables_exist_in_the_metadata(name: str) -> None:
    assert _table(name) is not None


def test_the_shala_columns() -> None:
    shala = _table("shala")

    assert set(shala.c.keys()) == {
        "id",
        "name",
        "city",
        "moon_city",
        "online",
        "owner_id",
        "join_code",
        "created_at",
        "updated_at",
    }
    assert [c.name for c in shala.primary_key.columns] == ["id"]
    assert shala.c.moon_city.nullable is True
    for name in ("name", "city", "online", "owner_id", "join_code"):
        assert shala.c[name].nullable is False, name
    assert str(shala.c.online.server_default.arg) == "false"
    assert shala.c.join_code.unique is True or any(
        {c.name for c in u.columns} == {"join_code"}
        for u in shala.constraints
        if u.__class__.__name__ == "UniqueConstraint"
    )


def test_the_owner_cascades_with_the_account() -> None:
    [fk] = list(_table("shala").c.owner_id.foreign_keys)

    assert fk.column.table.name == "account"
    assert fk.ondelete == "CASCADE"


@pytest.mark.parametrize("name", ["shala_staff", "shala_student"])
def test_the_membership_keys_and_cascades(name: str) -> None:
    table = _table(name)

    assert [c.name for c in table.primary_key.columns] == ["shala_id", "account_id"]
    assert table.c.joined_on.nullable is False
    for column, parent in (("shala_id", "shala"), ("account_id", "account")):
        [fk] = list(table.c[column].foreign_keys)
        assert (fk.column.table.name, fk.ondelete) == (parent, "CASCADE")
    assert any(
        [c.name for c in i.columns] == ["account_id", "created_at"] for i in table.indexes
    ), [i.name for i in table.indexes]


def test_staff_roles_are_a_text_array_defaulting_to_empty() -> None:
    roles = _table("shala_staff").c.roles

    assert roles.nullable is False
    assert "{}" in str(roles.server_default.arg)
    assert "roles" not in _table("shala_student").c


def test_the_invite_table() -> None:
    invite = _table("shala_staff_invite")

    assert [c.name for c in invite.primary_key.columns] == ["code"]
    assert set(invite.c.keys()) == {"code", "shala_id", "role", "created_by", "expires_at"}
    assert invite.c.expires_at.nullable is False
    assert invite.c.expires_at.type.timezone is True
    for column, parent in (("shala_id", "shala"), ("created_by", "account")):
        [fk] = list(invite.c[column].foreign_keys)
        assert (fk.column.table.name, fk.ondelete) == (parent, "CASCADE")
    assert any([c.name for c in i.columns] == ["shala_id"] for i in invite.indexes)


def test_the_owner_lookup_is_indexed() -> None:
    assert any([c.name for c in i.columns] == ["owner_id"] for i in _table("shala").indexes)


def test_memberships_are_exported_and_codes_are_not() -> None:
    """The export shows my own memberships (built in `shalas`); invites are credentials."""
    assert "shala_staff_invite" in EXCLUDED_TABLES
    for name in ("shala_staff", "shala_student"):
        assert name in EXPORTED_TABLES or name in EXCLUDED_TABLES
    assert "shala" not in EXPORTED_TABLES  # rows hold the join code and other people's ids


async def test_unconfigured_storage_has_unavailable_shalas() -> None:
    shalas = UnconfiguredStorage().shalas

    with pytest.raises(StorageUnavailable):
        await shalas.mine(uuid4())
    with pytest.raises(StorageUnavailable):
        await shalas.card(uuid4(), uuid4())
