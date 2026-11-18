# UI-06 stage 5: one word per thing in both languages; guides, screenshots, notes

- Status: **accepted** (owner, 2026-11-18: QA–QF in §11 all as recommended, "All yes"; in the notes QA = Q361, QB = Q362, QC = Q363, QD = Q364, QE = Q365, QF = Q366; revised before that with the ux-writer's and ashtanga-expert's reviews) · Size **L** (copy everywhere, little code), one pull request, branch `ui-06/stage-5-words` from `main` at `33e7e6e` · the last stage of UI-06
- Parent: `docs/specs/UI-06-simple-journey.md` (§1 row 5, §7 "i18n", §10 "Stage 5"). Requirements: **UI-06**; touches UI-05 (guides), PR-02/03/06/07/10, ST-01, SC-02/03/06, ID-04/06/07, MD-02/03.
- Inputs: Q330, Q341 (leftovers), Q342, Q352a, Q360b. Related: ADR-0007, 0043, 0044, 0045, 0049. New, proposed: **ADR-0050** (glossary as data, retired words banned by test).

## 1. Goal and scope
**Goal:** a person who has never used an app reads one word for one thing, the same in the bot, the Mini App and the guides, in English and in Russian; no text tells them to type a command.
**In:** the glossary (§3) and its tests (§5); text changes in `bot.ftl`, `card.ftl` and the Mini App's `.ftl` (en + ru); four small presentation fixes (§4); the RU month title; guides, What's new, a full screenshot re-run, notes.
**Out:** new features, screens, API, domain or use-case changes, migrations; any callback data (CLAUDE.md stale-button rule); what a teacher or shala sees; the export file's field names (data, not UI); guide URLs and file names (`students/check-in-and-diary` keeps its slug; its title changes). **Key renames only where a meaning changes** (one: §4.6).

