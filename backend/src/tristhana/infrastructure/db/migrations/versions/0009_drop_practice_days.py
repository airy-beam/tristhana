"""drop practice_days: reminder days are the practice days (PR-09 contract step)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-25

Contract (ADR-0014): 0008 cleared the column and no released revision since reads or
writes it (it only stayed in the table metadata), so the serving revision is unaffected
while this runs. Downgrade brings the column back empty (NULL = follow the day off).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | None = None
depends_on: str | None = None

SCHEMA = "tristhana"


def upgrade() -> None:
    op.drop_column("notification_settings", "practice_days", schema=SCHEMA)  # drops its CHECK


def downgrade() -> None:
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
