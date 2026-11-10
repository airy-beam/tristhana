# ADR-0043: The public site is a second Hosting site built with Astro Starlight; guides quote the product's Fluent messages and use generated screenshots
- Status: accepted (owner, 2026-11-11)
- Date: 2026-11-11
## Context
UI-05 (spec `docs/specs/UI-05-public-site-guides.md`) adds a landing page and user guides for students, teachers and shala staff, in RU and EN, for the public launch. The Mini App already owns the root of `tristhana.web.app`, and BotFather points there. Guides go stale quickly in a product that ships several features a week, and the owner wants them refreshed by a skill, with screenshots.

Owner decisions (2026-11-11): a second Firebase Hosting site in the same project; all screenshots automated; all three guides at launch in both languages; site name `tristhana-guide.web.app`; EN at `/`, RU at `/ru/`; light-theme screenshots only; a custom domain is decided later.
## Decision
- **Where:** a separate static site in `site/`, deployed to its own Hosting site `tristhana-guide` in project `braided-trees-444417-u6`, with its own workflow `.github/workflows/site.yml`. It shares nothing at runtime with the Mini App or the API.
- **How it is built:** Astro + Starlight (Markdown/MDX content, built-in i18n, sidebar, local Pagefind search). Versions are pinned exactly. Markdown runs through Astro's default Sätteri processor with one plugin of ours.
- **Labels are quoted, not typed:** guide pages write `:ftl[key]` (optionally `{arg=value}` and `{from=bot|app}`) and `:cmd[name]`. The plugin (`site/src/lib/directives.mjs`) resolves them at build time from the bot's and the Mini App's own `.ftl` files in the page's language, and from the command tuple in `tools/telegram/set_webhook.py`. An unknown key, a missing argument, a key whose text differs between bot and app without `from`, or a command outside the menu fails the build. `/admin` can never be documented this way (ADR-0042).
- **Twins are checked:** `site/scripts/check.mjs` (guide-check, also in CI) requires every page in both languages with the same features, heading count, screenshots and quoted keys, every menu command documented somewhere, and a fresh `site/guide-map.yaml` (feature ID → pages, generated from each page's `features` front matter).
- **No outside requests:** system fonts, no analytics, no cookies, no CDN. `site/scripts/check-dist.mjs` fails the build if a page loads anything from another origin, and holds the landing page under 150 KB gzip. Hosting sends a strict CSP.
- **Screenshots are generated and committed** (spec §5): the Mini App is driven by a script against a seeded demo cast; bot pictures are drawn from the real `Screen(text, markup)` objects and captioned as drawings. CI only checks that referenced files exist.
- **The workflow also runs when a locale file or the command list changes**, so a product change that breaks a guide fails on its own PR.
## Consequences
- The Mini App's deploy, CSP and bundle budget are untouched; the site can move to a custom domain without the app noticing.
- A removed or renamed Fluent key now has one more consumer. The failure is early and names the guide page. A changed label text needs no guide edit at all.
- The directive syntax differs from the spec's first draft (`{ftl:key}`): braces are expressions in MDX, and text directives are already parsed by the Markdown pipeline Starlight uses.
- Sätteri is new (Astro 6.4+). If its plugin interface changes, one small file changes; the label logic itself (`labels.mjs`) has no Astro dependency and is unit-tested.
- Messages that need the backend's custom Fluent types (dates and times formatted in Python) cannot be quoted; guides describe those in words.
- Screenshots need a local Postgres, the dev backend and the Mini App dev server to regenerate, so they are refreshed by a person or a skill, never by CI.
- One more `npm ci` in the repo and one more set of pinned dependencies to keep current.
## Alternatives considered
- **Under `/guide` on the Mini App's site:** no new site, but it couples two deploys and two CSPs, and the landing page could not be the root.
- **Hand-written HTML or the brand stories' approach:** no dependency, but i18n fallbacks, sidebar, search and accessible navigation would all be ours to build for ~28 pages per language.
- **VitePress / Docusaurus:** comparable; Starlight ships less JavaScript and has per-locale routing with root-locale support out of the box.
- **Typing labels by hand and checking with a linter:** two copies of every label remain, and the check can only warn after the fact.
- **Telegram Instant View or a Telegram channel as the guide:** not indexable in the same way, no structure, RU/EN mixing.
