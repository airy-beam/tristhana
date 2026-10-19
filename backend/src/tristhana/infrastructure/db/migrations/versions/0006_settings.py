"""settings: custom name/locale flags, moon intro flag, defaults back to NULL (ID-06)

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-19

Expand-only (ADR-0014): new columns with defaults; the data steps change no effective
setting, so the previous revision keeps serving correctly while this runs.
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None

SCHEMA = "tristhana"


def upgrade() -> None:
    for column in ("name_custom", "locale_custom"):
        op.add_column(
            "account",
            sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.false()),
            schema=SCHEMA,
        )
    op.add_column(
        "notification_settings",
        sa.Column("moon_intro_sent_at", sa.DateTime(timezone=True)),
        schema=SCHEMA,
    )
    # Q24: the intro went out to everyone who ever got a moon reminder (rows still kept).
    op.execute(
        """
        INSERT INTO tristhana.notification_settings (account_id, moon_intro_sent_at)
        SELECT account_id, min(updated_at) FROM tristhana.notification_delivery
        WHERE category = 'moon' AND status = 'sent' GROUP BY account_id
        ON CONFLICT (account_id) DO UPDATE SET moon_intro_sent_at = EXCLUDED.moon_intro_sent_at
        """
    )
    # Q25: values that only repeat today's defaults become NULL again (= "the default"),
    # so later default changes reach these people too. Effective settings don't change.
    op.execute(
        """
        UPDATE tristhana.notification_settings SET
          moon_offsets = CASE WHEN moon_offsets = '{1,7}'::smallint[]
                              THEN NULL ELSE moon_offsets END,
          moon_at = CASE WHEN moon_at = '19:00' THEN NULL ELSE moon_at END,
          daily_cap = CASE WHEN daily_cap = 3 THEN NULL ELSE daily_cap END,
          quiet_start = CASE WHEN (quiet_start, quiet_end) = ('22:00', '07:00')
                             THEN NULL ELSE quiet_start END,
          quiet_end = CASE WHEN (quiet_start, quiet_end) = ('22:00', '07:00')
                           THEN NULL ELSE quiet_end END
        """
    )
    op.create_check_constraint(
        op.f("notification_settings_quiet_pair_check"),
        "notification_settings",
        "(quiet_start IS NULL) = (quiet_end IS NULL)",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE tristhana.notification_settings "
        "DROP CONSTRAINT IF EXISTS notification_settings_quiet_pair_check"
    )
    op.drop_column("notification_settings", "moon_intro_sent_at", schema=SCHEMA)
    for column in ("locale_custom", "name_custom"):
        op.drop_column("account", column, schema=SCHEMA)
