"""practice reminder settings (PR-10, NT-01 practice category)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-19

Expand/contract: only nullable columns and a wider CHECK, so the previous revision keeps
serving while this runs (ADR-0014).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None

SCHEMA = "tristhana"
_CATEGORY = "notification_delivery_category_check"
# 0004 ran its CHECK names through the naming convention twice; this is the name it created
# (SQLAlchemy shortens long names deterministically, so prod has the same one).
_CATEGORY_0004 = "notification_delivery_notification_delivery_category_ch_2931"


def upgrade() -> None:
    op.add_column("notification_settings", sa.Column("practice_on", sa.Boolean()), schema=SCHEMA)
    op.add_column("notification_settings", sa.Column("practice_at", sa.Time()), schema=SCHEMA)
    op.add_column(
        "notification_settings",
        sa.Column("practice_days", ARRAY(sa.SmallInteger())),
        schema=SCHEMA,
    )
    op.create_check_constraint(
        op.f("notification_settings_practice_days_check"),
        "notification_settings",
        "practice_days <@ '{1,2,3,4,5,6,7}'::smallint[] AND cardinality(practice_days) > 0",
        schema=SCHEMA,
    )
    # IF EXISTS on both spellings: safe whichever name a database ended up with.
    for name in (_CATEGORY_0004, _CATEGORY):
        op.execute(f'ALTER TABLE {SCHEMA}.notification_delivery DROP CONSTRAINT IF EXISTS "{name}"')
    op.create_check_constraint(
        op.f(_CATEGORY), "notification_delivery", "category IN ('moon', 'practice')", schema=SCHEMA
    )


def downgrade() -> None:
    op.execute("DELETE FROM tristhana.notification_delivery WHERE category = 'practice'")
    op.drop_constraint(op.f(_CATEGORY), "notification_delivery", schema=SCHEMA)
    op.create_check_constraint(
        op.f(_CATEGORY_0004), "notification_delivery", "category IN ('moon')", schema=SCHEMA
    )
    op.drop_constraint(
        op.f("notification_settings_practice_days_check"), "notification_settings", schema=SCHEMA
    )
    for column in ("practice_days", "practice_at", "practice_on"):
        op.drop_column("notification_settings", column, schema=SCHEMA)
