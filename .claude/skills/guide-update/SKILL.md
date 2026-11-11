---
name: guide-update
description: Bring the public guides in site/ (UI-05) up to date after a feature changed what a person sees. Updates the English and Russian pages together, re-shoots the affected screenshots, adds a "What's new" entry and runs the checks. Use after a feature is built (e.g. /guide-update SC-04), or with "all" after several changes.
argument-hint: <REQ-ID …> | all
---
# Guide update for: $ARGUMENTS

The guides live in `site/src/content/docs/` (English) and `site/src/content/docs/ru/` (Russian, same paths). Read `site/README.md` once for the writing rules and the screenshot pipeline. Keep the user informed with one line per step.

## 1. Find what changed
- For each ID: read `docs/specs/<ID>-*.md`, the feature's diff (`git log --oneline --grep "<ID>"`, then the diffs) and the `.ftl` keys it added, renamed or removed.
- With `all`: run `/guide-check` first and take its `✗` and `?` lines and its "features with no page" list as the work list.
- Write down, in one or two lines per ID, **what a person now sees or does differently**. If nothing, say so and stop: internal changes need no guide change.

## 2. Find the pages
- `site/guide-map.yaml` maps each ID to its pages. Pictures are listed with their IDs in `site/shots/manifest.yaml`.
- An ID with no page: propose where it goes. Prefer a new section on an existing page; a new page needs a file in both languages, a line in the sidebar in `site/astro.config.mjs`, and the ID in its `features` front matter. A new audience or section is the owner's call: ask.
- Never document `/admin` (ADR-0042).

## 3. Update English and Russian together
- Page pattern: one sentence on what this is for → numbered steps → one to three pictures → "Good to know" → "Next". One task per page, about two phone screens.
- Button, label and command names are never typed by hand: `:ftl[key]`, `:ftl[key]{arg=value}`, `:ftl[key]{from=bot}` and `:cmd[name]`. The twins must have the same headings count, pictures and directives.
- Tone: friendly, simple, polite, informal. Russian uses «ты», no gendered past tense, and the product's own words («занятие», «команда шалы», «лед-класс»). Never "streak", "missed", "skipped", «серия», «пропуск». 🌸 stays discreet.
- Privacy and "who sees what" lines say only what the code enforces today; check `backend/src/tristhana/application/policies.py` and the ADRs, not memory.
- Ask the **ux-writer** agent to review the changed pages in both languages (report only), and the **ashtanga-expert** agent when the change touches practice, rest, moon days, progression or roles. Apply their findings to both twins.

## 4. Pictures
- Add or change entries in `site/shots/manifest.yaml`. If a new screen needs data, extend `site/shots/lib/seed.mjs` (and its test) through the product's real API or bot, never the database.
- Re-shoot only what changed: `cd site && npm run shots -- --only <ID or name>`. It needs the `tristhana-pg` container and Chrome, takes about a minute, and starts its own demo copy on ports 8010 and 5183; the owner's dev instance is not touched. Do not run it while a backend or Mini App test suite is running.
- Look at every new picture before using it (text cut off, wrong language, another person's name, an error screen).
- A full run (`npm run shots`) changes every file because dates follow the day. Do one only when the user asks.

## 5. What's new
Add one line for each change a person would notice to `reference/whats-new.md` in both languages, under the current month's heading (add the heading if the month is new). Plain words, no IDs.

## 6. Check
From `site/`: `npx prettier --write src/content/docs` · `npm run check:guide -- --write` · `npm test` · `npm run typecheck` · `npm run build && node scripts/check-dist.mjs`. Fix until all pass.

## 7. Show the owner
List the changed pages with their local addresses (`npm run dev`, then `http://localhost:4321/<slug>/` and `/ru/<slug>/`), the new pictures, anything left as a question, and the check results as they are. Suggest a commit message (`UI-05: update the guide for <ID>`). Commit only when the user asks; the site deploys from `main`.
