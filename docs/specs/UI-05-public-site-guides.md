# UI-05: public site, a landing page and user guides in RU and EN

- Status: **accepted** (owner, 2026-11-11: the three scoping questions, then §9 all as recommended; Q-E left open) · Date: 2026-11-11 · Size **L** (~5–7 days, mostly content), Phase 3 (public launch)
- Requirements: **UI-05** (new: public landing page and user guides for students, teachers and shala staff, RU + EN, with screenshots, kept current by skills). Touches the launch item in the roadmap (landing page, BotFather description and screenshots), NF-02 (deploy), NF-09 (first load).
- Related: ADR-0011 (deploy, one GCP project), ADR-0013 (Firebase Hosting for the Mini App). **ADR-0043** (accepted): a second Hosting site, Astro Starlight, quoted labels, generated screenshots.
- Owner decisions so far: a **second Firebase Hosting site** in the same project (custom domain later); **all screenshots automated** (Mini App driven by a script, bot chats drawn from real screens); **all three guides at launch, RU + EN**.

## 1. Scope
**In:** a static site in a new `site/` folder: landing page, "Start here", guides for students, teachers and shala staff, a reference section, "What's new"; RU and EN mirrored page for page; generated screenshots in both languages; CI checks and deploy; two skills (`guide-update`, `guide-check`) and one new step in the `feature` skill; links to the site from the bot (`/help`) and the Mini App (Settings).
**Out:** a blog, analytics or cookies of any kind, comments or a contact form, accounts or login on the site, the asana guide (AC-04), video, more languages, a custom domain (Q-B), a web version of the app. No backend use case, API or migration changes, except the dev-only demo seed (§5).

## 2. Structure
EN lives at `/`, RU at `/ru/`; the same slugs in both. A language switch is on every page. The landing page offers the other language once, by a visible link, never by a redirect.

| Section | Pages |
|---|---|
| **Landing** | What Tristhana is in one screen · three cards (I practise / I teach / I run a shala) · privacy in three lines · moon days in one paragraph · "Open in Telegram" · open source (AGPL, GitHub) |
| **Start here** | First steps in 2 minutes (`/start`, language, the first log) · The bot and the app: which is for what |
| **For students** | Log a practice · Rest days, moon days and 🌸 · Reminders · My practice: calendar, month, badges, share cards · My asanas · Check-in and diary · My teacher · My shala: schedule, calendar, attendance · Settings and your city · Your data: privacy, export, delete |
| **For teachers** | Become a teacher and invite students · What you see, and what you never see · Mark a new asana · Announcements · Moon days your students follow · The SYC directory line |
| **For shala staff** | Create a shala and invite staff · Classes and the week · Closures, swaps and substitutes · Attendance · Announcements |
| **Reference** | FAQ · All bot commands · Privacy in plain words · How moon days are calculated · What's new |

About 27 pages per language.

**Page pattern** (every guide page): one sentence on what this is for → numbered steps, with "In the bot" / "In the app" tabs where both exist → one to three screenshots → "Good to know" (limits, privacy) → "Next" link. A page answers one task and fits in about two phone screens.

**Rules for the text**
- Tone: friendly, simple, polite, informal. RU «ты», no gendered past tense. EN: short sentences, "you". Same banned words as the product: no streak / missed / skipped / «серия».
- Button and command names are never typed by hand. A page writes `:ftl[start-open-app]` and the build puts in the real label from the `.ftl` files in that language (§4). If a label changes, the guide follows. If a key disappears, the build fails.
- 🌸 is described once, on "Rest days, moon days and 🌸", plainly and with the privacy line first. It is not on the landing page.
- Moon-day and practice wording is reviewed by the ashtanga-expert; all copy by the ux-writer.
- Privacy statements say only what the code enforces today, and "What you never see" for teachers mirrors the ST-06 projection.

