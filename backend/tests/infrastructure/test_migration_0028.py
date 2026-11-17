"""Migration 0028 `welcomed_at` (UI-06 spec §3, §6), without a database: its place, the one
additive nullable column, and that it is not part of the export. The write (`mark_welcomed`)
and up/down/`alembic check` run on Postgres in `test_db_accounts.py`."""

from alembic.script import ScriptDirectory
from sqlalchemy import DateTime

from tristhana.infrastructure.db import tables
from tristhana.infrastructure.db.migrate import alembic_config


def test_0028_follows_0027() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql://unused"))
    revision = script.get_revision("0028")
    assert revision is not None  # the head is checked by the newest migration's test
    assert revision.down_revision == "0027"


def test_the_column_is_a_nullable_instant_without_a_default() -> None:
    column = tables.account.c.welcomed_at

    assert isinstance(column.type, DateTime)
    assert column.type.timezone is True
    assert column.nullable is True
    assert column.server_default is None  # no backfill: activity is checked on /start


def test_it_is_a_flag_of_the_app_not_the_persons_data() -> None:
    """Like `day_off_dismissed_at`: an internal guard, never exported (spec §6)."""
    import inspect

    from tristhana.domain import export

    assert "welcomed" not in inspect.getsource(export)
