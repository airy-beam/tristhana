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
| `:ftl[start-open-app]`     | the real label in the page's language, in bold                  |
| `:ftl[some-key]{n=3}`      | a message with arguments (numbers pick the right plural)        |
| `:ftl[some-key]{from=app}` | when the bot and the Mini App both have the key with other text |
| `:cmd[log]`                | `/log`, checked against the bot's command menu                  |

The keys come from `backend/src/tristhana/infrastructure/i18n/locales/` and `miniapp/src/locales/`. An unknown key or command fails the build and names the page.

Tone: friendly, simple, polite, informal. Russian uses «ты» and avoids gendered past tense. No "streak", "missed", "skipped", «серия».

## Keeping the guides current

Two Claude Code skills do the routine work: `/guide-update <ID>` after a feature changed what a person sees (pages in both languages, pictures, a What's new line, checks), and `/guide-check` to see what is out of step. `/feature` and `/wrapup` call on them.

## Screenshots

```sh
npm run shots                    # all of them, English and Russian
npm run shots -- --only PR-01    # by feature ID or by shot name
npm run shots -- --lang ru       # one language only
```

Needs the local Postgres container (`tristhana-pg`), `uv` and Google Chrome. The script builds a private demo copy of the product and throws it away afterwards: its own database (`tristhana_demo`, dropped and re-created on every run), a backend on port 8010 that never reads `backend/.env` and has no real bot token, and a Mini App dev server on port 5183. Your own dev instance on port 8000 is not touched.

- The list is `shots/manifest.yaml`; the comments at its top explain each field. A step is a Fluent key, `=student`, `=teacher` or `=shala` for a name from the demo cast, or `#2` for the second button of a bot message.
- The demo people and what they logged are in `shots/lib/cast.mjs` and `shots/lib/seed.mjs`. Everything is entered through the real REST API and the real bot webhook.
- Mini App pictures are a phone-sized Chrome looking at the real app. Bot pictures are drawn from the bot's real reply (text and buttons) in the site's own style; they are drawings, and the guide says so.
- Dates in the pictures follow the day you run it, so a full re-run changes every file. Use `--only` after a feature change.
- Files land in `src/assets/shots/<lang>/<name>.webp` and are committed. A page shows one as `![what it shows](../../../assets/shots/en/<name>.webp)` (one more `../` under `ru/`). `npm run check:guide` fails on a shot that is unlisted, unused, in the wrong language, missing or over 120 KB.
