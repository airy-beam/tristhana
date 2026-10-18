# UI-03 (Phase 0 slice): Mini App skeleton (Vite + React + TS, Telegram SDK, theme, Fluent, generated client)

- Status: confirmed by the owner (answers at the end), awaiting owner answers (§8) · Date: 2026-10-18
- Requirements: **UI-03** (Mini App for rich screens; ST-01..03 build on it in Phase 1), **UI-04** (theme light/dark, haptics, main/back buttons, skeleton level), **NF-01** (Fluent en + ru, RU plurals), **NF-05** (generated TS client, no hand-written API types), **NF-09** (first load < 2 s on 4G).
- Related: ADR-0004 (Firebase Hosting), ADR-0007 (Fluent), ADR-0011 (pipeline, WIF), ADR-0012. New: **ADR-0013** (Mini App contract, origin and hosting).

## 1. Scope
**In (PR A, no cloud changes):** `miniapp/` scaffold (Vite, React, TS `strict` + `noUncheckedIndexedAccess`), Telegram SDK init + helpers, theme tokens, Fluent, generated client + TanStack Query, one **Home** screen, Vitest + Testing Library, ESLint (typescript-eslint strict-type-checked, react-hooks, `react/jsx-no-literals`) + Prettier, bundle budget, `miniapp.yml` CI. Backend: OpenAPI dump command + freshness check, `CORS_ORIGINS` setting (off by default).
**In (PR B, after owner ☁️ steps, if Q1 = yes):** Firebase Hosting site, deploy job via WIF, prod `CORS_ORIGINS`, BotFather Mini App URL for both bots, NF-09 measurement (incl. from RU).
**Phase 1 (not here):** initData → backend HMAC → JWT (`POST /api/v1/auth/telegram`), silent time-zone capture, router + real screens (ST-01..03), ECharts (lazy chunk), coach-marks (UI-02), PR preview channels.

## 2. Flows and copy
- **In Telegram:** tap launch button (Q2) → app calls `miniApp.ready()` on first render → Home: greeting with `initDataUnsafe.user.first_name` (display only, **unverified**, never sent as identity) + a small status line from `GET /api/v1/health` (loading → `v0.1.0 · 13dfd1c` / offline). Home never blocks on the API; it paints first.
- **Skeleton UI-04 demo:** main button "Check connection" refetches health with `haptic.impact("light")`, then `notification("success"|"error")`. Back button hidden on Home (helper ready for Phase 1 screens).
- **Outside Telegram:** dev → mocked environment (§3); prod → localized "Open Tristhana from Telegram" screen, no API calls.
- **Copy** in `miniapp/src/locales/{en,ru}/app.ftl` (separate from bot.ftl, Q3; ux-writer polishes, RU informal «ты»): `home-greeting = Namaste, { $name } 🙏` / `Намасте, { $name } 🙏`; `home-greeting-anon`; `home-server-status = Server { $version } · { $commit }`; `home-server-loading`; `home-server-offline` ("Can't reach the server right now. Your data is safe; try again in a moment."); `home-check-connection`; `not-in-telegram`; `practice-days` (plural demo, used by ST-03 later: ru `[one] { $count } день [few] { $count } дня *[many] { $count } дней`, en `[one] … day *[other] … days`). Keys are prefixed by screen; `.ftl` comments give translator context.