## 3. Technology
- **Astro + Starlight** in `site/` (its own `package.json`, Node 24). Markdown/MDX content, built-in i18n with a fallback notice, sidebar, tabs, local search (Pagefind, no third party). Output is static HTML with almost no JavaScript. The landing page is a custom Starlight page using the brand palette from `docs/brand/` (indigo, saffron, paper) and system-safe fonts with Cyrillic (Lato and Noto Serif Display self-hosted, subset).
- **Hosting:** a second Firebase Hosting site in project `braided-trees-444417-u6` (name: Q-A). `site/firebase.json` has its own strict CSP (`default-src 'self'`, no API origin, `frame-ancestors 'none'`), immutable cache for hashed assets and screenshots, `no-cache` for HTML.
- **CI:** new `.github/workflows/site.yml`, path-filtered to `site/**`, `backend/src/tristhana/**/locales/**` and `miniapp/src/locales/**`: build, link check, `guide-check` script (§6), deploy on `main` through the existing WIF deployer, smoke check. ☁️ one owner step: create the Hosting site (and let the deployer deploy to it, if the role isn't project-wide).
- **Budgets:** landing page ≤ 150 KB transferred without screenshots; each screenshot ≤ 60 KB (WebP, 2× of a 390-wide phone frame, lazy-loaded with fixed width and height); guide page first load < 2 s on 4G (NF-09).
- **No tracking:** no analytics, no cookies, no external requests. Search engines may index it (`sitemap.xml`, `hreflang` pairs, Open Graph image from `docs/brand/`).

## 4. Label and command macros
Markdown text directives, resolved at build time by a Sätteri plugin (`site/src/lib/directives.mjs`, logic in `labels.mjs`):
- `:ftl[key]` → the message from the bot's or Mini App's `.ftl` for the page's language, in bold. Arguments: `:ftl[key]{n=3}` (numbers pick the plural); a missing argument fails the build. If the bot and the app both have the key with different text, the page says which: `{from=bot}` or `{from=app}`. Multi-line messages are refused (they are not labels).
- `:cmd[log]` → `/log`, checked against the command list `tools/telegram/set_webhook.py` registers. `/admin` is never documented (ADR-0042).

(The first draft wrote `{ftl:key}`; braces are expressions in MDX, so the built syntax is the directive form.) This is the main defence against guides going stale.

## 5. Screenshots
All generated, stored as files in `site/src/assets/shots/{en,ru}/<name>.webp`, committed (CI does not regenerate them; it only checks every referenced file exists). One manifest, `site/shots/manifest.yaml`, lists each shot: name, kind (`app` or `bot`), how to reach it, which guide pages use it, which feature IDs it belongs to.

- **Demo data:** a dev-only command `uv run tristhana-demo-seed` fills the local dev DB (refuses unless `APP_ENV=dev`) with a fixed cast: a student "Maya" with three months of logs, a teacher "Arjun" with five students, a shala "Morning Mysore" with a week of classes. Invented names, no real people, fixed dates relative to a pinned "today", so shots are stable. It goes through the real use cases, so encrypted fields are sealed normally.
- **Mini App shots:** `site/shots/app.mjs` (Playwright, dev dependency of `site/` only) opens `npm run dev` with the mocked Telegram (`?lang=`, light theme, the demo account), walks to each screen from the manifest and saves a 390×844 capture, cropped to the element when the manifest says so. The clock is pinned.
- **Bot shots:** `uv run python tools/guide/bot_shots.py` calls the real screen builders (`Screen(text, markup)`) for the demo accounts through the real use cases, and writes each as a small HTML chat bubble with its inline keyboard; the same Playwright run captures them. The bubble style is neutral and plainly a drawing (a caption on first use: "Pictures of the bot are drawn from its real messages"), not a copy of Telegram's UI. This lives outside `bots/telegram/` only as a caller; `aiogram` stays imported there alone (the tool asks a thin `bots.telegram` helper for `(text, rows of button labels)`).
- **Privacy:** only the seeded demo cast ever appears. Feed links, invite codes and share-card tokens in shots are fake fixed values.
- One command regenerates everything: `cd site && npm run shots` (needs the local Postgres, the dev backend and the Mini App dev server; the script starts and stops the last two). `npm run shots -- --only <name|feature-id>` for a subset.

## 6. Keeping it current
- **Feature map:** `site/guide-map.yaml`: feature ID → pages and shots (e.g. `SC-05: [students/my-shala, staff/attendance]`). Every page's front matter lists its feature IDs; the map is generated from that and checked in.
- **Skill `guide-update <ID or "all">`** (`.claude/skills/guide-update/`): read the feature's spec and diff → find its pages in the map (or propose a new page and its place in the sidebar) → update EN and RU together (ux-writer; ashtanga-expert when domain wording changes) → re-shoot the affected shots → add a "What's new" entry in both languages → run `guide-check` → show the owner the changed pages before any commit.
- **Skill `guide-check`** (`.claude/skills/guide-check/`, runs `site/scripts/check.mjs`, also in CI): every EN page has an RU twin with the same headings count and the same shots; every `{ftl:}` and `{cmd:}` resolves; every menu command is documented somewhere; every shot in the manifest is used and exists in both languages; no page is older than the newest change to a spec it maps to (warning only, listed for the owner); internal links work.
- **`feature` skill:** step 5 gains one line: "If the feature changed what a person sees, run `guide-update <ID>`."
- **`wrapup` skill:** mentions pending guide warnings from `guide-check`.

## 7. Links into the product
- Bot `/help`: one URL button "📖 Guide" / «📖 Справка» to the site in the person's language (new `.ftl` keys, new setting `PUBLIC_SITE_URL`; empty = no button).
- Mini App Settings: a "📖 Guide" row opening the link with Telegram's `openLink`. Also on the `NotInTelegram` screen.
- BotFather description, about text and the three promo screenshots are prepared in `docs/brand/` from the same shots; the owner sets them (☁️).

## 8. Delivery plan
1. **Skeleton:** `site/` with Starlight, landing page draft, sidebar with empty pages, macros plugin, `check.mjs`, CI build (no deploy yet). ADR-0043.
2. **Demo seed + shot pipeline** with three proof shots (one app, one bot, one RU).
3. **Student guide** EN + RU, with shots. Owner reads it.
4. **Teacher and staff guides, reference, What's new** (backfilled from the roadmap, short).
5. **Skills** and the `feature` / `wrapup` edits.
6. **Deploy** (☁️ owner creates the site), links from the bot and the Mini App, BotFather texts.

Each step is its own PR.

## 9. Questions for the owner (answered 2026-11-11: all as recommended; Q-B is decided after step 3, Q-E stays open and the site shows only the bot and GitHub links until then)
- **Q-A Site name.** `tristhana-guide.web.app` (recommended: says what it is, leaves `tristhana.web.app` to the app) or another name? It is permanent until a custom domain.
- **Q-B Custom domain.** Attach `tristhana.app` before the launch posts go out, or launch on `web.app`? Recommended: decide after step 3; old links keep working either way.
- **Q-C Landing language.** EN at `/`, RU at `/ru/` (recommended, standard), or RU first since the beta group is Russian-speaking?
- **Q-D Demo cast.** Names "Maya", "Arjun", shala "Morning Mysore" in a demo city Almaty. OK, or other names?
- **Q-E Contact.** Does the site show a way to reach you (a Telegram group or channel link), and which?
- **Q-F Light only.** Screenshots in the light theme only (recommended: half the files), site itself follows the reader's light/dark setting.

## 10. Tests
- `site`: build passes; `check.mjs` unit tests (missing twin, unknown `{ftl:}` key, missing argument, undocumented command, orphan shot); macro plugin tests in both languages incl. a message with variables.
- Backend: demo seed refuses outside dev; seeds twice without duplicates; the bot-shot helper returns text and button labels for one screen per module.
- CI: link check, shot files exist, budgets (page weight, shot size).
- Manual: the owner reads every page on the phone in both languages; the ux-writer and ashtanga-expert review before step 6.
