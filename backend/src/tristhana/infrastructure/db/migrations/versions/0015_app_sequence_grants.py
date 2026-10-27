"""app sequence grants: the app role may use sequences (progression_event ids)

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-27

Fix for PR-08: 0001 gave `tristhana_app` default privileges on TABLES only, so the first
table with an identity column (`progression_event`, 0014) failed in production with
"permission denied for sequence progression_event_id_seq". Grants USAGE/SELECT on the
existing sequences and as a default for later ones. Guarded like 0001: local and CI
databases may not have the role.
"""

from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tristhana_app') THEN
            GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA tristhana TO tristhana_app;
            ALTER DEFAULT PRIVILEGES IN SCHEMA tristhana
              GRANT USAGE, SELECT ON SEQUENCES TO tristhana_app;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'tristhana_app') THEN
            ALTER DEFAULT PRIVILEGES IN SCHEMA tristhana
              REVOKE USAGE, SELECT ON SEQUENCES FROM tristhana_app;
            REVOKE USAGE, SELECT ON ALL SEQUENCES IN SCHEMA tristhana FROM tristhana_app;
          END IF;
        END $$;
        """
    )
