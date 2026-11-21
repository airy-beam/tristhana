"""Migration 0030 `share_card` kind 'moon' (ST-10), without a database: the head and the
model's CHECK. Up/down and `alembic check` run on Postgres in `test_db_share_cards.py`."""

from alembic.script import ScriptDirectory
from sqlalchemy import CheckConstraint

from tristhana.infrastructure.db import tables
from tristhana.infrastructure.db.migrate import alembic_config


def test_0030_follows_0029_and_is_the_head() -> None:
    script = ScriptDirectory.from_config(alembic_config("postgresql://unused"))
    revision = script.get_revision("0030")
    assert revision is not None
    assert revision.down_revision == "0029"
    assert script.get_current_head() == "0030"


def test_share_card_kind_allows_moon() -> None:
    table = tables.metadata.tables["tristhana.share_card"]
    checks = [str(c.sqltext) for c in table.constraints if isinstance(c, CheckConstraint)]
    assert "kind IN ('month', 'year', 'asana', 'count', 'moon')" in checks
