# Tristhana backend

FastAPI API + Telegram bot. See the repo `CLAUDE.md` for commands and rules.

## Local Postgres (accounts, ID-01)

Accounts need Postgres 17 (same major as Supabase). Without `DATABASE_URL` the app still
starts, but the bot answers "try again in a minute" and `/api/v1/me` returns 503.

```sh
podman run -d --name tristhana-pg -e POSTGRES_PASSWORD=dev -e POSTGRES_DB=tristhana \
  -p 127.0.0.1:5432:5432 docker.io/library/postgres:17-alpine
# backend/.env: DATABASE_URL=postgresql://postgres:dev@127.0.0.1:5432/tristhana
uv run tristhana-migrate            # applies migrations (reads DATABASE_URL from the environment)
```

The DB tests (`-m db` marker) run when `TEST_DATABASE_URL` points to a disposable database,
e.g. `TEST_DATABASE_URL=postgresql://postgres:dev@127.0.0.1:5432/tristhana_test uv run pytest`.
They are skipped without it, except in CI.

New migration: edit `src/tristhana/infrastructure/db/tables.py`, then add a revision under
`src/tristhana/infrastructure/db/migrations/versions/`. A test runs `alembic check`, so the
two can't drift. Migrations must be expand/contract: the previous revision keeps serving
while the deploy's `tristhana-migrate` job runs.

In the Mini App's browser mock (`npm run dev`), initData is signed by the backend's dev-only
`/dev/telegram-init-data` (`APP_ENV=dev`, `DEV_INIT_DATA=true`, any bot token), so the real
auth path runs. It mints a session for any user id: keep it off when the dev server is
reachable through a tunnel.
