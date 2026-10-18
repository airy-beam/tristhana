"""accounts and identities (ID-01, ID-02)

Revision ID: 0001
Revises:
Create Date: 2026-10-18

Expand/contract: the previous revision keeps serving while this runs (ADR-0014).
"""

from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None

SCHEMA = "tristhana"


def _timestamp(name: str) -> sa.Column[datetime]:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())


def upgrade() -> None:
    op.create_table(
        "account",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("display_name", sa.Text()),
        sa.Column("locale", sa.Text(), nullable=False),
        sa.Column("timezone", sa.Text()),
        _timestamp("created_at"),
        _timestamp("updated_at"),
        _timestamp("last_seen_at"),
        sa.CheckConstraint(
            "char_length(display_name) <= 64", name="account_display_name_length_check"
        ),
        sa.CheckConstraint("locale IN ('en', 'ru')", name="account_locale_check"),
        sa.PrimaryKeyConstraint("id", name="account_pkey"),
        schema=SCHEMA,
    )
    op.create_table(
        "identity",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("provider_user_id", sa.Text(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        _timestamp("created_at"),
        sa.CheckConstraint("provider IN ('telegram')", name="identity_provider_check"),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["tristhana.account.id"],
            name="identity_account_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("provider", "provider_user_id", name="identity_pkey"),
        schema=SCHEMA,
    )
    op.create_index("identity_account_id_idx", "identity", ["account_id"], schema=SCHEMA)
    # The app's login role (infra/supabase/roles.sql) gets DML only, never DDL. Local and CI
    # databases don't have it, hence the guard.
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tristhana_app') THEN
            GRANT USAGE ON SCHEMA tristhana TO tristhana_app;
            GRANT SELECT, INSERT, UPDATE, DELETE
              ON tristhana.account, tristhana.identity TO tristhana_app;
            ALTER DEFAULT PRIVILEGES IN SCHEMA tristhana
              GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO tristhana_app;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.drop_table("identity", schema=SCHEMA)
    op.drop_table("account", schema=SCHEMA)
