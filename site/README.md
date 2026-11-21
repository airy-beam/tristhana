# Tristhana public site (UI-05)

The landing page and the user guides, in English (`/`) and Russian (`/ru/`). Astro + Starlight, static output. Spec: `docs/specs/UI-05-public-site-guides.md`, ADR-0043.

```sh
npm ci
npm run dev            # http://localhost:4321
npm run build          # → dist/
npm test               # label macros and guide-check
npm run check:guide    # guides vs the product and vs each other
npm run check:guide -- --write   # also refresh guide-map.yaml
npm run check:guide -- --stale   # also list pages older than the specs of their features
npm run typecheck
npm run format:check   # fix with: npx prettier --write .
node scripts/check-dist.mjs      # after a build: no outside requests, page weight
```

## Writing a page

Pages live in `src/content/docs/` (English) and `src/content/docs/ru/` (Russian), same path and file name in both. Every page needs `title`, `description` and `features` (the requirement IDs it documents) in its front matter. A new page also goes into the sidebar in `astro.config.mjs`.

Never type a button label or a command by hand:

| Write                      | Get                                                             |
| -------------------------- | --------------------------------------------------------------- |
| `:ftl[city-ask-button]`    | the real label in the page's language, in bold                  |
| `:ftl[some-key]{n=3}`      | a message with arguments (numbers pick the right plural)        |
| `:ftl[some-key]{from=app}` | when the bot and the Mini App both have the key with other text |
| `:cmd[moon]`               | `/moon`, checked against the bot's commands (menu or hidden)    |

The keys come from `backend/src/tristhana/infrastructure/i18n/locales/` and `miniapp/src/locales/`. An unknown key or command fails the build and names the page.

Tone: friendly, simple, polite, informal. Russian uses «ты» and avoids gendered past tense. No "streak", "missed", "skipped", «серия».

## Deploy

A push to `main` that touches the site, a locale file or the bot's command menu runs `.github/workflows/site.yml`: the checks, then `firebase deploy` to the Hosting site `tristhana-guide`, served at https://tristhana.app (the site's own `tristhana-guide.web.app` address works too) and a smoke check. Nothing deploys from a pull request. The Hosting site and the deploy permission are created once by `infra/gcp/bootstrap.sh`.

## Keeping the guides current

Two Claude Code skills do the routine work: `/guide-update <ID>` after a feature changed what a person sees (pages in both languages, pictures, a What's new line, checks), and `/guide-check` to see what is out of step. `/feature` and `/wrapup` call on them.

## Screenshots

```sh
npm run shots                    # all of them, English and Russian
npm run shots -- --only PR-01    # by feature ID or by shot name
npm run shots -- --lang ru       # one language only
```

Needs the local Postgres container (`tristhana-pg`), `uv` and Google Chrome. The script builds a private demo copy of the product and throws it away afterwards: its own database (`tristhana_demo`, dropped and re-created on every run), a backend on port 8010 that never reads `backend/.env` and has no real bot token, and a Mini App dev server on port 5183. Your own dev instance on port 8000 is not touched.

- The list is `shots/manifest.yaml`; the comments at its top explain each field. A step is a Fluent key, `=student`, `=teacher` or `=shala` for a name from the demo cast, or `#2` for the second button of a bot message. An app shot's steps start from the Today tab, so most begin with a tab (`tab-practice`, `tab-shala`); a control with no visible words, like the gear (`settings-open`), is found by its accessible name. A thing with no label of its own, like a class on the shala's week, is a `css=<selector>` step. `top` is one more step: the picture begins at that thing, for something opened far down a long screen. `=invite` in a bot shot's `say` is the demo teacher's invite code.
- The demo people and what they logged are in `shots/lib/cast.mjs` and `shots/lib/seed.mjs`. Everything is entered through the real REST API and the real bot webhook.
- Mini App pictures are a phone-sized Chrome looking at the real app. Bot pictures are drawn from the bot's real reply (text and buttons) in the site's own style; they are drawings, and the guide says so.
- Dates in the pictures follow the day you run it, so a full re-run changes every file. Use `--only` after a feature change.
- Card examples (`src/assets/cards/<lang>/`, ST-10) are not screenshots: the backend's card renderer draws them, `cd backend && uv run python ../tools/cards/render_guide_examples.py`. Re-run it after a card's look changes.
- Files land in `src/assets/shots/<lang>/<name>.webp` and are committed. A page shows one as `![what it shows](../../../assets/shots/en/<name>.webp)` (one more `../` under `ru/`). `npm run check:guide` fails on a shot that is unlisted, unused, in the wrong language, missing or over 120 KB.
