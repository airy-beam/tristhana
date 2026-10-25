"""day off: the weekly day off on the account, reminder days follow it (PR-09)

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-25

Expand-only (ADR-0014): nullable columns. The data step only turns stored reminder days
that repeat today's default (Sun-Fri) into NULL, which the previous revision also reads as
Sun-Fri, so it keeps serving correctly while this runs. No day off is inferred (explicit
choices only, ADR-0021).
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | None = None
depends_on: str | None = None

SCHEMA = "tristhana"
_CHECKS = {
    "day_off": "day_off BETWEEN 0 AND 127",
    "day_off_before": "day_off_before BETWEEN 0 AND 127",
    "day_off_period": "day_off_before IS NULL OR day_off_since IS NOT NULL",
    "day_off_since_set": "day_off_since IS NULL OR day_off IS NOT NULL",
}


def upgrade() -> None:
    op.add_column("account", sa.Column("day_off", sa.SmallInteger()), schema=SCHEMA)
    op.add_column("account", sa.Column("day_off_since", sa.Date()), schema=SCHEMA)
    op.add_column("account", sa.Column("day_off_before", sa.SmallInteger()), schema=SCHEMA)
    op.add_column(
        "account", sa.Column("day_off_dismissed_at", sa.DateTime(timezone=True)), schema=SCHEMA
    )
    for name, condition in _CHECKS.items():
        op.create_check_constraint(
            op.f(f"account_{name}_check"), "account", condition, schema=SCHEMA
        )
    # NULL = "follow the day off", which for a day off never chosen is Sun-Fri: unchanged.
    op.execute(
        """
        UPDATE tristhana.notification_settings SET practice_days = NULL
        WHERE practice_days @> '{1,2,3,4,5,7}'::smallint[]
          AND practice_days <@ '{1,2,3,4,5,7}'::smallint[]
        """
    )


def downgrade() -> None:
    for name in _CHECKS:
        op.execute(f"ALTER TABLE tristhana.account DROP CONSTRAINT IF EXISTS account_{name}_check")
    for column in ("day_off_dismissed_at", "day_off_before", "day_off_since", "day_off"):
        op.drop_column("account", column, schema=SCHEMA)
