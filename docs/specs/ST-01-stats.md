# ST-01 + ST-02 + ST-03: year heatmap, month summary, consistency

- Status: **accepted** (owner: all yes, 2026-10-19, after the ashtanga-expert review) · Date: 2026-10-19 · **§9 overrides §2–§8 where they differ**
- Requirements: **ST-01** (year heatmap with rest/moon/ladies markers), **ST-02** (month summary: practices, rest days, by type, by series), **ST-03** (consistency that respects rest days: "X of Y possible days" + a run that skips rest/moon days); settles **Q18** (run semantics) and **Q19** (pranayama-only day). Also delivers the **Mini App backfill** promised with ST-01 (PR-01 decision). Prepares ST-07 (share cards), GM-01 (milestones), ST-06 (teacher view). Budget: < 300 ms p50 per tap (warm).
- Related: ADR-0005 (time), 0013 (generated client), 0016 (sealed ladies' holiday), 0017 (catalog in memory), 0019 (stored moon calendars). New: **ADR-0020** (stats computed server-side in the domain; heatmap as hand-made SVG, no ECharts; Proposed).

## 1. Scope
**In:** a pure `domain/stats.py`; one use case `GetYearStats`; `GET /api/v1/me/stats?year=`; a lazily loaded Mini App **Stats** screen (consistency card, 12-month heatmap, month calendar + summary); tapping a day in the month calendar opens a **day editor** (status chips + practice details) for backfill.
**Out:** a bot `/stats` (Q8), ST-07 share cards, GM-01 milestones, ST-04/05, ST-06 teacher views, PR-09 auto-fill (moon days are **markers only**, never statuses, Q21), percentages, comparisons with other people (no leaderboards), shading by practice length.
**Cut if time is short:** the day editor (the bot's `/log` covers backfill), the 🌸 toggle (ladies' holiday then always shows as rest on the grid).

## 2. Flows and copy
- **Entry:** Home gets a row button `stats-open` "📊 My practice" under the Today card. It switches an in-app view state (no router) to **Stats**; Telegram's BackButton returns to Home. The Stats chunk is `React.lazy`-loaded, so the initial bundle doesn't grow.
- **Stats screen, top to bottom** (360 px phone, Telegram theme colours):
  1. **Consistency card** (current year only): `stats-consistency` "Practiced on { $x } of { $y } possible days this month" + `stats-run-current` "🌿 { $n } practices in a row" (shown only when n ≥ 2) + `stats-run-longest` "Longest run this year: { $n }" + a one-line `stats-consistency-hint` "Rest, moon, sick and travel days don't count against you: they're part of the practice."
  2. **Year heatmap:** `‹ 2026 ›` (bounded by `first_year` … the current year) and `stats-year-total` "{ $n } practices in { $year }". **12 mini-months in a 3 × 4 grid**, each 7 columns (**Monday first**, both locales) × ≤ 6 rows of ~12 px cells. A true 53 × 7 GitHub strip needs ~740 px (horizontal scroll, unreadable labels); month blocks fit 360 px, read naturally and double as month navigation (tap a block → that month below). Legend underneath.
  3. **Month view:** `‹ October 2026 ›` (month name via `Intl` standalone form), a large 7-column calendar (~44 px cells, so taps are comfortable) with the same colours plus the day number; today outlined. Under it, the **month summary** (rules in §3.1). Tap a past/today cell → the **day editor** sheet (the TodayCard chips + PracticeDetails for that date; 🌸 shown pressed only here). Future cells are inert.
- **Cell encoding (one colour per status family; ADR-0020):** practiced = theme accent · rest / logged moon / ladies' holiday = soft "rest" tone (logged moon a deeper shade of it) · sick + travel = neutral "away" tone · "No practice" = pale sand · not logged = empty with a faint border · future = blank. **Moon day of the followed calendar** = a small ring/dot on any cell, logged or not, never a status. Practising on a moon day shows accent + ring, nothing else. **Ladies' holiday** is drawn as rest by default; a legend switch `stats-show-ladies` "Show 🌸 days (only you see this)" gives them their own tone, kept on the device (`localStorage`), never sent anywhere. Every cell has an `aria-label` `stats-cell-label` "{ $date }: { $status }"; the legend is a real list; colour is never the only signal in the month view (day numbers + status emoji on long-press/tap).
- **Empty / failures:** no data in a month → `stats-month-empty` "Nothing logged this month yet. Each day you log shows up here."; load error → `stats-load-failed`; `invalid_year` can't happen from the UI (bounded arrows).
- **Copy (app.ftl only; RU «ты»; never "missed", "broken", "lost", "only", "streak"; avoid «серия», which means an Ashtanga series; ⚑ ux-writer + ashtanga-expert):**
  - `stats-open` "📊 My practice" / «📊 Моя практика»; `stats-title` "My practice" / «Моя практика»
  - `stats-year-total` "{ $n } practices in { $year }" / «{ $year }: { $n } практика / практики / практик» (Fluent plural on `$n`)
  - `stats-consistency` "Practiced on { $x } of { $y } possible days this month" / «Практика в { $x } из { $y } возможного дня / возможных дней в этом месяце» (plural on `$y`: one → «возможного дня», other → «возможных дней»)
  - `stats-run-current` "🌿 { $n } practices in a row" / «🌿 { $n } практика / практики / практик подряд»; `stats-run-longest` "Longest run this year: { $n }" / «Дольше всего подряд в этом году: { $n }» ⚑ (wording of "run")
  - `stats-consistency-hint` (above) / «Отдых, лунные дни, болезнь и дорога не идут в минус: это тоже часть практики.»
  - Legend: `stats-legend-practiced` "Practice" / «Практика», `-rest` "Rest" / «Отдых», `-moon` "Moon day" / «Лунный день», `-ladies` (reuses `status-ladies`), `-away` "Sick or travelling" / «Болезнь или дорога», `-skipped` "No practice" / «Без практики», `-none` "Not logged" / «Без отметки», `-moon-marker` "Full or new moon · 📍 { $city }" / «Полнолуние или новолуние · 📍 { $city }»
  - Summary: `stats-month-practices` "{ $n } practices" (plural), `stats-month-rest` "{ $n } rest days" / «{ $n } день / дня / дней отдыха», breakdown labels reuse `status-*`, `context-*`, `series-name`, `length-summary` (short); `stats-online` "🌐 online: { $n }"; `stats-duration` "⏱ { $total } in total · about { $avg } per practice" with `stats-hm` "{ $h } h { $m } min" / «{ $h } ч { $m } мин»; `stats-unlogged` "{ $n } days without a mark: tap one to fill it in" / «{ $n } день / дня / дней без отметки: нажми на день, чтобы отметить»
  - `stats-cell-label`, `stats-show-ladies` / «Показывать 🌸 дни (видишь только ты)», `stats-month-empty`, `stats-load-failed`, `stats-prev` / `stats-next` (aria).

## 3. Design
### 3.1 Rules (domain, pure) ⚑ ashtanga-expert
Notation: **P** practiced (incl. pranayama-only, Q19), **R** rest-like (rest, moon, ladies, sick, travel), **N** "No practice", **·** not logged.
- **Possible days** = P + N in the period (logged days only). R never counts; **·** never counts against you (Q18). Example month: 18 P, 2 N, 6 R, 4 · → "18 of 20". y = 0 → the line is hidden.
- **Run** = the number of P days in a sequence where R days are transparent (neither add nor end), **N ends it quietly**, and **more than 3 consecutive ·** (strictly before today) end it quietly. Today, if not logged, never ends a run (the day isn't over).
  - `P P R P` → 3 · `P P N P` → current 1, longest 2 · `P · · · P` → 2 · `P · · · · P` → 1 · `P` + a week of sick + `P` → 2 · `P P` + today unlogged → current 2 · `P P N` + today → current 0 (hidden), longest 2.
  - Why a bridge of 3: it covers an unlogged day off next to an unlogged moon day plus one forgotten day; without any cap, someone returning after 3 months would see their old run continue, which is meaningless. The constant lives in the domain (`MAX_UNLOGGED_BRIDGE = 3`).
- **Month summary:** practices (P), possible, skipped (N), unlogged (· up to today), rest by kind (rest, moon, ladies, sick, travel), contexts (mysore/led/private/self + online count; unspecified not shown), **series bucket = the furthest series of the length** (0 = short; "½ Primary" → Primary; "Primary 2nd half + Intermediate" → Intermediate; none given → `unspecified`), duration total + count (avg = total / count, only practices with a duration).

### 3.2 Domain and use case
- `domain/stats.py`: `Cell = DayStatus | None`; `cells(days, start, end) -> list[Cell]`; `summarize(days, start, end, today, catalog) -> PeriodSummary`; `runs(days, today) -> list[Run(first, last, practices)]`; `current_run(runs, today)`; `longest_in(runs, year)` (a run touching the year counts in full, within the loaded window); `year_stats(...) -> YearStats(cells, months[12], year_total, current_run | None, longest)`. No I/O, no clock.
- `application/stats.py`: **`GetYearStats(days, moon, cities, catalog, clock).execute(principal, year=None) -> YearStatsView(today, timezone_known, year, first_year, location, moon_days, stats)`**. "Today" from the account zone, **provisional allowed** (display only, like `GetDays`). Raises `InvalidYear` (< 2000 or > local current year). Loads `[Jan 1 of year − 1 … min(Dec 31, today)]` so a run crossing New Year is whole (a run longer than ~2 years is clipped: documented limit). Own data only (`Principal`); a later teacher view goes through a policy and `public_status` projection, so it can never see 🌸.
- **Port:** `DayLogRepository.history(account_id, start, end) -> History(days, first_date)` = `list_range` plus `(SELECT min(local_date) … WHERE account_id = :id)` as a scalar subquery, **one statement**; `MoonCalendarRepository.days(location, Jan 1, Dec 31)` (existing) = statement 2. No migration and no new index: both are PK range scans (`day_log (account_id, local_date)`, `practice (account_id, local_date, slot)`, `moon_day (location, date)`).
- **Cost (estimate, measure as the first TDD step):** ≤ 731 day rows + practice rows, one PyNaCl open per rest row (~100/year, µs each), a linear domain pass: ~10–20 ms server time warm. The bot can reuse `GetYearStats` later unchanged.

### 3.3 API (initData auth, own data)

| Method, path | Request | Response |
|---|---|---|
| `GET /api/v1/me/stats?year=2026` | `year` optional (default: local current year) | 200 below; 422 `invalid_year` |

```
{ today, timezone_known, year, first_year: int | null,
  cells: [DayStatus | "none"],         // one per date, Jan 1 … min(today, Dec 31)
  moon: { location: slug, days: [{date, phase}] },
  months: [Summary × 12], year_total: Summary,
  runs: { current: int | null, longest: int } }   // current only for the current year
Summary = { practiced, possible, skipped, unlogged,
  rest: {rest, moon, ladies, sick, travel},
  contexts: {mysore, led, private, self}, online,
  series: [{number: 0..6, practices}], unspecified,
  duration: {total_min, count} }
```
~8 KB uncompressed for a full year. No ETag (the data changes with every log; the client caches `["stats", year]` with `staleTime` 60 s and **invalidates it from `settleDays`** after any day/practice mutation). Ladies' holiday is returned as `ladies` because only the owner calls this; the 🌸 toggle is purely presentational.

### 3.4 Mini App
`screens/Stats.tsx` (lazy), `Heatmap.tsx` (SVG `<rect>`s, ~12 px, 3 × 4 months), `MonthView.tsx` (CSS grid), `DayEditor.tsx` (TodayCard's chips + PracticeDetails extracted with a `date` prop; TodayCard becomes `DayEditor date={today}`). `useStats(year)`; `useDaysRange(from, to)` for the editor (the existing optimistic `useSetDay`/`useSavePractice` keep updating `["days","recent"]` and now also invalidate `["days", …]` and `["stats"]`). No new dependency. Estimate: initial +0.5 KB (button + view state), lazy chunk ~6–8 KB gzip (now 110.6/150).

## 4. Ops
None ☁️. No migration, no new secret or job.

## 5. Migration
None (§3.2).

## 6. Cross-cutting checks
- **Time zones:** all cells are stored **local dates**; nothing converts instants. "Today" and the current year come from the account zone (provisional for display only, `timezone_known` returned as `/me/days` does). Year and month boundaries are local calendar dates; DST is irrelevant. Moon markers use the followed calendar's dates as the same date (MD-03 rule); stored coverage is previous year … current + 2, so older years show no markers (no fallback computation on a request). Tests: Kiritimati vs Honolulu on 31 Dec/1 Jan, provisional zone, a run across New Year.
- **Privacy:** own data only; 🌸 drawn as rest unless the device-local toggle is on; the toggle never leaves the device. ST-07 cards and ST-06 must use `public_status` (noted in ADR-0020). Logs: account uuid + timing only.
- **i18n:** all copy in `app.ftl` en/ru with Fluent plurals (`$n`, `$y`, `$h`/`$m` abbreviated, no plural); month names and weekday initials via `Intl.DateTimeFormat` (RU standalone «октябрь»); numbers via `NUMBER`.
- **Responsiveness:** one HTTP request per year (months switch without fetching); 2 statements; stats chunk lazy; editor taps reuse the existing optimistic mutations (no extra round trip).

## 7. Test plan
- **Domain (`stats`):** every example in §3.1; possible days (unlogged and rest excluded; y = 0); bridge of exactly 3 vs 4; today unlogged; a moon-day practice counts; pranayama-only (no length) counts; series buckets (short, ½ Primary, 2nd half + Intermediate, Advanced A, unspecified); contexts + online; duration totals with missing durations; cells for a leap year and a partial current year; longest run touching the year; runs across New Year.
- **Use case (fakes, fixed clock):** default year from the account zone and the provisional zone; `InvalidYear` (1999, next year); window = previous Jan 1 … today; moon days of the followed city (default Mysuru); `first_year` None without data.
- **Infrastructure (real Postgres):** `history` returns days + practices + `first_date` in one statement; a sealed ladies row comes back as `ladies`; an unreadable seal → rest.
- **API contract:** shape and defaults; 422; 401 without initData; OpenAPI regenerated; `ladies` present for the owner.
- **Mini App (Vitest):** heatmap colours per state + moon ring + aria labels; the 🌸 toggle default off (ladies drawn as rest) and persisted; month tap → month view; year arrows bounded; day editor saves and invalidates stats; consistency/run lines hidden when y = 0 / n < 2; RU plurals (1, 2, 5, 21); bundle check (initial unchanged ±1 KB).
- **Bot:** none (no bot change). **Architecture:** import-linter (domain pure).

## 8. Open questions for the owner (recommendations)
1. **Scope** as §1 (Mini App stats + Mini App backfill via the month calendar; no bot `/stats`, no share cards yet)? Recommended: yes.
2. **Server-side stats** in a pure domain module behind one endpoint, rather than computing in the Mini App from `/me/days` (ADR-0020)? Recommended: yes: one request, tested once in Python, reused by the bot, ST-06 and ST-07.
3. **Layout:** 12 mini-month blocks (fits 360 px, tappable) instead of a horizontally scrolling 53-week GitHub strip? Recommended: yes. **Week starts Monday** in both languages? Recommended: yes.
4. **Possible days = practiced + "No practice"** (unlogged and rest-like never count; no percentages)? Recommended: yes ⚑. Revisit once PR-09 marks the weekly day off.
5. **Run rules (Q18):** rest-like days transparent, "No practice" ends a run quietly, more than 3 unlogged days in a row end it, today never ends it; current shown only from 2? Recommended: yes ⚑ (the bridge of 3 is the main judgement call).
6. **Pranayama-only day (Q19)** counts as a practice for consistency and runs? Recommended: yes for now (it's logged as Practiced); revisit with activity types.
7. **🌸 on the heatmap:** drawn as rest by default, with a device-local "Show 🌸 days" switch; the month summary merges ladies into rest unless it's on? Recommended: yes (screenshots, ST-07).
8. **Bot `/stats`** (a short month + run text with "Open the app") now or later? Recommended: later; the use case is ready, so it's ~1 hour when wanted.
9. **One practiced colour** (no shading by length or context)? Recommended: yes: length isn't a measure of a good practice.
10. **Copy ⚑:** "run" / «подряд» wording, "possible days", the hint line; ux-writer + ashtanga-expert settle before release? Recommended: yes.

## 9. Decisions (owner: all yes, 2026-10-19, with the ashtanga-expert's changes)
1–3. Scope, server-side stats (ADR-0020 accepted), 12 mini-months Monday-first: as proposed.
4. **Possible days** = P + N; rest-like and unmarked never count; no percentages. **When N = 0 the "of Y" part is hidden**: `stats-consistency-count` "This month: { $n } practices".
5. **Runs:** count P days only (Sat off and moon days never inflate: `P(Fri) ·(Sat) P(Sun)` → 2); R transparent; N ends quietly; **`MAX_UNLOGGED_BRIDGE = 7`** (more than 7 unmarked days in a row end a run; an unlogged ladies' holiday next to a day off and a moon day must not); today never ends a run; current shown from 2. Wording "in a row" / «подряд» only; never streak/broken/missed/record, «серия», «полоса», «цепочка».
6. Pranayama-only counts as practice; in the series breakdown it falls into **"No details" / «Без деталей»** (never a series label).
7. One practiced colour. 🌸 drawn as rest by default **everywhere on screen incl. `aria-label`s, tap emoji and the month summary**; switch "Show 🌸 days on this device" (device-local).
8. **Moon rings also on future days** of the current month (stored coverage allows it).
9. **"Unmarked days" line only for the current month**, counted strictly before today.
10. Later: bot `/stats`; a weekly count from the user's own day-off setting (PR-09), never "of 6".
11. Copy: the expert's lines (§2 replaced): `stats-consistency` "This month: practice on { $x } of { $y } days" / «В этом месяце: практика в { $x } из { $y } дня/дней»; `stats-run-current` "🌿 { $n } practices in a row"; `stats-run-longest` "Most in a row this year: { $n }" / «Больше всего подряд в этом году: { $n }»; hint "Only days you mark count. Rest, moon, sick and travel days keep the run going: rest is part of the practice."; legend "🌙 Moon day (rest)" vs the ring "Full or new moon · 📍 { $city }"; "Sick or travelling" / «Болезнь или поездка»; "Not marked"; breakdown header "By series" / «По сериям» (never "series reached"); `stats-unlogged` "{ $n } unmarked days: tap a day to add it". ux-writer polish.

## 10. Implementation notes and review fixes (2026-10-19)
- **Measured** (local Postgres, warm): a heavy user with 657 logged days and practice rows: `history` query ~11 ms, domain pass ~2 ms. Stats chunk 3.4 KB gzip (lazy); initial JS 113.0 KB (+2.4 KB, mostly the new copy, bundled with the first load).
- **Code-review blocker fixed:** day/practice mutations now update **every** cached day query optimistically (the recent week and the editor's ranges, a range only for dates inside it) and roll all of them back on error. Before, a quick second tap on an old day sent a stale body and wiped the first detail.
- **Privacy:** the day editor follows the 🌸 switch: with it off a ladies' holiday shows as Rest pressed, the 🌸 chip is hidden, and tapping Rest doesn't downgrade the stored status.
- **Runs across New Year** are counted whole from both years: the use case loads previous year … next year (to today).
- **UI fixes:** "No practice" count shown without rest days; consistency line hidden while nothing is practised this month; "most in a row" from 2; the unmarked-days invitation also in an empty current month; moon days and today named for screen readers (`aria-current="date"`); month grid is a labelled group; dark day numbers on pastel cells (dark theme); an on-screen "‹ Back" when Telegram's Back button is unavailable; returning to the current year reuses its cache.
- **Tests added:** Kiritimati vs Honolulu on 31 Dec (default year, next-year boundary), `year=0` → 422, a past-year run into January, a "No practice" today.
- **Known limits / follow-ups:** only slot 1 feeds contexts/series/duration (one practice per day for now); stored moon calendars start at the previous year, so older years show no rings; the month's unmarked count includes days before someone's first log (an invitation to backfill).
