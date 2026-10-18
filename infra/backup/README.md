# Database backups

Supabase's free plan has no backups we can rely on, so a weekly logical dump runs in our
own GCP project (decided with ID-01, before the private beta).

| What | Where |
|---|---|
| Job | Cloud Run Job `tristhana-backup` (europe-west3), image `postgres:17-alpine` pinned by digest, runs `infra/backup/backup.sh` |
| Schedule | Cloud Scheduler `tristhana-backup-weekly`, Sundays 03:00 UTC |
| Output | `gs://braided-trees-444417-u6-tristhana-backups/tristhana-<UTC timestamp>.dump` (pg_dump custom format, schema `tristhana` only), deleted after 90 days |
| DB login | role `tristhana_backup`: read-only (`infra/supabase/backup_role.sql`), secret `database-url-backup` |
| TLS | verify-full against `supabase-ca` (the CA from `infra/supabase/certs/`, as a secret file) |
| Account | SA `tristhana-backup`: create + read objects in the bucket, never delete or overwrite |

Set up by `infra/gcp/bootstrap.sh` (re-run it after changing `backup.sh`: the script is
embedded in the job). Cost: a few KB per week, seconds of job time: effectively $0.

Private values stay encrypted in the dump (ladies' holiday is sealed, ADR-0016), so a dump
is only fully useful together with the `field-encryption-keys` secret.

## Check it ran
```sh
gcloud run jobs executions list --job tristhana-backup --region europe-west3 \
  --project braided-trees-444417-u6 --limit 5
gcloud storage ls -l gs://braided-trees-444417-u6-tristhana-backups/ | tail -5
```
Run once by hand: `gcloud run jobs execute tristhana-backup --region europe-west3 --project braided-trees-444417-u6 --wait`.

## Restore (practise on a scratch database first)
1. Download a dump: `gcloud storage cp gs://braided-trees-444417-u6-tristhana-backups/<file>.dump .`
2. Restore it into an **empty** database (it creates schema `tristhana`, its tables, data and
   `alembic_version`):
   ```sh
   pg_restore --dbname "<target url>" --no-owner --exit-on-error <file>.dump
   ```
   Locally: start Postgres 17 as in `backend/README.md`, create a database, restore into it.
3. Into Supabase after a disaster: restore into the project as `postgres` (session pooler
   URL from the `database-url-migrate` secret), then re-run the grants of
   `infra/supabase/roles.sql` and `infra/supabase/backup_role.sql` (the dump carries no
   privileges), and deploy as usual (migrations continue from the restored version).

Tested 2026-10-18 on a local Postgres 17: dump → restore into an empty database gave the
same rows, the same sealed bytes and the same `alembic_version`.
