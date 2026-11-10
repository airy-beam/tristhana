# Tristhana public site (UI-05)

The landing page and the user guides, in English (`/`) and Russian (`/ru/`). Astro + Starlight, static output. Spec: `docs/specs/UI-05-public-site-guides.md`, ADR-0043.

```sh
npm ci
npm run dev            # http://localhost:4321
npm run build          # → dist/
npm test               # label macros and guide-check
npm run check:guide    # guides vs the product and vs each other
npm run check:guide -- --write   # also refresh guide-map.yaml
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
