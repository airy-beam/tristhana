---
name: guide-check
description: Check the public guides in site/ (UI-05). Finds pages that differ between English and Russian, labels and commands that no longer exist, undocumented commands, screenshot problems, and pages that may be behind the product. Use before committing guide changes, at wrap-up, or when asked whether the guides are up to date.
---
# Guide check
Read-only unless the user asks for a fix. Run everything from `site/`.

1. **Structure.** `npm run check:guide -- --stale`
   - Lines with `✗` are problems and fail CI: a page without its twin, different headings, pictures or quoted labels in the two languages, a bot menu command no page mentions, a screenshot that is unlisted, unused, missing, in the wrong language or over 120 KB, or a stale `guide-map.yaml` (refresh it with `npm run check:guide -- --write`).
   - Lines with `?` are hints, not failures: the spec of a feature changed after its page did. Read the spec's diff (`git log -p -1 -- docs/specs/<ID>-*.md`) and say whether a person would see a difference. If yes, the fix is `/guide-update <ID>`.
2. **Labels and commands.** `npm run build`. An unknown `:ftl[key]` or `:cmd[name]` stops the build and names the page and the key. A renamed key is usually a one-word fix in both twins; a removed button means the step is gone, so the page needs `/guide-update <ID>`.
3. **Built site.** `node scripts/check-dist.mjs` (no requests to other sites, landing page under its size budget).
4. **Features with no page.** Compare `site/guide-map.yaml` with the ✅ items in `/home/pumpkin_vibe/Documents/pumpkin_notes/02_projects/tristhana_bot/09 Roadmap.md`. List requirement IDs that changed what a person sees and are not in the map. Ignore infrastructure IDs (NF-*, AC-01) and `/admin` (never documented, ADR-0042).
5. **Report** a short table: problem · page or picture · suggested fix. Then one line: "Guides OK" or how many problems and hints. Offer `/guide-update <ID>` for content, and fix mechanical things (the map, a renamed key) only when the user says so.

Do not start the screenshot pipeline here; it belongs to `/guide-update`.
