-- Read-only role for the weekly backup job (infra/backup/README.md). Run ONCE by the owner in
-- the Supabase SQL editor. Replace the password placeholder with a letters+digits-only
-- password (it goes into a URL); put it only into the Secret Manager secret `database-url-backup`.

CREATE ROLE tristhana_backup LOGIN PASSWORD '<generate-a-password>'
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
ALTER ROLE tristhana_backup SET default_transaction_read_only = on;
ALTER ROLE tristhana_backup SET statement_timeout = '5min';

GRANT USAGE ON SCHEMA tristhana TO tristhana_backup;
GRANT SELECT ON ALL TABLES IN SCHEMA tristhana TO tristhana_backup;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA tristhana TO tristhana_backup;
-- Tables created by later migrations (run as postgres) are readable too.
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA tristhana
  GRANT SELECT ON TABLES TO tristhana_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA tristhana
  GRANT SELECT ON SEQUENCES TO tristhana_backup;
