# ADR-0050: One word per thing: the glossary is a data file, and tests ban retired words in both products and the guides
- Status: accepted (owner, 2026-11-18, with the UI-06 stage 5 spec, Q361–Q366)
- Date: 2026-11-18
## Context
UI-06 stage 5 (spec `docs/specs/UI-06-stage-5-words.md`) settles the product's words before launch. The ux-writer found the same thing named differently and different things named the same (Q330, Q342), and the bot and the Mini App keep separate copies of many messages under the same key. Two narrow tests already keep some copies equal (the Settings rows, UI-06 stage 3; the request and consent messages, ADR-0049). The tone rule ("never streak, missed, skipped, «серия», «пропуск»") lives only in `.ftl` comments and `site/README.md`. Guides quote labels by key (ADR-0043), so a changed text reaches them for free, but their own prose is unchecked. Without enforcement the words drift again with the next feature.
## Decision
- **`docs/glossary.yaml` is the glossary.** One entry per concept: `en`, `ru`, `where` (screens or key prefixes), `retired` (per language: words or regexes that must not name this concept), optional `except` (keys allowed to keep a retired word or a short form, each with a reason; e.g. the Mini App's tab label "📊 Practice" for the place called "My practice", because a 320 px tab cannot hold the long form), optional `expert: true` (an Ashtanga-domain word; changed only after the ashtanga-expert agrees). A top-level `banned` list holds words that are never allowed (the tone rule), per language.
- **Tests read it** (`site/src/lib/words.test.mjs`, in the site suite, which already loads every bot and Mini App `.ftl` and runs when a locale file changes; its workflow also watches `docs/glossary.yaml`):
  1. no message text in `bot.ftl`, `card.ftl` or any Mini App `.ftl`, en or ru, contains a retired or banned word of its language, outside `except`. Only what a person reads is scanned: message values and attributes with placeables removed; never ids, comments, variant keys or variable names (so `status-skipped` and `[skipped]` are fine). Where a retired word is also a domain word, the rule names the phrase, not the word: RU «серия» (series) is banned only in run phrases («серия дней», «серия практик», «прервать / сохранить серию», with «дней подряд»), and RU «класс» only as a word of its own, never after a hyphen, so «Лед-класс» and «майсор-класс» pass without an `except`;
  2. the same for guide pages (`site/src/content/docs/**`): prose, titles and descriptions, without `:ftl[…]`, `:cmd[…]`, code, links and image paths; file names and URLs are not words and stay;
  3. **a key present in both products renders the same text** for a sample of every variable, en and ru, unless it is listed in `same-key-different-text` in the glossary file with a reason (a heading without the bot's emoji, a bot line that carries a value the app shows elsewhere). The two existing words-in-step tests stay as they are.
- **Key renames only when the meaning changes.** A new word for the same thing is a text change under the same key; guides and screenshot steps follow by themselves.
- **Consent texts may change words, not promises** (ADR-0045 "presentation only", as ADR-0049 did for "/teachers"): same callbacks, same consent id, the byte-for-byte tests updated in the same commit, the changed sentences shown to the owner.
## Consequences
- A new string with a retired word fails CI on its own pull request and names the key or page; the reviewer no longer has to remember the list.
- The drift between bot and app becomes a visible, shrinking allow-list instead of a surprise in a screenshot.
- One more file to keep current: a new concept with a new word is a glossary line in the same pull request. The ux-writer reads the file before writing copy.
- Regexes per language can give false positives (RU inflections, a domain word that is also a retired word elsewhere); `except` with a reason is the outlet, and a review sees it.
- The site suite now guards product copy, so a bot-only change that adds a retired word fails the site check, not the backend one. Both run on such a pull request (ADR-0043's path filter).
## Alternatives considered
- **A Markdown table only.** Readable in Obsidian, enforces nothing; the stage 1 collisions came from exactly that.
- **A pytest in the backend.** Sees `bot.ftl` but not the Mini App's files or the guide pages without duplicating the site's Fluent reader.
- **One shared `.ftl` source for bot and app.** Removes copies at the root, but the app splits messages into lazy files per chunk (ADR-0047) and the bot formats dates in Python; a large build change for a wording stage.
- **A linter warning instead of a failing test.** Warnings are read once and then ignored.