## 3. Design
**Layout.** `src/main.tsx` (bootstrap) · `telegram/` (`init.ts`, `useBackButton`, `useMainButton`, `haptics.ts`: thin wrappers, no-ops when unsupported) · `theme/tokens.css` · `i18n/` (`negotiate.ts`, `L10nProvider.tsx`) · `locales/` · `api/` (`openapi.json`, `schema.d.ts` generated, `client.ts`) · `screens/Home.tsx`. No router yet (one screen).
**Telegram SDK.** `@telegram-apps/sdk-react` only; **no** `telegram-web-app.js` script (one less blocking request to telegram.org). Init mounts miniApp, themeParams, viewport, back/main button, binds theme and viewport CSS vars. Dev (`import.meta.env.DEV` and no launch params): `mockTelegramEnv` with fake launch params (user "Dev", light/dark theme, language from `?lang=ru`); the mock is tree-shaken from prod builds.
**Theme.** Semantic tokens (`--c-bg`, `--c-text`, `--c-hint`, `--c-link`, `--c-accent`, `--c-accent-text`, `--c-surface`) map to `--tg-theme-*` with `prefers-color-scheme` fallbacks. System font stack, no web fonts, no icon font. Plain Telegram-native look (Q5).
**i18n.** `@fluent/bundle` + `@fluent/react`; `negotiateLocale(code)` mirrors `domain/locale.py` (primary subtag; ru/be/kk/ky → ru, else en). Both sides test against one fixture `data/i18n/locale_cases.json` so they cannot drift. Both locales are bundled while small (< 10 KB raw each, via Vite `?raw`); split per locale once larger. Phase 1: the stored user locale from the backend overrides negotiation. Fluent's `useIsolating` stays on (bidi-safe).
**API client (ADR-0013).** Backend `tristhana-openapi` script writes the schema (sorted keys, stable) to `miniapp/src/api/openapi.json` (committed: the contract is reviewable in PRs). `npm run gen:api` = `openapi-typescript` → `schema.d.ts` (committed). `client.ts` = `openapi-fetch` `createClient<paths>({ baseUrl: import.meta.env.VITE_API_BASE_URL })` + TanStack Query hooks (`useHealth`). No `operationId` changes needed (openapi-fetch is path-based). ESLint `no-restricted-imports` keeps `schema.d.ts` usage inside `api/`. Freshness: backend CI fails if the dump differs from the committed json; miniapp CI fails if `gen:api` changes `schema.d.ts`.
**Origin and CORS.** Prod calls `*.run.app` directly (no Firebase rewrite proxy: no extra hop, the API stays hosting-independent). Backend `CORSMiddleware` from `CORS_ORIGINS` (comma-separated, exact origins, no wildcard), `allow_credentials=False` (bearer token later, no cookies), methods GET/POST/PATCH/DELETE, headers `Authorization, Content-Type`, `max_age=7200` so Phase 1's preflight costs one RTT per session. Empty → middleware not added. Dev needs none: Vite proxies `/api` → `localhost:8000` (`tristhana-dev`), `VITE_API_BASE_URL=""`.
**Performance (NF-09).** Initial JS budget **≤ 150 KB gzip** (expected ~100: React 19 ~45, SDK ~20, Query ~13, Fluent ~10, app), CSS ≤ 10 KB, checked by `scripts/check-bundle.mjs` (node zlib, no dependency). Heavy libs (ECharts, later) only via `React.lazy` routes. `<link rel="preconnect">` to the API origin (build-time env). Hosting headers: `index.html` `no-cache`, `/assets/**` `max-age=31536000, immutable`. Target `es2022`. Measure first load with DevTools "Fast 4G" + a phone in Telegram, warm and cold backend; record in `04 Architecture`.
**Dev in Telegram.** Daily work in the browser with the mock. For on-device checks: `cloudflared tunnel --url http://localhost:5173` (no account; Vite `server.allowedHosts`) set as @tristhana_dev_bot's Mini App URL. Cloudflare may be slow from RU; ngrok or a Firebase preview channel are alternatives.

## 4. Ops (☁️ owner only, PR B, in order)
1. Add Firebase to the existing project `braided-trees-444417-u6` (console "Add Firebase to Google Cloud project"; no Analytics). Create Hosting site (id Q6, e.g. `tristhana` → `https://tristhana.web.app`).
2. Grant the existing deployer SA `roles/firebasehosting.admin` (project-level; the narrowest Hosting role) via `infra/gcp/bootstrap.sh` (dry-run first). WIF provider unchanged (main only). Verify `firebase-tools` deploys with the WIF credential file; if not, fall back to the Hosting REST API.
3. Merge PR B: deploy sets `CORS_ORIGINS=https://<site>.web.app`; `miniapp.yml` deploy job runs on `main`.
4. BotFather, both bots: Mini App URL (prod: web.app; dev: tunnel) + launch style per Q2.

## 5. Migration
None (no DB). New npm deps only (lockfile committed, `npm ci`); backend gains no runtime deps (`CORSMiddleware` is Starlette).

