#!/bin/sh
# Weekly logical backup of schema `tristhana` (runs in the Cloud Run Job `tristhana-backup`,
# image postgres:17-alpine). See infra/backup/README.md.
#
# Env: DATABASE_URL (role tristhana_backup, read-only), BACKUP_DIR (the mounted bucket),
# PGSSLMODE / PGSSLROOTCERT (TLS verify-full against the Supabase CA).
# Writes one new object per run and never overwrites or deletes (the job's account can't).
set -eu

: "${DATABASE_URL:?DATABASE_URL is not set}"
: "${BACKUP_DIR:?BACKUP_DIR is not set}"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
tmp="/tmp/tristhana-${stamp}.dump"

# Custom format: compressed, restorable table by table with pg_restore.
pg_dump --dbname="$DATABASE_URL" --schema=tristhana --format=custom \
  --no-owner --no-privileges --file="$tmp"

# Sanity check before it counts as a backup: the archive must list our tables.
tables="$(pg_restore --list "$tmp" | grep -c ' TABLE DATA tristhana ' || true)"
if [ "$tables" -lt 1 ]; then
  echo "backup FAILED: archive has no tristhana table data" >&2
  exit 1
fi

cp "$tmp" "${BACKUP_DIR}/tristhana-${stamp}.dump"
echo "backup ok: tristhana-${stamp}.dump, $(wc -c < "$tmp") bytes, ${tables} tables"
