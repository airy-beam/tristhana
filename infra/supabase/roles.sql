-- Tristhana database roles (ADR-0014). Run ONCE by the owner in the Supabase SQL editor,
-- before the first deploy that runs migrations. Replace the password placeholder with a
-- freshly generated one (e.g. `openssl rand -base64 32`), then put it only into the
-- Secret Manager secret `database-url` (never into git or a chat).
--
-- tristhana_app: what the API service logs in as. DML only, no DDL: migration 0001 grants
-- SELECT/INSERT/UPDATE/DELETE on schema `tristhana` tables (and default privileges for
-- tables created later by the migration role).
-- Migrations log in as `postgres` via the `database-url-migrate` secret.

CREATE ROLE tristhana_app LOGIN PASSWORD '<generate-a-password>'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;

-- Fail fast instead of piling up behind locks or long queries.
ALTER ROLE tristhana_app SET statement_timeout = '5s';
ALTER ROLE tristhana_app SET lock_timeout = '2s';
ALTER ROLE tristhana_app SET idle_in_transaction_session_timeout = '10s';

-- Idempotent catch-up: if migration 0001 already ran before this script (it grants only
-- when the role exists), give the role its DML rights now. No-op on a fresh project.
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'tristhana') THEN
    GRANT USAGE ON SCHEMA tristhana TO tristhana_app;
    GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA tristhana TO tristhana_app;
    ALTER DEFAULT PRIVILEGES IN SCHEMA tristhana
      GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO tristhana_app;
  END IF;
END $$;