## 2. What the sweep found (beyond Q330's list)
1. **"Other…" for four more things:** `preset-other` opens the same picker as My asanas' `progression-choose` "Choose…"; `day-off-ask-other` (RU «Другой…»; «Другой день» would clash with `log-another-day`); the bot's `pause-other` "Other…" where the app already says "Another number…" (the reason is in the app's comment); `class-form-length-other` "Other".
2. **Same key, different thing:** `students-day-blank` (bot "·"; app "nothing to show", while the app's `students-day-blank-mark` is the bot's text); `remind-days-follow` (different sentence and variables); `moon-teacher-shared` (bot "in /moon", app "choose your own city"); `moon-same-as-city` (📍 only in the bot).
3. **Same text, different thing (RU):** `class-form-more` «Ещё настройки» = Settings' `settings-more-title`; «отметка» for a logged day, an attendance mark, a teacher's asana mark **and** a check-in (`settings-checkin-hint`).
4. **Link sending:** the teacher invite says `invite-send` "✉️ Send the link"; the shala invite (bot) and the app's invite card say `invite-share` "📤 Share"; `shala-join-hint` / `invite-hint` "Share this link". "Share" also names share cards (pictures).
5. **EN "check-in"** survives in `checkin-clear`, `checkin-save-failed`, `trends-open`, `trends-title`, `settings-checkin-hint`, `delete-explain`, `settings-privacy-sharing` and four consent texts; RU says «самочувствие» everywhere.
6. **"diary"** in `diary-saved`, `diary-removed`, `diary-title`, `diary-private-hint` and the consents ("diary notes"), beside the button "📓 Note".
7. **"time zone" / «часовой пояс»** in `log-date-future`, `moon-use-city-zone`, `settings-share-location`, `settings-location-zone`, `settings-location-unknown`, `students-days-note`, `moon-zone-needed-app`.
8. **Commands in running text:** 19 bot messages name `/moon`, `/remind`, `/settings`, `/teachers` or `/start`, including the **invite, shala-join and staff consents, both layers** (`invite-consent`, `shala-join-consent`, `shala-staff-consent` and their `-short`); `delete-done` "Send /start". `admin-listing-new` "/admin" is the admin's own note (kept).
9. **Undeclined RU names:** `schedule-covering-for` «(за { $teacher })», `my-classes-covering` «ты заменяешь { $name }» (Q341's).
10. **EN "Details"** is both `practice-details` and `consent-details` (RU already differs: «Детали» / «Подробнее»).
11. **Remove / delete:** EN "Remove note" is RU «Удалить заметку», while every other own-entry removal is «Убрать».

## 3. Glossary (proposed; becomes `docs/glossary.yaml`, ADR-0050). **Bold** = a change.
| Concept | EN | RU | Where | Retired |
|---|---|---|---|---|
| The calendar and numbers place (QA) | My practice (heading, Menu row, 🌸 switch); the tab keeps the short form **📊 Practice** | Моя практика; tab **📊 Практика** | `stats-title`, `menu-practice`, `stats-show-ladies`; `tab-practice` in `except` (a 102 px tab: «📊 Моя практика» would be cut at 320 px) | – |
| A logged practice | 🧘 Practiced (legend: Practice) | 🧘 Практика (legend: Практика) | `status-practiced`, legend | – (Q342: kept; 📊 and 🧘 tell the place from the status) |
| The student's own practice, how far it goes (ashtanga-expert: kept) | My practice: … / Your practice: … | Моя практика: … / Твоя практика: … | `preset-mine`, `progression-current` | – (the Ashtanga sense; My asanas is one tap from the Practice tab, the first row under the month in `Stats.tsx`) |
| How far in the series (QD) *(for ashtanga-expert)* | **📏 How far** | 📏 Объём практики | `practice-length` | EN "Length" |
| Minutes (QD) | **⏱ How long** | **Длительность** (details and class form) | `practice-duration`, `class-form-length` | EN "Duration", "Length" for minutes · RU «Сколько длится» |
| The record of days | log | журнал | everywhere | – |
| Private text on a day | 📓 Note (**`diary-saved` "📓 Note saved", `diary-removed` "Note removed"**) | 📓 Заметка (**«📓 Заметка сохранена», «Заметка убрана»**) | `diary-*`, consents, More | **EN "diary" · RU «дневник»** |
| How you feel after practice | ✨ How do you feel? (noun: **how you feel**); **`checkin-clear` "Remove answers"; `trends-open` / `trends-title` "✨ How you've felt"** | ✨ Как самочувствие? (самочувствие); **«Убрать ответы»**; «✨ Самочувствие за год» (kept) | `checkin-*`, `trends-*`, Settings, consents | **EN "check-in(s)"** · RU «отметка» for it; **`settings-checkin-hint` names the app's chips Mood / Body / Mind** (Настроение / Тело / Ум), not "mood, energy and effort" |
| Practice details | 📝 Details · 📝 Add details | 📝 Детали | P0/P1, day card | – |
| A consent's full text | **📄 Read in full** | 📄 Подробнее | `consent-details` (bot + `ask.ftl`) | EN "Details" here |
| The day's third choice | Other… | Другое… | `today-other`, `remind-other` only | as any other label: **`preset-other` "🎯 Choose…" / «🎯 Выбрать…»; `day-off-ask-other` "Pick days…" / «Выбрать дни…» (the picker it opens takes one or two days: `day-off-pick`, `day_off.py`); bot `pause-other` = the app's; `class-form-length-other` "Enter minutes" / «Ввести минуты»** |
| One session at a shala | class | занятие | everywhere | RU «урок», «класс» alone (never after a hyphen: «Лед-класс», «майсор-класс» stay) |
| Class kinds *(for ashtanga-expert)* | Mysore · Led · 1:1 · Self-practice | Майсор · Лед-класс · Индивидуально · Самостоятельно | details, class form | – (**fix the comment example in `miniapp/src/locales/ru/shala.ftl` ~l. 95: «Лед-класс Полная первая» → «Лед-класс Первая серия целиком»**, decision 2026-10-19) |
| My week of classes (QB) | 🗓 My schedule | 🗓 Моё расписание | **`menu-classes`, `command-schedule`, `welcome-shala-student`**, `my-schedule-*` | "Classes" / «Занятия» as a place |
| A shala's timetable | 🗓 Schedule | 🗓 Расписание | shala card | – |
| Passing a link on | **✉️ Send the link** | **✉️ Отправить ссылку** | both invites, both products; the hints `shala-join-hint` / `invite-hint` **"Send this link or show the QR code." / «Отправь ссылку или покажи QR-код.»** | "Share" / «Поделиться» for links |
| Share a picture | Share | Поделиться | share cards only | – |
| Joining a shala | join | присоединиться (in sentences; never on a button: too long) | hints, consents, `feed-moon-only` | **RU «вступить»** |
| People with a role in a shala | staff | команда шалы | card, setup, consents | **EN `setup-staff` "Invite teachers" → "Invite teachers and staff"** (as the card's "Teachers and staff"; RU «Пригласить в команду» stays) |
| Teacher | teacher | учитель (on my list) · преподаватель (a role in a shala) | – | – (ID-07 rule, kept) |
| Moon day *(for ashtanga-expert)* | 🌙 Moon day · Full moon / New moon | 🌙 Лунный день · Полнолуние / Новолуние | – | – |
| Rest · day off · 🌸 · no practice | Rest day · Day off · Ladies' holiday · No practice | День отдыха · Выходной · Женские дни · Без практики | – | banned always: streak, missed, skipped, broken / «полоса», «пропуск», and only the run phrases «серия дней», «серия практик», «прервать / сохранить серию», «дней подряд» (the series stays «серия»; «практик подряд» stays) |
| Where times are told | My city · 🕐 Times: Almaty | Мой город · 🕐 Время: Алматы | settings, reminders, moon, schedule | **"time zone" / «часовой пояс»** (except the UTC option and the location-privacy line); e.g. **`log-date-future` "In your city this day hasn't come yet." / «В твоём городе этот день ещё не наступил.»** |
| Product name (QF) | Tristhana | **Tristhana**, never declined: where a case is needed, "the app" | greeting, profile texts, app errors (**`startup-failed` «Открой приложение заново», `not-in-telegram` «Открой приложение в Telegram: @tristhana_bot»**, `session-expired` likewise) | **RU «Тристхана»** |
| Getting somewhere in the bot (QC) | ☰ Menu → 🌙 Moon days | ☰ Меню → 🌙 Лунные дни | running text | **/moon, /remind, /settings, /teachers, /start** in text |
| Extra fields of a form | More options | **Дополнительно** | `class-form-more` | RU «Ещё настройки» here |
| Removing my own entry · deleting for everyone | Remove · Delete | Убрать · Удалить | – | **RU `diary-clear` «Удалить заметку» → «Убрать заметку»** |
| The class form's rhythm | **Regularly** · One date (the chips answer "When"); How often: every week / every 2 weeks | **Регулярно** · Одна дата; «Повторяется по дням» stays the next field | `class-form-weekly` | the "Every week" chip |

The ux-writer settles the final text of every bold cell; the ashtanga-expert signs off the marked rows.

## 4. Changes per surface
1. **Bot (`bot.ftl`, en + ru, same keys):** the bold rows above; the 19 command mentions (QC) become button paths or go; `start-greeting`, `bot-description` RU (QF); consents per QE; `remind-days-follow`, `moon-teacher-shared`, `moon-same-as-city` say the app's words where it is the same screen.
2. **Bot, presentation:** the pause question (`days.py`, `pause-ask` screen) gains `screens.menu_row` (Q330); the shala card shows `shala-place` alone when the shala's zone is the viewer's own, and `shala-time` (now with the offset, ADR-0044) only otherwise (`shalas.py`). No callback changes.
3. **Mini App (`app.ftl`, `details.ftl`, `shala.ftl`, `settings.ftl`, `practice.ftl`, `trends.ftl`, `ask.ftl`, `requests.ftl`):** the same rows; `ask.ftl` follows the bot byte for byte (ADR-0049 test); the tab label stays as it is (QA); the RU comment example in `shala.ftl` is corrected (§3, class kinds).
4. **RU month title (Q352a):** one helper `monthTitle(year, month, locale)` in `miniapp/src/i18n/dates.ts`: «Ноябрь 2026» (capital, nominative, no «г.»); used by the month card, the year layer, Trends and `listing.ts::checkedMonth` (which strips «г.» by hand today).
5. **Mini App, presentation:** the shala card's place line as in 2; the run-together labels in My asanas and Settings (Q341) get the `ui/` field layout, as PR #115 did for forms. Initial JS (144.0 / 150 KB) and CSS must not rise.
6. **One key rename (meaning):** the app's `students-day-blank` → `students-day-blank-spoken`, and its `students-day-blank-mark` → `students-day-blank` (the bot's text). `check:guide` confirms no page quotes them.
7. **Q360b:** the Starlight "i18n collection is empty" warning comes from Starlight looking for its optional UI-translation collection; harmless. Confirm on a `main` build; if present, define that collection with Starlight's own loader and schema in `content.config.ts` (no page changes); if that does not silence it, close Q360b as harmless.

## 5. Enforcement (ADR-0050)
- **`docs/glossary.yaml`:** the table above as data (`en`, `ru`, `where`, `retired` per language, `except` with reasons, `expert`), plus `banned` and `same-key-different-text`.
- **`site/src/lib/words.test.mjs`** (site suite; `site.yml` also watches `docs/glossary.yaml`): (a) no retired or banned word in any message text of `bot.ftl`, `card.ftl` and the app's `.ftl`, en and ru (values and attributes only; never ids, comments, variant keys or variables). RU «серия» is matched only in run phrases (§3), and «класс» only as a word of its own, never after a hyphen («Лед-класс», «майсор-класс»); (b) the same in guide pages' prose, titles and descriptions (not `:ftl`, `:cmd`, code, links); (c) **every key both products define renders the same**, for samples of each variable, unless listed in `same-key-different-text` with a reason. The two existing words-in-step tests stay.
- **Order:** slice 1 lands the tests with today's offenders in a `pending:` list (green); slices 2–4 empty it; slice 4 adds "`pending` is empty".

## 6. Guides, What's new, screenshots
- **Pages:** text quoted by key changes by itself. Prose to rewrite (EN + RU twins, per the retired-word test): `students/check-in-and-diary` (title too), `students/your-data`, `students/settings`, `students/my-practice`, `students/my-shala`, `students/reminders`, `students/log-practice`, `students/my-teacher`, `teachers/what-you-see`, `staff/classes`, `staff/create-shala`, `start/bot-and-app`, `start/first-steps`, `reference/privacy`, `reference/faq`, `index`. `reference/commands` keeps its `:cmd` list. `features:` unchanged.
- **What's new** (EN + RU): one entry "Clearer words" naming the visible renames (My schedule, Send the link, How far / How long, Note, How you've felt).
- **Screenshots:** a **full re-run** (`npm run shots`, en + ru): renamed labels sit on most bot shots and many app screens (details, class form, shala card, Settings → More, trends), and RU loses «Тристхана»; click paths are keys, so none changes. Check by eye at 320 px in Russian.

## 7. Cross-cutting checks
- **Time zones ✔.** No data change. Words only: "time zone" leaves the UI for "city" and "time"; the shala card follows ADR-0044 (offset only outside the viewer's zone); the RU month title is formatted in UTC as today.
- **Privacy ✔.** 🌸 wording untouched; the consent promises do not change (QE); share cards keep saying nothing personal.
- **i18n ✔.** Every change in `.ftl`, en + ru, key and variable parity; Russian plurals untouched; RU «ты», no gendered past tense; names never follow a word that needs a case (the colon form); labels wrap at 320 px.
- **Responsiveness ✔.** No new read, import or chunk; `check:bundle` before and after slice 3.
- **Layering ✔.** No domain, application or API change; the two bot fixes stay in `bots/telegram/`; import-linter unchanged.

## 8. Tests
- **New:** `words.test.mjs` (§5); vitest for `monthTitle` (en, ru, also `TZ=UTC`); bot: the pause question ends with the Menu row; the shala card without "shala time" in the viewer's own zone and with the offset outside it (bot and `ShalaScreen.test.tsx`).
- **Pinned and to update (text only):** `tests/infrastructure/test_i18n*.py` (consent byte tests and item tables for QE; `/moon` and `/teachers` assertions), `test_settings_bot.py`, `test_shalas_bot.py`, `test_my_schedule_bot.py`, `test_days_bot.py`, `test_diary_bot.py`, `tests/tools/test_set_webhook.py` (`command-schedule`); Mini App tests that find labels by text (`Stats`, `DayEditor`, `Settings`, `ShalaTab`, `ClassForm`, `Trends`). **Untouched:** `test_stale_buttons_bot.py`, every callback test, the ADR-0049 words-in-step test (both sides change together).
- **By hand:** 320 px, Russian, dark theme: tab bar, day card details, class form, shala card.

## 9. Slices (each green: pytest, ruff `--no-cache`, pyright, lint-imports, vitest also `TZ=UTC`, lint, typecheck, `check:bundle`, site tests and build)
1. **Glossary and tests:** `docs/glossary.yaml`, `words.test.mjs` with `pending`, the `site.yml` path filter.
2. **Bot:** `bot.ftl` en + ru, the pause Menu row, the shala place line, consents (QE), backend test updates.
3. **Mini App:** the app's `.ftl` files, `monthTitle`, the shala place line, Q341 labels, the one key rename.
4. **Guides, screenshots, notes:** pages and What's new (`/guide-update UI-06`), full re-shoot, Q360b, `pending` empty. ux-writer and ashtanga-expert review the copy before the final suite.
- **Ops ☁️ (ask the owner):** after the deploy, `python3 tools/telegram/set_webhook.py` (command menu: "My schedule") and `--texts` (RU profile, QF).
- **Notes on acceptance (not done by this spec):** QA–QF numbered (next free: Q361–Q366) and Q330, Q341, Q342, Q352a, Q360b closed in `03 Open Questions & Decisions.md`; a "Words" pointer to `docs/glossary.yaml` in `01 Domain Context.md`; ADR-0050 in `04 Architecture.md`; UI-06 ✅ in `02 Requirements.md` and `09 Roadmap.md`; CLAUDE.md's i18n rule names the glossary.

## 10. Risks
- **Stale buttons:** labels change, callback data does not; old messages keep old labels and land on living screens.
- **Guide quotes:** only §4.6 renames a key; `check:guide` fails the build if a page quotes it.
- **Consent records (QE):** changing words in a confirmed text; mitigated by ADR-0045's rule and the owner reading each changed sentence.
- **Muscle memory:** "Classes" becomes "My schedule"; What's new says so, and the emoji stay.
- **RU width:** longer labels at 320 px (e.g. «Выбрать дни…», «Пригласить в команду»); the tab bar is untouched (QA), and «присоединиться» stays off buttons.
- **False positives** in RU regexes (inflections, «серия» the series): `except` with a reason.

## 11. Questions for the owner (placeholders; the bold recommendation is what this spec builds)
- **QA. The calendar place and «Практика» (Q342).** **Recommended: keep it as it is. The tab keeps the short form "📊 Practice" / «📊 Практика» (a tab is about 102 px at 320 px and «📊 Моя практика» would be cut); the heading and the bot's Menu row say "My practice" / «Моя практика»; the logged status stays "🧘 Practiced" / «🧘 Практика»: 📊 and 🧘 tell the place from the status.** The tab is the glossary's one listed exception. "My practice: …" in the length choices and "Your practice: …" in My asanas keep their Ashtanga sense (ashtanga-expert); My asanas is one tap from the Practice tab (its first row under the month). Alternative: keep the tab, and change the RU status to «🧘 Была практика».
- **QB. "Classes" or "My schedule" for the week of classes.** **Recommended: "🗓 My schedule" / «🗓 Моё расписание» everywhere** (the screen and the app already say it; "class" stays the word for one class, "Schedule" for a shala's). Alternative: "🗓 Classes" / «🗓 Занятия» everywhere, so the app row and the screen title change instead.
- **QC. Commands in the bot's text.** **Recommended: no message names a command; say the button path ("☰ Menu → 🌙 Moon days") or nothing.** Commands stay in Telegram's command menu and on the guides' Commands page. Alternative: keep them in bot messages as a shortcut for people who type, remove them only where the app shows the text.
- **QD. "Length" and "Duration" in English.** **Recommended: "📏 How far" (how far in the series) and "⏱ How long" (minutes, also on the class form); Russian keeps «Объём практики» and uses «Длительность» for minutes in both places.** Alternative: keep "Length" / "Duration" as they are (the class form already avoids "Length").
- **QE. The consent texts.** They name `/teachers`, "check-ins" and "diary notes". **Recommended: change those words with the sweep, as presentation only (same promises, same buttons, tests updated, every changed sentence shown to you in the pull request).** Alternative: freeze the consent texts and list them as exceptions; they keep "/teachers" while the bot no longer lists that command.
- **QF. The product's name in Russian.** **Recommended: "Tristhana" in Latin in every Russian text, as the guides, share texts, links and the bot's name already are, and never declined: where Russian needs a case, the text says «приложение»** («Я — Tristhana, твой спутник…»; «Открой приложение заново»; «Открой приложение в Telegram: @tristhana_bot»); voice-overs keep their own spelling. Alternative: «Тристхана» in Russian running text, Latin only in names and links (then the guides and share texts change instead).