## 6. Cross-cutting checks
- **Time zones:** no times displayed. Rule carried forward: every time gets a zone label (`07:00 Almaty (UTC+5)`), formatted via `Intl.DateTimeFormat` with an explicit IANA zone; a single `formatZoned` helper lands with the first time display (Phase 1).
- **Privacy/security:** `initDataUnsafe` used for display only; initData never logged or stored client-side beyond memory; no analytics, no third-party scripts or fonts; CSP via hosting header (`default-src 'self'; connect-src 'self' <api>`); exact-origin CORS without credentials; no secrets in the bundle (only `VITE_*` public config).
- **i18n:** all JSX text through `<Localized>`/`useLocalization` (enforced by `react/jsx-no-literals`); en/ru key parity test; RU plural test; fallback en.
- **Responsiveness:** paint before any API call; one request on load (health); TanStack Query `staleTime` avoids refetch on focus; haptics fire before the network call; < 150 KB initial JS.

## 7. Test plan
- **Unit (Vitest):** `negotiateLocale` against the shared fixture (also wired into backend pytest); every `.ftl` parses with no junk, en/ru key and variable sets equal; `practice-days` renders RU 1/2/5/11/21/22/25 and EN 1/2; theme token fallbacks; haptics/buttons wrappers are no-ops when unsupported.
- **Component (Testing Library, mocked SDK env + MSW or a stub fetch):** Home greets by first name (ru and en), anon greeting without user, health version/commit shown, offline copy on 503/network error, main button click refetches; outside-Telegram prod mode shows `not-in-telegram`.
- **Contract:** `tsc --noEmit` compiles `client.ts` against `schema.d.ts`; `gen:api` diff check (miniapp CI); `tristhana-openapi --check` (backend CI).
- **Backend:** CORS: allowed origin gets ACAO + preflight 200 with max-age; other origin gets none; empty setting adds no middleware; dump excludes `/telegram/webhook`.
- **Build:** `npm run build` + bundle budget in CI; Lighthouse/DevTools 4G run is manual (PR B).
- **CI `miniapp.yml`:** path filter `miniapp/**`, `data/i18n/**`, the workflow; Node 24 with npm cache; `npm ci` → lint → typecheck → test → gen:api check → build → budget; pinned action SHAs; deploy job (PR B) on `main` only.

## 8. Open questions for the owner
1. Hosting and deploy (Firebase on the existing GCP project `braided-trees-444417-u6`, CI deploy via WIF, CORS, BotFather URL) as PR B of this task, or a separate Phase 1 task? (Recommended: PR B now, so the skeleton opens in Telegram and RU reachability gets tested early.)
2. Launch style: BotFather "main Mini App" (Open button in the profile + chat), the menu button, an inline "Open app" button under `/start`, or a combination? (Recommended: main Mini App + menu button now; inline buttons in Phase 1 flows.)
3. Mini App copy in its own `miniapp/src/locales/{en,ru}/app.ftl` (recommended), or shared with the bot's `bot.ftl`?
4. Package manager: npm as in CLAUDE.md (recommended), or pnpm?
5. Visual direction for the skeleton: plain Telegram-native look using theme colors (recommended), or a branded look (accent color, logo)?
6. Hosting site id / URL: `tristhana.web.app` if free? Custom domain (`tristhana.app`) later or never?
7. Show the backend version/commit on Home for everyone, or only in dev / behind a long-press?

### Answers (owner, 2026-10-18)
1. Hosting and deploy: **PR B in this task** (Firebase Hosting on `braided-trees-444417-u6`, CI deploy via WIF, prod CORS, BotFather URL). ☁️ steps still need explicit approval.
2. Launch: **main Mini App + menu button + an inline "Open app" button under `/start`** (the button text lives in the bot's `.ftl`; the bot needs the Mini App URL as a setting, so it lands with PR B).
3. Mini App copy in its own `miniapp/src/locales/{en,ru}/app.ftl`. 4. **npm**.
5. **Telegram-native** look built from theme colors.
6. Hosting site `tristhana.web.app` if free; custom domain later.
7. Backend version/commit on Home **only in dev**, and behind a long-press in prod.
