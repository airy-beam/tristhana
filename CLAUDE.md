# Tristhana: Ashtanga yoga practice platform

A Telegram bot + Telegram Mini App (later web/mobile) for the **Ashtanga yoga** community. Students log practice and see stats. Teachers follow their students. Shalas publish schedules. Moon days are handled correctly. Hobby project, built to be low-cost and responsive.

## Where the knowledge lives
- **Product & planning notes (Obsidian, source of truth for product decisions):**
  `/home/pumpkin_vibe/Documents/pumpkin_notes/02_projects/tristhana_bot/`
  - `00 Index.md`: hub · `01 Domain Context.md`: **read before any domain work** · `02 Requirements.md`: requirement IDs (e.g. `PR-03`)
  - `03 Open Questions & Decisions.md`: decision log · `04 Architecture.md` · `05 Domain Model.md`
  - `06 Time Zones.md` · `07 Moon Days.md` · `08 Asana Catalog (draft).md` · `09 Roadmap.md`: **current phase and task status**
  - `11 Working with Claude Code.md`: how the human uses this setup
- **Diagrams:** `/home/pumpkin_vibe/Documents/pumpkin_notes/attachments/tristhana_bot/diagrams/tristhana_bot_*.mmd` (+ `.png`). Re-render with `python3 tools/render_diagrams.py`.
- **Promo images and videos:** the other subfolders of `attachments/tristhana_bot/` (`launch/`, `carousel/`, `teasers/`, `reels/`, `beta/`, `phases/`, `series/`); the map is in `13 Launch Materials.md`. The Reels teaser videos, their sources and their build live only in `reels/` (start with its `README.md`), not in this repository.
- **Technical decisions:** `docs/adr/` (ADR per decision; add one for any significant choice).
- **Prior art (read-only):** `/run/media/pumpkin_vibe/abff5e52-c45d-434c-9c88-8d3e7c83a7b4/Documents/Programming/ashtanga/`. The moon algorithm reference is `moon_days/generator/generator.py`. Do not copy the secrets found there.

## Domain essentials (short; details in 01 Domain Context)
- 6 series: Primary (1st), Intermediate (2nd), Advanced A–D (3rd–6th). Every practice = opening (Surya Namaskara A/B) → standing (Padangusthasana … **Parsvottanasana**; UHP…Virabhadrasana belong to Primary) → series body up to the student's **last given asana** → backbending → finishing.
- Class types: **Mysore** (self-paced, long window), **Led** (fixed start, teacher counts), **1:1**, **home self-practice** (no class, very common). Online or offline.
- Rest days: weekly day off (Sat or Sun), **moon days** (Purnima/Amavasya, tithi at local sunrise, may differ ±1 day by location), **ladies' holiday** (sensitive, hidden by default), sick, travel.
- Moon days: **never invent a new algorithm**. Port `generator.py` (Swiss Ephemeris, sunrise tithi, kshaya detection). Golden tests against SYC-posted dates.
- Asana names: simple Latin is the primary display, IAST is metadata, RU uses Cyrillic transliteration. Variants (A/B…) exist only where the catalog lists them.
- Tone: supportive, never guilt-inducing. Streaks skip rest/moon days. No leaderboards by default.

## Architecture rules (non-negotiable)
- **Monorepo:** `backend/` (Python 3.13, FastAPI, SQLAlchemy 2 async, Alembic, uv), `miniapp/` (React + TS + Vite), `site/` (public landing page + guides, Astro Starlight), `data/seed/`, `docs/adr/`, `infra/`, `tools/`.
- **Hexagonal layering** in `backend/src/tristhana/`: `domain/` (pure, no I/O) ← `application/` (use cases + ports) ← adapters (`api/`, `bots/telegram/`, `jobs/`, `infrastructure/`).
  - `aiogram` is imported **only** in `bots/telegram/`. Bot handlers call use cases and contain no business logic.
  - The REST API and the bot use the **same use cases**.
  - Authorization checks live in `application/` policies, not in handlers or the UI.
- **API-first:** versioned `/api/v1`. The OpenAPI spec generates the Mini App's TS client. Don't hand-write API types in the frontend.
- **Time:** instants are `timestamptz` UTC. Practice days are `date` + IANA tz. Recurring classes are wall-clock + IANA zone + RRULE. Never store fixed offsets. Every displayed time carries a zone label in the form `07:00 Almaty (UTC+5)`.
- **i18n:** all user-facing strings live in Fluent `.ftl` files (`en`, `ru`). No hard-coded UI text in code. Russian plurals go through Fluent.
- **Privacy:** diary, check-in notes and ladies' holiday reason are encrypted at the application level. Teacher views get projected data (ladies' holiday becomes "rest") unless the student opted in.
- **Responsiveness:** answer callback queries first. Edit messages in place. Stateless callback data. One DB round trip per interaction where possible. Lazy-import heavy libs. Target < 300 ms p50 per tap (warm).
- **Data, not code:** asanas, series and sequences come from `data/seed/*.yaml` → DB. Never hard-code the asana list.
- **Secrets:** never commit them. Use `.env` locally (git-ignored) and Secret Manager in the cloud.

