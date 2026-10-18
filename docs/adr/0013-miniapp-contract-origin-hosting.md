# ADR-0013: Mini App API contract, origin and hosting
- Status: accepted
- Date: 2026-10-18
## Context
The Mini App (UI-03) needs a typed client for the backend (NF-05: never hand-write API types), a way to reach the API from a static host (ADR-0004: Firebase Hosting, API on Cloud Run `*.run.app`), and its own UI copy (ADR-0007: Fluent). Spec: `docs/specs/UI-03-miniapp-skeleton.md`.
## Decision
- **Contract as a committed file.** A backend script (`tristhana-openapi`) dumps the OpenAPI schema deterministically to `miniapp/src/api/openapi.json`. `npm run gen:api` runs `openapi-typescript` → `schema.d.ts` (committed). Calls go through `openapi-fetch` (path-based, ~2 KB) wrapped in TanStack Query hooks. Backend CI fails when the dump is stale; miniapp CI fails when the generated types are stale. Frontend work needs no Python toolchain.
- **Cross-origin API with exact-origin CORS.** The Mini App calls `*.run.app` directly. CORS origins come from the `CORS_ORIGINS` setting (exact origins, no wildcard, no credentials; auth will be a bearer JWT), with `max_age=7200` to amortize preflights. Local dev avoids CORS with a Vite proxy to `tristhana-dev`.
- **Telegram SDK:** `@telegram-apps/sdk-react` only, without loading `telegram-web-app.js`.
- **Separate Mini App copy:** `miniapp/src/locales/{en,ru}/app.ftl`, bundled with the app; locale negotiation mirrors `domain/locale.py`, both tested against one shared fixture (`data/i18n/locale_cases.json`).
- **Hosting:** Firebase Hosting on the existing GCP project, deployed from `main` via the existing WIF deployer SA; hashed assets immutable, `index.html` no-cache.
## Consequences
Contract changes show up as reviewable diffs; type drift fails CI. The API stays independent of the static host (a RU mirror can point at it or at a proxy). Authenticated requests pay one preflight per session. The bot and Mini App keep separate `.ftl` files, so shared phrases are duplicated (acceptable while small).
## Alternatives considered
Generating the schema in CI from a running backend (needs Python in the frontend job); hand-written or `orval`-generated hooks (heavier); a Firebase Hosting rewrite of `/api/**` to Cloud Run (same origin, no preflight, but an extra hop, a 60 s timeout and coupling the API to the host); one shared `.ftl` tree for bot and Mini App (cross-package build coupling); the official `telegram-web-app.js` (extra blocking script from telegram.org).
