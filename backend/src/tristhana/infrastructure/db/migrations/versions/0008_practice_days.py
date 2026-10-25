"""practice days: reminder days are the practice days, no longer chosen (PR-09)

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-25

The owner merged the two day settings (2026-10-25): reminders come on the practice days,
which the day off decides. Stored custom reminder days become NULL, which revision 0007
also reads as "follow the day off", so it keeps serving correctly while this runs. The
column stays (expand/contract); a later migration drops it.
"""

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE tristhana.notification_settings SET practice_days = NULL "
        "WHERE practice_days IS NOT NULL"
    )


def downgrade() -> None:
    pass  # the custom days are gone for good; NULL reads as "follow the day off"
