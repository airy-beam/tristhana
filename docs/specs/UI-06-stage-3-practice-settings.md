# UI-06 stage 3: the Practice tab (month first, four legend items) and Settings (five rows, five short pages)

- Status: **accepted** (owner, 2026-11-17: QA–QF in §13 all as recommended, "All yes"; in the notes they are QA = Q346, QB = Q347, QC = Q348, QD = Q349, QE = Q350, QF = Q351) · Size **L**, one pull request, branch `ui-06/stage-3-practice-settings` from `main` at `e1c761d`
- Parent: `docs/specs/UI-06-simple-journey.md` (§1, §10). Sits in the shell of `UI-06-stage-2-app-shell.md` (ADR-0047). Requirements: **UI-06**; changes ST-01/02/03 (layout, legend), ID-06 (Settings); touches WH-01/02 (how 🌸 shows to its owner), PR-06, PR-09, NT-01/02, SC-06, ST-09, UI-05.
- Related: ADR-0020, 0021, 0029, 0044, 0047. **No new ADR:** the pages are inner layers of the Settings screen (ADR-0047 already allows them), the legend is presentation over an unchanged API (ADR-0020 gets an "amended by" line), nothing is stored or migrated.

## 1. Scope
**In:** the Practice root rebuilt around one month; the legend from eight items to four; the year behind one row; the numbers in one line and one fold; Settings as five rows that carry their values (the bot's five, the bot's words) and five lazy pages; one new launch value `?open=settings`; stats CSS out of the initial stylesheet; ADR-0044 labels on these screens.
**Out:** any change to `GET /me/stats`, to what a teacher or a shala sees, to share cards, Badges, Check-ins over time, My asanas, the Today tab, the day card's choices (stage 2); the wording sweep (stage 5). No domain change, no use case, no port, no migration.

## 2. Inventory (read 2026-11-17)
**Practice tab today** (`screens/stats/Stats.tsx`), top to bottom: heading and gear · My asanas row · consistency card (this month "X of Y" or a count, in a row, most in a row, a hint, the day-off question or link) · year card (year pager, year total + Share, twelve mini-months, legend, the 🌸 device switch) · month card (title + Share, the grid, the day card on a tap, the month summary: practices, rest by kind, where, online, by series, time, "N days not logged") · Badges row · Check-ins row. The month is the fifth thing on the screen.

| # | Legend item today | Drawn as | After (§3) |
|---|---|---|---|
| 1 | Practice | accent fill | **stays (1)** |
| 2 | Rest | green | **stays (2)**, and absorbs 3, 4, 5 and 🌸 |
| 3 | 🌙 Moon day (rest) | darker green fill | merged into Rest; the moon is the marker, never a fill |
| 4 | Day off or moon day (not logged) | light green, dashed | merged into Rest (it is rest); the screen-reader name still says "not logged" |
| 5 | Sick or traveling | grey | merged into Rest; the reason is one tap away, on the day |
| 6 | No practice | sand | **stays (4)**, with its 🌱 |
| 7 | Not logged | outlined empty cell | dropped: an empty day is a plain number and needs no entry |
| 8 | Full or new moon · 📍 city | ring | **stays (3)** as "🌙 Moon day"; the city moves to the day |
| (9) | 🌸 Ladies' holiday, only with the device switch on | pink | dropped: no pink fill, no fifth item (§3) |