## Commands
> CI: `.github/workflows/backend.yml`, `miniapp.yml` and `site.yml` (each runs its checks on a pull request and deploys from `main`). API contract: `cd backend && uv run tristhana-openapi` → `miniapp/src/api/openapi.json`, then `cd miniapp && npm run gen:api`.
- Backend: `cd backend && uv sync` · `uv run pytest` · `uv run ruff check --no-cache . && uv run ruff format .` (`--no-cache` before committing: a stale cache once hid a CI failure) · `uv run pyright` · `uv run lint-imports` · full moon parity: `uv run pytest -m slow` · DB tests: set `TEST_DATABASE_URL` (local Postgres, see `backend/README.md`) · migrations: `uv run tristhana-migrate` (reads `DATABASE_URL` from the environment, not `.env`: `set -a && . ./.env && set +a` first, or for the local container pass it inline: `DATABASE_URL=postgresql://postgres:dev@127.0.0.1:5432/tristhana uv run tristhana-migrate`; a fresh dev DB must be migrated once before `tristhana-dev`)
- Run locally: `cd backend && uv run tristhana-dev` (API on :8000, `/docs`; with `TELEGRAM_MODE=polling` + the dev bot token in `backend/.env`, @tristhana_dev_bot long-polls in the same process). Config: copy `backend/.env.example` → `backend/.env`.
- Mini App: `cd miniapp && npm ci` · `npm run dev` (mocked Telegram; `/api` proxied to :8000) · `npm test` (CI runs in UTC, so check with `TZ=UTC npm test` too) · `npm run lint` · `npm run format:check` (CI runs it; fix with `npx prettier --write .`) · `npm run typecheck` · `npm run build && npm run check:bundle` · `npm run gen:api`
- Public site (UI-05, `site/`): `cd site && npm ci` · `npm run dev` (:4321) · `npm test` · `npm run check:guide` (`-- --write` refreshes `guide-map.yaml`, `-- --stale` lists pages older than their features' specs) · `npm run typecheck` · `npm run format:check` · `npm run build && node scripts/check-dist.mjs` · screenshots: `npm run shots` (`-- --only <ID|name>`, `-- --lang <en|ru>`; own demo DB `tristhana_demo`, backend :8010, Mini App :5183, needs `tristhana-pg` and Chrome). Guides quote labels with `:ftl[key]` and commands with `:cmd[name]`, never by hand (`site/README.md`, ADR-0043).
- Diagrams: `python3 tools/render_diagrams.py`
- Brand images: `docs/brand/render.sh SRC OUT W H` (sources in `docs/brand/src/`, see `docs/brand/README.md`)
- Ops (☁️ ask the owner first): `infra/gcp/bootstrap.sh --dry-run`, then without the flag · `python3 tools/telegram/set_webhook.py [--info]` (webhook, menu button, command menu, profile texts; `--texts` sets only the bot's description and about text from `bot-description` / `bot-about` in `bot.ftl`) · container check: `ENGINE=podman infra/ci/container-smoke.sh IMAGE` · catalog review table: `cd backend && uv run python ../tools/catalog/render_review.py <notes-dir>`
- Prod env vars live only in the deploy step of `.github/workflows/backend.yml` (`--set-env-vars` replaces them all on each deploy); never set them by hand on the service.
- Guide links: `PUBLIC_SITE_URL` in the same deploy step puts "📖 Guide" under the bot's `/help`; the Mini App's copy of the address is `miniapp/src/guide.ts`. The site deploys from `main` by `.github/workflows/site.yml` to the Hosting site `tristhana-guide`, served at https://tristhana.app (custom domain at Porkbun, DNS records there; the old `tristhana-guide.web.app` address still works).
- Platform admins: `PLATFORM_ADMIN_IDS` (account UUIDs, not Telegram ids) in the same deploy step; the bot's `/admin` is in no command menu (ADR-0042).

## How we work
- Check `09 Roadmap.md` for the current phase. Work items reference requirement IDs.
- Feature flow: `/feature <ID>` (spec → confirm with the user → TDD → review → update notes). Small fixes don't need the full flow.
- Guides: when a change alters what a person sees, `/guide-update <ID>` updates the public guides in `site/` (EN + RU pages, screenshots, What's new); `/guide-check` reports what is out of step.
- Domain-sensitive changes (sequences, moon days, terminology, rest-day logic) → consult the `ashtanga-expert` agent.
- Before calling work done: tests pass, ruff/pyright clean, strings in `.ftl` for both RU and EN, no layering violations, and the roadmap/decision notes are updated (`notes-keeper`).
- Ask the user when a product decision is ambiguous. Record answers in `03 Open Questions & Decisions.md`.
- Commit messages: imperative, reference the requirement ID (`PR-03: add practice length picker`).