| Setting today | Where | Needed | 
|---|---|---|
| Name | Settings, profile card | once, usually never |
| Language | profile card | once |
| My city (list, "not listed" → phone's time or UTC), city nudge with "Not now", zone hint | city card | once; again after a move |
| Day off (seven days, "No fixed day off") | day-off card | once |
| Moon calendar city (follow teacher / shala / my city / list), source line, calculation note | moon card | once, mostly never (inherited) |
| Moon reminders: days before (7 · 3 · 1), send at | moon card | rarely |
| Practice reminder: on / off, time, paused line + resume, days line | reminder card | once, then rarely |
| Quiet hours, "No quiet hours", at most N a day | quiet card | almost never |
| Announcements switch (only with a teacher or a shala) | own card | rarely |
| Calendar subscription | card (also on My schedule) | once |
| Guide | row | when lost |
| Three privacy texts (🌸 encrypted · what a teacher sees · location and map credit) | privacy card | read once, if ever |
| Show 🌸 days on this device (`localStorage` `stats.showLadies`) | privacy card **and** under the Practice legend | once |
| Show the 🌸 button (`hide_ladies`) · Show "How do you feel?" (`offer_check_in`) | privacy card | once |
| My data: download, delete | last card | almost never |

Ten cards and a row on one scroll. Opening it needs up to five reads besides `me` (`notification-settings`, `moon-days`, `moon/cities`, `links`, `shalas`; some are already cached from Today) and the modules of the moon screen and the calendar card, which `Settings.tsx` imports statically. The bot's `/settings` is five rows and no read.

## 3. Practice tab
**First screen, in order:** heading and gear · **the month card** · rows: `progression-open` · `stats-year-open` · `badges-open` · `trends-open`. The rows sit outside the loaded part, so they show while stats load and when they fail (the year row needs stats and waits).

**The month card:** `‹ November 2026 ›` and Share (as today, only with a practice) · the grid · the day card when a day is open · the legend, one line · **one number**: `stats-month-practices` ("12 practices"), else `stats-month-empty` · on the current month only: `stats-run-current` from 2, `stats-unlogged`, and the day-off question or link while no day off is chosen (unchanged components) · the fold `stats-more`.
- **Pager** moves by month and crosses years (`{year, month}` lifts from `Loaded` into `Stats`; the previous year's data stays on screen while the next loads). Lower bound: January of `first_year`; upper bound: the current month. "Today" and the current month come from `stats.today`, never the device.
- **Legend, four items in this order** (QA; from the Ashtanga-domain review): **Practice** (accent fill, one colour: led, Mysore, home and short all look alike) · **Rest** (one green: logged rest, weekly day off, auto-rest, a logged moon day, sick, travel, 🌸) · **🌙 Moon day** (the ring on the date; a marker, never a fill or a status; also on the coming days of this month) · **🌱 No practice** (quiet sand; the chosen status behind "X of Y").
- **Not in the legend:** today (keeps its outline) · an empty past day (a plain number: no outline, no colour) · future days (hint colour, not tappable, as today).
- **Moon days.** A practice on a moon day is the practice fill with the ring and no remark. A day logged "Moon day" on a date the followed city does not mark is rest without a ring. The city is on the day card (`stats-day-moon`: phase and 📍 city, from `stats.moon`).
- **🌸 (QB).** Device switch off (the default): rest tone, legend "Rest", accessible name "Rest day", counted with rest in the fold. On: rest tone plus a small 🌸 in the day's corner (`aria-hidden`; the name is `status-ladies`), its own line in the fold; still four legend items, no pink. The year view never marks it. The switch leaves this tab and lives in Settings → More only.
- **One tap on a day** (up to today) opens the day card for that date under the grid: the same `DayLog` as Today's, with the moon line when the date is one. The card scrolls into view and its heading takes the focus; Done or Back closes it; the tab bar hides meanwhile (ADR-0047). **The day card always tells its owner the truth** (QB): 🌸 is offered under "Other…" by `hide_ladies` alone and shows as 🌸 with `today-private-note`, as on Today and in the bot. Today the editor follows the device switch, so with the default a past 🌸 day cannot be logged in the app at all.
- **The fold `stats-more`** ("The month in numbers", closed, `aria-expanded`; absent for an empty month) holds today's month summary whole (rest by kind, where, online, by series, time), then `stats-consistency` ("Practice on 9 of 10 days", only when a "No practice" day exists), `stats-run-longest` (current year) and `stats-consistency-hint`.
- **The year** (QD): the row `stats-year-open` carries the year and its total ("📅 2026 · 143 practices") and opens a layer over the tab (lazy `stats/Year.tsx`, as Badges does): year pager, `stats-year-total` + Share, the twelve mini-months in the same three fills and ring, the legend. A tap on a mini-month closes the layer on that month. Back returns to the month that was shown.
- **Tone.** No "missed", no red, no cross, no greyed past day, no intensity by length or series, nothing that singles out a moon-day practice. The only count that can read as a shortfall, "of Y", sits in the fold and exists only once the person chose "No practice" themselves.

## 4. Settings
**First screen (`Settings.tsx`, rendered from the cached `me`, no request):** heading · five rows, each label carrying its value, with the bot's keys and text · a quiet last row `guide-open` (QE). Nothing else.

| Row (key = the bot's) | Value from `me` | Page | On the page |
|---|---|---|---|
| `settings-language-line` | `language-auto` / `-en` / `-ru` | **Language** | three choices, one per row; a tap saves |
| `settings-city-line` · `-unset-line` · `-unlisted-line` · `-no-zone-line` | `home_city`, `timezone` (ADR-0044: own city without offset; no city: the offset is the information) | **My city** | the time now · the city list · "not listed" → phone's time or UTC · `settings-zone-hint` · `settings-privacy-location` (small) |
| `settings-day-off-line` · `settings-days-off-line` · `-none-line` · `-unset-line` | `day_off` | **Day off** | seven days and "No fixed day off" · a two-sentence hint |
| `settings-reminders-button` | – | **Reminders** | `settings-times-place` (the place, once, for every time below) · practice reminder (switch, time, pause line) · moon reminders (days before, send at) · fold `settings-quiet` with the bot's summary line (`settings-quiet-line`): hours, "No quiet hours", daily limit · announcements switch (same rule as today) |
| `settings-more-button` | – | **More** | Name · group `settings-log-title`: moon calendar city with its source line, `settings-ladies-button`, `stats-show-ladies`, `settings-checkin` (QC) · group `settings-privacy`: fold `feed-open` (the calendar card), fold `settings-privacy-open` (the two privacy texts), My data (download, delete) |

- **Pages are inner layers of Settings**, each its own lazy chunk through `lazyRetry`, prefetched when the five rows mount; each registers Back (→ the five rows) and takes the heading focus. Saving is as today: a tap saves, optimistic, `settings-save-failed`; the name saves on blur. The rows re-read `me`, so a value changes as soon as it is saved.
- **Gear and Telegram's ⋯ "Settings": one route, unchanged** (`openSettings`); both land on the five rows. `SettingsFocus` keeps its two values and now names a page: `day-off` → Day off, `remind` → Reminders. A page opened by a focus closes Settings on Back (the person returns to where they were, as today).
- **Where everything lands (nothing is lost):**

| Thing | Today | After |
|---|---|---|
| Name | profile card | More, first field |
| Language · My city · Day off | three cards | rows 1–3 and their pages |
| City nudge + "Not now" | city card | **removed**: the row asks ("My city? 🕐 …"), as the bot since stage 1; `home_city_chosen` is still set by a choice |
| Zone hint · location and map credit (ODbL, ADR-0029) | city card · privacy card | My city page |
| Practice reminder | card `#remind` | Reminders, first |
| Moon reminders (days before, send at) | moon card | Reminders |
| Quiet hours, daily limit | card | Reminders, fold |
| Announcements switch | card | Reminders, last |
| Moon calendar city + source line | moon card | More |
| Moon calculation note | moon card | **removed here**; it stays on the Moon screen (Today → moon row) |
| Calendar subscription | card | More, fold; My schedule keeps its card |
| 🌸 encrypted · what a teacher sees | privacy card | More, fold `settings-privacy-open` |
| Show 🌸 days on this device | privacy card and Practice legend | More only (QB) |
| 🌸 button · "How do you feel?" | privacy card | More |
| My data | card | More, last |
| Guide | row | first screen, last row |

## 5. Routes, chunks, budgets
- **Chunks.** Unchanged: `Stats` (Practice root), `Badges`, `Trends`, `DayEditor`, `dayExtras`. New: `stats/Year` (the heatmap leaves `Stats`); `settings/pages/{Language,City,DayOff,Reminders,More}`. `Settings` shrinks to the rows and no longer imports `MoonScreen`, `CalendarFeedCard`, `PracticeReminderCard`, `MyData` or `stats/cells` (they go with their pages).
- **Initial JS (144.9 of 150 KB): must not rise.** What touches the first chunk: one case in `launchNav` (+), `DayLog` loses `showLadies` (−), five legend keys and two nudge keys leave `app.ftl` (−). **Every new message goes to a lazy file** added with `addMessages`: `locales/{en,ru}/practice.ftl` (with `Stats`) and `settings.ftl` (with `Settings`). Headroom if the check moves up: `stats-*` and `settings-*` messages that no first-chunk module uses may move to those files (verified by grep; `stats-back`, `stats-editor-done`, `settings-open`, `settings-save-failed`, `settings-zone-*` stay). The site reads every `.ftl`, so a moved key costs the guides nothing.
- **Initial CSS (budget 10 KB): expected to fall.** The rules used only under `screens/stats/` (pager, heatmap, cells, swatches, legend, month grid, day, counts; about 200 lines of `theme/tokens.css`) move to `screens/stats/stats.css`, imported by `Stats` and `Year`; the moon, 🌸, away and dashed-auto colours are deleted. New `screens/settings/settings.css` (the row with its value) ≤ 0.5 KB gzip, with the `Settings` chunk. Pages use the existing card, chip and toggle classes and `ui/` (its `form.css` already rides with lazy chunks).
- Sizes above are not measured. The PR records `npm run check:bundle` before and after each slice.

## 6. API, backend, domain
- **API: none.** `Me` already carries every row's value; `Stats` already carries the moon phases. No OpenAPI change, no `gen:api`, no policy, no migration, no domain or use-case change.
- **One bot line (QF):** `bots/telegram/settings.py::more` builds "⚙️ More in the app" with `app_url(self._app, "settings")` in place of the bare address, which opens Today. `launchNav`: `settings` → Today root with Settings pushed; Back → Today. An app bundle older than the bot opens Today (unknown value), as now.

## 7. Copy (the ux-writer settles the text; RU «ты», no gendered past tense)
**New, `practice.ftl`:**

| Key | en | ru |
|---|---|---|
| `stats-month-prev` / `-next` (`.aria-label`) | Previous month / Next month | Предыдущий месяц / Следующий месяц |
| `stats-more` | The month in numbers | Месяц в цифрах |
| `stats-year-open` (`$year`, `$n`) | 📅 { $year } · { $n } practice(s); `[0]` the whole year | 📅 { $year } · { $n } практика / практики / практик; `[0]` весь год |
| `stats-day-moon` (`$phase`, `$city`) | 🌕 Full moon · 📍 { $city } / 🌑 New moon · 📍 { $city } | 🌕 Полнолуние · 📍 { $city } / 🌑 Новолуние · 📍 { $city } |
| `stats-legend-label` (the list's accessible name) | What the marks mean | Что означают отметки |
| `stats-show-ladies-hint` | On this phone only. While it's off, these days look like rest. | Только на этом телефоне. Пока выключено, эти дни выглядят как отдых. |

**New, `settings.ftl`, text copied from `bot.ftl` under the same key** (a test keeps them equal, §10): `settings-language-line`, `settings-city-line`, `settings-city-unset-line`, `settings-city-unlisted-line`, `settings-city-no-zone-line`, `settings-day-off-line`, `settings-days-off-line`, `settings-day-off-none-line`, `settings-day-off-unset-line`, `settings-reminders-button`, `settings-more-button`, `settings-reminders-title`, `settings-more-title`, `settings-quiet-line`, `settings-quiet-off-line`.
**New, `settings.ftl`, the app's own:** `settings-times-place` (`$zone`: "🕐 Times: { $zone }" / «🕐 Время: { $zone }») · `settings-log-title` ("Your log" / «Твой журнал») · `settings-privacy-open` ("🔒 What others see" / «🔒 Что видят другие»).

**Changed text, same key:** `stats-show-ladies` ("Show 🌸 on my calendar" / «Показывать 🌸 в календаре») · `stats-consistency` ("Practice on { $x } of { $y } days" / «Практика в { $x } из { $y } дней», plural kept: any month, not only this one) · `settings-day-off-hint` ("Pick one or two. They show as rest, and practice reminders skip them." + the existing `$first` sentence, shortened to "A change applies from today." / «Отметь один или два. Они отмечаются как отдых, и напоминания о практике в эти дни не приходят.» + «Изменение действует с сегодняшнего дня.»).
**Reused, no new key:** the legend's third and fourth items are `status-moon` and `status-skipped` (one word per thing); `stats-legend-practiced`, `stats-legend-rest` unchanged; `stats-legend-none` stays as the screen-reader name of an empty day.
**Removed:** `stats-legend-moon`, `stats-legend-auto`, `stats-legend-away`, `stats-legend-skipped`, `stats-legend-moon-marker`, `stats-consistency-count`, `settings-city-nudge`, `settings-city-not-now`. No guide quotes them.
**Must survive** (guides quote them): `stats-show-ladies`, `settings-open`, `settings-quiet`, `guide-open`, `badges-open`, `trends-open`, `tab-practice`, `feed-open`, `export-button`, `delete-button`, `status-*`.

## 8. Old links and stored state
| Existing | After |
|---|---|
| `?open=practice` (the bot's Menu "My practice", old messages) | Practice root: the current month |
| `?open=new-shala`, `announce`, `listing`; none or unknown | unchanged (Shala tab; Today) |
| Old "⚙️ More in the app" (bare address in a sent message) | Today, as now; new messages carry `?open=settings` |
| Telegram ⋯ "Settings", the gear | the five rows |
| `settings{focus: "day-off"}`: the stats day-off question's "Other…", `stats-day-off-link` | Day off page over Practice; Back → Practice |
| `settings{focus: "remind"}`: Today's reminder step without a zone, `remind-change-time` | Reminders page; Back → Today |
| Section ids `#day-off`, `#remind` (scroll targets) | gone with the scroll; nothing outside `Settings` uses them |
| `localStorage` `stats.showLadies` | same key and values; now read by the month grid, the fold and More (no longer by the day card or `MySchedule`) |
| `localStorage` `tz.keep`, next-step "Not now", setup "I teach alone", schedule filter, badges seen | untouched |
| Every bot callback | untouched (`test_stale_buttons_bot.py` stays green as it is) |

## 9. Cross-cutting checks
- **Time zones ✔.** Days are dates in the account's zone: the grid, "today" and the pager's bounds come from `stats.today`; date-only values are formatted in UTC as today (also under `TZ=UTC`). Reminders names the place once for every time on the page (own zone: no offset; no zone: `moon-zone-needed-app`, as today). The city row follows ADR-0044's two cases. Nothing stores an offset.
- **Privacy ✔.** 🌸 is rest on the month, the year, the legend and the fold unless the device switch is on; the switch never leaves the phone; the year view and share cards never mark it; accessible names follow the switch. The day card shows 🌸 only to its owner, after a tap, with `today-private-note` (QB). `hide_ladies`, the sealed status and every teacher projection are untouched. The two privacy texts and the map credit keep their wording.
- **i18n ✔.** Every string in `.ftl`, en + ru, key and variable parity (the two new files join `bundles.test.ts`); Russian plurals in `stats-year-open`; row labels wrap at 320 px, never truncate.
- **Responsiveness ✔.** Practice: one read (`stats`), as today; a month step inside a year makes none. Settings' first screen: none (up to five today); each page reads what it shows. Saves stay optimistic; a row or page tap answers with a haptic first.
- **Accessibility, touch, theme ✔.** Rows and choices ≥ 44 px; day cells ≥ 36 px at 320 px with the ring and the 🌸 mark clear of the number; the legend is a list with a name; the fold and the page folds use `ui/More` (`aria-expanded`). Dark theme: rest and sand keep dark numbers, the ring and today's outline use the text colour, an empty past day is the text colour, a future day the hint colour.
- **Layering ✔.** Mini App presentation only; the single backend line is in `bots/telegram/`.

## 10. Tests
- **`stats/Stats.test.tsx` (most cases change).** New: the month heading comes before any year; the pager crosses a year, stops at the current month and at `first_year`'s January; exactly four legend items in order, en and ru, no "Not logged"; sick, travel, a logged moon day, 🌸 and auto-rest all get the `rest` class, an empty past day gets none; the ring on a coming day of this month and on a practiced moon day; 🌸 off → rest and "Rest day", on → rest + mark + `status-ladies`, legend still four; no switch on the tab; one number, the fold closed, then the old summary inside it; the run line only on the current month; the year row's label and the lazy layer; a mini-month tap lands on that month; the day card shows the moon line; My asanas after the month and still there when stats fail. Pinned today by: "draws a ladies' holiday as rest until shown on this device", "marks moon days with a ring, also later this month", "summarises the month and counts unmarked days only for this month", "bounds the year arrows by the first year with data", "the editor keeps a ladies' holiday as rest while the switch is off", "has My asanas as its first row, under the heading", "draws an unlogged day off lighter…", "asks once on the stats card…", both Share cases, "comes back to the same month…" (Badges, Check-ins).
- **Day card (QB):** `stats/DayEditor.test.tsx` "has no 🌸 among the reasons while 🌸 days are hidden on this device" and `RestPeriods.test.tsx` "names a cut 🌸 pause as rest while 🌸 days are hidden on this device" turn round; "leaves 🌸 out of the day editor too" (`hide_ladies`) stays.
- **`settings/Settings.test.tsx` (regrouped by page).** New: five rows and Guide, each value for each state of `me` (language chosen or not; city, no city, unlisted, no zone; one, two, no, unset day off); no request but `me` until a page opens; each page's controls and saves; `focus` opens its page and Back closes Settings; the 🌸 switch is in More and the Practice tab reads it. Pinned today by: "opens scrolled to the practice reminder when asked", "nudges once: Not now answers it…", "has no nudge once answered", "explains privacy and shares the 🌸 switch with Stats", "is separate from the device-only 🌸 days switch", and every case that finds a control on the one long screen.
- **Shell:** `nav.test.ts` (`?open=settings`); `App.test.tsx` (gear and ⋯ show the five rows; `?open=settings` then Back is Today; the day-off link from Practice opens the Day off page). The test that forbids plain `React.lazy` covers the six new chunks.
- **Words in step:** `site/src/lib/guide.test.mjs`: the fifteen shared keys read the same in app and bot, en and ru (the site workflow runs when either side's locales change).
- **Bot:** `tests/bots/test_settings_bot.py`: More's app button ends in `?open=settings`.
- **By hand:** 320 px wide in Russian and the dark theme, for the month card, an open day, the fold, the year layer, the five rows and each page; one iPhone and one Android.

## 11. Guides and screenshots (`/guide-update UI-06`, each page with its `ru/` twin)
- **Pages:** `students/my-practice` ("What you see": the month, four marks, the fold, the year behind its row; the 🌸 line), `students/settings` (the app has the same five rows; where the name, quiet hours and the daily limit are), `students/rest-and-moon-days` (the 🌸 switch is under Settings → More; a 🌸 day reads as rest on the calendar), `students/reminders` (the gear → Reminders → quiet hours), `students/check-in-and-diary` and `students/your-data` (the app's path through More), `start/bot-and-app`, `start/first-steps`, `reference/faq`, `reference/whats-new`.
- **Screenshots (`site/shots/manifest.yaml`, en + ru):** `app-my-practice` and `app-settings` change whole. New: `app-practice-day` (a day open), `app-practice-year`, `app-settings-reminders`, `app-settings-more`. `stats-year-open` carries a count, so its step names it by place, as the waiting row's does. The demo student's browser has the 🌸 switch off.
- **Notes on acceptance (not done by this spec):** ST-01/02/03, ID-06 and UI-06 rows in `02 Requirements.md`; QA–QF numbered and recorded in `03 Open Questions & Decisions.md`; an "amended by" line in ADR-0020 (three fills and a marker); the Stats and Settings paragraphs of `04 Architecture.md`; `09 Roadmap.md`.

## 12. Build slices (each ends green: tests, lint, typecheck, `check:bundle`)
1. **Practice tab.** `stats.css` out of `tokens.css`; `practice.ftl`; `{year, month}` in `Stats`, the month card, four fills and the ring (`cells.ts::kindOf`), the legend, the fold, `stats/Year`; the day card stops following the device switch (`DayLog`, `DayEditor`, `MySchedule`); the switch leaves the tab (Settings still has it).
2. **Settings.** `settings.ftl`, `settings.css`; the five rows; the five page chunks cut out of today's `Settings.tsx`; `focus` → page; `?open=settings` in `launchNav`; the nudge removed; the words-in-step test.
3. **Bot line, guides, screenshots.** `app_url(…, "settings")` and its test; `/guide-update UI-06`; the notes.

## 13. Questions for the owner (the bold recommendations are what this spec builds)
- **QA. The four legend items.** **Recommended (from the Ashtanga-domain review, which ran in parallel; it may still adjust the wording): Practice · Rest · 🌙 Moon day (a ring on the date) · 🌱 No practice. Rest takes in the day off, auto-rest, a logged moon day, sick, travel and 🌸; an empty day is a plain number with no entry.** Option within it: keep "No practice" as the fourth item (recommended: it is the person's own choice and explains "X of Y"), or draw it like an empty day and drop the "of Y" count, which leaves three items.
- **QB. The device-only 🌸 switch.** **Recommended: keep it, in one place (Settings → More), off by default; it decides only whether the calendar marks 🌸. The day card always shows its owner the real status, as Today and the bot do, so a past 🌸 day can be logged from the month.** Alternatives: keep today's rule (with the switch off the opened day also says "Rest day" and offers no 🌸: discreet against a glance over the shoulder, but a past 🌸 day can then be logged only in the bot); or drop the switch, so the calendar never marks 🌸.
- **QC. "Show 'How do you feel?'" (`offer_check_in`, Q313).** **Recommended: keep it, under More, as in the bot** (already built on both sides, stored values kept). Alternative: retire it and always show the line; one switch fewer, at the cost of a bot change and an unused column.
- **QD. The year.** **Recommended: behind one row that carries the year's total; the first screen is one month.** Alternative: keep the twelve mini-months on the tab, under the month (nothing hidden, a longer screen, the legend twice).
- **QE. Settings' first screen.** **Recommended: exactly the bot's five rows and a quiet "Guide"; the name is the first field under More.** Alternative: "Name" as a sixth row on the first screen (it is what teachers see, but the bot has no such row and most people keep their Telegram name).
- **QF. The bot's "⚙️ More in the app".** It opens Today, where nothing says Settings. **Recommended: it opens the app's Settings (`?open=settings`): one line in the bot and one launch value.** Alternative: leave it; the stage then has no backend change at all.
