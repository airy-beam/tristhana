# ST-05: check-in trends (mood, energy and effort by month, weekday and near full / new moon)

- Status: **accepted 2026-11-11** (architect; ashtanga-expert reviewed, copy in §2 adjusted; owner: all as recommended, Q284–Q292; ux-writer polishes §2 during the build) · Size **S–M** (about 2 days), Phase 3, priority C
- Requirements: **ST-05** ("Check-in trends: energy/effort over time, correlation with moon phase/weekday"). Reads **PR-06** data (`check_in`), the **MD-02/03** stored moon calendar and the followed city. Touches nothing in **ST-06** (teachers), **ST-07** (share cards), **ST-09** (export), **GM-02**.
- Related: ADR-0020 (rules server-side, the client only draws; hand-written SVG/CSS), ADR-0024 (check-ins plain, owner-only; the practiced join), ADR-0019 (stored calendars), ADR-0032/0033 (followed city), ADR-0041 (read-time projection). **No ADR:** no chart library (nothing here needs interaction, so ADR-0020's "revisit for ST-05" is answered with "not needed"), no stored aggregate, no migration.

## 1. Scope
**In:** a read-only Mini App screen (lazy chunk) opened from 📊 My practice, showing the person's own check-in averages for the **last 12 calendar months**: (a) by month, (b) by weekday, (c) near full moon / near new moon / other days. One endpoint `GET /api/v1/me/check-in-trends`, one use case `GetCheckInTrends`, one pure module `domain/check_in_trends.py`, one read statement.

**Out:** tags of any kind (Q290); a bot screen or command (Q284); a period picker or older years; day-level points or a list of days; any comparison in words ("higher on…", differences, arrows, best/worst, ranking, colours for high/low); any explanation of weekday differences (Led day, the day after rest, Friday Primary); a count for the moon day on its own; statistics words (correlation, significant, trend line); advice or inference of any kind (PR-06 §1); percentages; teacher, shala or share-card views; export changes (ST-09 already exports every check-in; nothing new is stored); notifications.

**Tone:** a quiet description of the person's own numbers. The app never says energy *is* different near a moon day or on a weekday: it shows the figures and how many check-ins they come from, and says nothing when there are too few. No scale is "good" (effort 5 is not better than effort 2).

## 2. User flow and copy
**Mini App.** 📊 My practice → a row button `trends-open` under `badges-open` → `screens/trends/Trends.tsx` (`React.lazy` from the already lazy Stats chunk; My practice stays mounted and hidden, as for Badges; Telegram BackButton, fallback `stats-back`). Top to bottom at 320–360 px:
1. Title, then `trends-window`.
2. **By month:** three small SVG strips (mood, energy, effort), 12 columns each, one dot per month at the height of its average on a fixed 1–5 axis with faint lines at 1, 3 and 5. **Dots only, never a line** (a line would draw values for months that have none). The scale ends reuse `checkin-energy` / `checkin-effort` and the mood emoji 😔 / 😊. Month initials via `Intl`. Under each strip, a visually hidden table with the same numbers.
3. **By weekday:** a CSS grid, 7 columns Monday first (as Stats) × 3 rows; each cell is the average to one decimal with the count in small type under it.
4. **Near full and new moon:** the same grid with 3 columns (`trends-moon-full`, `trends-moon-new`, `trends-moon-other`), then `trends-moon-note` naming the city.
5. `trends-gap-note` (only when a "—" is on screen) and `trends-note`.

A cell or month under the minimum (§3) shows "—" or no dot, with no explanation of why. Sections 3 and 4 are left out whole when the server returns `null`. No haptics, no animation, no tap targets.

**States:** no check-in with a scale in the window → `trends-empty`. Fewer than `MIN_TOTAL` → `trends-too-few` (states the threshold, never a count "to go"). Load error → `trends-load-failed`.

| Key (`trends.ftl`, lazy; `trends-open` in `app.ftl`) | EN | RU |
|---|---|---|
| `trends-open` | ✨ Check-ins over time | ✨ Самочувствие за год |
| `trends-title` | Check-ins over time | Самочувствие за год |
| `trends-window` | The last 12 months, from the check-ins you add after practice. | Последние 12 месяцев, по твоим отметкам самочувствия после практики. |
| `trends-by-month` / `-by-weekday` / `-by-moon` | By month / By weekday / Near full and new moon | По месяцам / По дням недели / Около полнолуния и новолуния |
| `trends-scale` (selector `$scale`) | Mood / ⚡ Energy / 🔥 Effort | Настроение / ⚡ Энергия / 🔥 Усилие |
| `trends-moon-full` / `-new` / `-other` | 🌕 Near full moon / 🌑 Near new moon / Other days | 🌕 Около полнолуния / 🌑 Около новолуния / Остальные дни |
| `trends-moon-note` | "Near" is the day of the full or new moon, the day before and the day after. Dates for 📍 { $city }. | «Около» — день полнолуния или новолуния, день до и день после. Даты для 📍 { $city }. |
| `trends-n` (plural `$n`) | { $n } check-in / check-ins | { $n } отметка / отметки / отметок |
| `trends-cell-label` (aria; plural `$n`) | { $scale }, { $where }: { $mean } on average, { $n } check-ins | { $scale }, { $where }: в среднем { $mean }, { $n } отметка / отметки / отметок |
| `trends-gap-note` | "—" means fewer than { $min } check-ins there. | «—» значит, что там меньше { $min } отметок. |
| `trends-empty` | Nothing here yet. Check-ins you add after practice will show up here. | Здесь пока пусто. Отметки самочувствия после практики появятся здесь. |
| `trends-too-few` | Averages appear here from { $min } check-ins. | Средние появятся здесь начиная с { $min } отметок. |
| `trends-note` | These are averages of your own check-ins. The app draws no conclusions from them. Teachers and shalas don't see them. | Это средние по твоим отметкам. Приложение не делает из них выводов. Учителя и шалы их не видят. |
| `trends-load-failed` | Couldn't load this. Try again in a moment. | Не получилось загрузить. Попробуй чуть позже. |

Reused: `checkin-energy`, `checkin-effort`, `checkin-mood-chip`, `stats-back`. RU «ты», no gendered forms; «меньше { $min } отметок» / «начиная с { $min } отметок» are right for 5–20 (a test pins `MIN_TOTAL` and `MIN_BUCKET` inside that range). «Отметки самочувствия» on first mention, so «отметка» is not read as a practice log. **Avoid-word grep** over `trends-*`: the PR-06 §6 list (incl. only / «только», should, bad, pain) plus streak, broken, missed, better, worse, lower, higher, because, affects, influence, depends, correlat, trend, tend, pattern, normal, cycle, score, usually; RU «влия», «завис», «коррел», «тренд», «обычно», «лучш», «худш», «хуже», «выше», «ниже», «норм», «цикл», «из-за», «потому». "Full moon" / "New moon" only (never Purnima / Amavasya here).

**Bot:** nothing (Q284).

## 3. Domain (pure) `domain/check_in_trends.py`
```python
MONTHS = 12        # the window: the 1st of the month 11 months before today's month .. today
MIN_TOTAL = 10     # check-ins with at least one scale in the window, before anything is shown
MIN_BUCKET = 5     # values of one scale in one month / weekday / moon bucket, before its average is shown
NEAR_DAYS = 1      # "near" a full or new moon: |local_date - moon date| <= 1
class Scale(StrEnum): MOOD, ENERGY, EFFORT
class MoonBucket(StrEnum): FULL, NEW, OTHER
@dataclass(frozen=True, slots=True)
class ScaleDay: local_date: date; mood: int | None; energy: int | None; effort: int | None
@dataclass(frozen=True, slots=True)
class TrendFacts: days: tuple[ScaleDay, ...]; moon: tuple[MoonDay, ...]   # moon: window widened by NEAR_DAYS
@dataclass(frozen=True, slots=True)
class Average: tenths: int; n: int                    # mean x 10, rounded half up in integer arithmetic
Averages = Mapping[Scale, Average | None]             # None = under MIN_BUCKET
@dataclass(frozen=True, slots=True)
class Trends: start: date; end: date; total: int; enough: bool
              months: tuple[tuple[date, Averages], ...]            # 12, oldest first; () unless enough
              weekdays: tuple[Averages, ...] | None                # 7, Monday first
              moon: Mapping[MoonBucket, Averages] | None
def window(today: date) -> tuple[date, date]
def average(values: Sequence[int], minimum: int = MIN_BUCKET) -> Average | None
def moon_bucket(day: date, moon: Iterable[MoonDay], near: int = NEAR_DAYS) -> MoonBucket
def trends(facts: TrendFacts, today: date) -> Trends
```
- **Counted per scale:** every scale is optional, so `n` is the number of check-ins that have *that* scale. A row with tags only is not counted anywhere (`total` counts rows with at least one scale).
- **Weekday** = `local_date.isoweekday()`: the day as the person lived it; later travel never moves it.
- **Moon bucket:** FULL if within `NEAR_DAYS` of a `purnima` / `kshaya_purnima` date, NEW likewise for `amavasya`, else OTHER (`MoonDayKind.phase`). The moon day itself is inside "near": most people rest on it, so a bucket of that day alone would stay empty (Q288). Full and new moons are about 14 days apart, so no date is in both.
- **Under the minimum → `None`, decided here**, so the API never carries a small-sample average and no client can show one. `enough = total >= MIN_TOTAL`; when false, `months = ()`, `weekdays = None`, `moon = None`.
- **Section rules:** `weekdays` is `None` unless at least 2 weekdays have an average for some scale. `moon` is `None` unless the calendar has dates in the window, OTHER has an average, and FULL or NEW has one for the same scale.
- The module holds no words and no comparisons: no "highest", no differences, no ordering by value.

## 4. Application, port, infrastructure
- **Use case** `application/check_in_trends.py`: `GetCheckInTrends(trends, cities, clock).execute(principal) -> TrendsView(trends: Trends, city: City)`. Policy: the existing `can_view_check_ins(account, account)` (owner only; no new policy). Zone = account zone or provisional (display only, as Stats and Badges); `today` local; city = `moon_follow_of(account, cities).city`.
- **Port** `application/ports/check_in_trends.py`: `CheckInTrendsRepository.facts(account_id, moon_location, start, end) -> TrendFacts`, on `Storage.check_in_trends`.
- **Infrastructure** `infrastructure/db/check_in_trends.py`, **one statement**, two single-row aggregates cross-joined (the `db/badges.py` pattern):
  - `scales`: `array_agg` of `local_date, mood, energy, effort` from `check_in c JOIN day_log d USING (account_id, local_date)` `WHERE c.account_id = :me AND c.slot = 1 AND d.status = 'practiced' AND c.local_date BETWEEN :start AND :end AND (c.mood IS NOT NULL OR c.energy IS NOT NULL OR c.effort IS NOT NULL)`. `tags` and `sealed_status` are never selected.
  - `moon`: `array_agg(date, kind)` from `moon_day WHERE location = :loc AND date BETWEEN :start - 1 AND :end + 1`.
- **Bucketing lives in the domain, not SQL** (ADR-0020): thresholds and "near" are rules with tests, and at most 366 rows cross the wire.
- **Cost:** the window bounds the read whatever the account's age: a PK range of at most 366 `check_in` rows, a PK join to `day_log`, about 27 `moon_day` rows. Expected 2–4 ms; the 9 000-day test account reads the same 366 rows. Domain pass O(n), under 1 ms. No write path changes; bot unchanged.
- **Followed city:** the city followed *today* is used for the whole window. The follow is resolved at read time and has no history (ADR-0032), exactly as the Stats rings and Badges work; cities differ by at most a day, which the ±1 window mostly absorbs (Q289). The window never starts before 1 January of the previous year, so it is always inside the stored calendars (ADR-0019).

## 5. API (initData; additive; `gen:api`)
| Method, path | Auth / policy | Response |
|---|---|---|
| `GET /api/v1/me/check-in-trends` | initData; owner (`can_view_check_ins`) | `CheckInTrendsOut {from: date, to: date, total: int, enough: bool, min_total: int, min_bucket: int, months: [{month: "YYYY-MM", mood: AvgOut \| null, energy: AvgOut \| null, effort: AvgOut \| null}], weekdays: [ScalesOut × 7] \| null, moon: {location: slug, full: ScalesOut, new: ScalesOut, other: ScalesOut} \| null}`; `AvgOut {mean: number (one decimal), n: int}` |

A new endpoint rather than more fields on `/me/stats`: stats are keyed by year and refetched after every day mutation, while this has its own window and is opened rarely. No parameters, no new `ErrorCode`; 401/503 as the router. Client: `useCheckInTrends()` with key `["me", "check-in-trends"]` and `staleTime: 0` (the screen unmounts on Back, so each opening refetches; no invalidation code is added to the initial bundle).

## 6. Migration
**None.** `check_in`'s PK `(account_id, local_date, slot)`, `day_log`'s PK and `moon_day (location, date)` serve the statement; the app role already reads all three. `alembic check` stays clean.

## 7. Cross-cutting checks
- **Time zones:** only stored `local_date`s; no instant is read (`created_at` / `updated_at` unused), so no time and no zone label appears; the moon note carries the 📍 city. `today` and the window's month edges are local calendar dates in the account zone. Month and weekday names via `Intl` with `timeZone: "UTC"` on date strings. Tests: Kiritimati vs Honolulu on the last day of a month; a provisional zone; a check-in logged in Almaty still counts on its own weekday after a move to Lisbon.
- **Privacy:** owner-only by policy; the response holds aggregates only, never a date of a practice or a rest. **🌸:** a ladies' holiday is stored with plain status `rest`, so the `status = 'practiced'` join can never read a check-in on such a day, including a stray row left by the ADR-0024 race; `sealed_status` is not in the statement. Nothing on screen describes absence: a month or bucket with too few check-ins is blank, with no text about a gap, no "no check-ins in…" and no rest counts, so a screenshot shows less than the heatmap already does. Nothing reaches teachers (not even "missing"), shalas, share cards, logs (account uuid only) or the export (unchanged).
- **i18n:** all copy in `trends.ftl` (en, ru) plus one `app.ftl` key; parity and variable tests; RU plurals through Fluent (`trends-n`, `trends-cell-label`); numbers through `Intl.NumberFormat` ("3.4" / «3,4»).
- **Responsiveness:** one GET, one statement, target well under 300 ms p50 warm. **Bundle:** `Trends.tsx` + `trends.ftl` ≈ 2.5–3 KB gzip, lazy, no dependency; the lazy stub sits in the Stats chunk; the initial bundle gains one Fluent key per locale, ≈ +0.05 KB (147.1 → ~147.2 of 150). Generated API types add no runtime code. `check:bundle` must pass; RU at 320 px (7 columns of one-decimal numbers, scale rows labelled by emoji with visually hidden names).

## 8. Test plan
- **Domain:** `window` (mid-month, 1 January, 29 February, 31st); `average` at 4 / 5 / 6 values and half-up rounding (3.25 → 3.3, 3.35 → 3.4); per-scale counting (energy on 6 days, effort on 4 → energy shown, effort `None`); a tags-only row counts nowhere; `total` 9 vs 10 (`enough`, empty sections); `moon_bucket` at −2 / −1 / 0 / +1 / +2 days for full and new, kshaya kinds, a date outside any calendar → OTHER; weekdays by ISO day with Monday first; `weekdays` `None` with one weekday filled; `moon` `None` with an empty calendar, without OTHER, or with FULL at 4; months oldest first, a month under the minimum → `None`; no input → `total = 0`.
- **Use case (fakes, fixed clock):** owner only; window and `today` from the account zone and from a provisional zone; city via `moon_follow_of` (chosen, follow-teacher, shala, Mysuru default); one repository call.
- **DB (real Postgres):** one statement (counter); **a stray `check_in` row on a day now stored as `rest`, on a `skipped` day and on a sealed 🌸 day is not returned**; `sealed_status` and `tags` absent from the compiled SQL; a tags-only row not returned; rows outside the window not returned; moon dates include the day before `start` and after `end`; another account's rows never returned; `tristhana_app` role read; under 60 ms on the 9 000-day account (Q283's limit; expected ~3 ms); `alembic check` clean.
- **API contract:** 401; empty account (`total = 0`, `enough = false`, `[]`, nulls); too few; a full payload with `null` cells; `min_total` / `min_bucket` equal the domain constants; OpenAPI regenerated and the TS client builds.
- **Bot:** none (no change; suites stay green).
- **Mini App (Vitest, also `TZ=UTC`):** the row on My practice opens the lazy screen and Back returns to the same month; empty state; too-few state shows no numbers; dots only for months with an average and no `<line>` / `<path>` between dots; "—" cells and the gap note only when one is present; weekday and moon sections absent on `null`; aria labels and the hidden tables; RU plurals at 1 / 2 / 5 / 21; "3,4" in RU; city name in the moon note; load failure; an older payload without `moon` renders.
- **i18n:** en/ru key parity for `trends.ftl`; every key formats with its variables; the avoid-word grep (§2).
- **Architecture / budget:** import-linter (domain pure, no aiogram); `check:bundle` (initial ≤ 150 KB; delta ≤ 0.2 KB).

## 9. Build order
1. Domain module + tests. 2. Port, SQL statement, DB tests (incl. the stray rows and timing). 3. Use case + fakes. 4. API route, schemas, OpenAPI, `gen:api`. 5. `trends.ftl` (ux-writer + ashtanga-expert before the final suite) and the screen with its tests. 6. `check:bundle`, 320 px RU check, then `/guide-update ST-05` and the notes.

## 10. Questions for the owner (answered 2026-11-11: **all as recommended**)
284. **Surface.** (A) Mini App only, a lazy screen opened from 📊 My practice; no bot screen. (B) Also a bot summary. **Recommended: A** (the bot has no `/stats` yet, Q32; this is a look-back screen).
285. **Window and step.** (A) The last 12 calendar months, by month, one window for all three views. (B) The last 12 weeks by week for "over time", 12 months for weekday and moon. (C) A year picker as on My practice. **Recommended: A:** one sentence explains it, monthly averages are steadier than weekly ones (2–6 values a week invites reading noise), and it always fits the stored moon calendars.
286. **Mood** shown next to energy and effort? **Recommended: yes** (same read, same rules; the requirement names only energy and effort).
287. **Minimums.** (A) 10 check-ins before anything, 5 per month / weekday / moon bucket. (B) 10 and 8. (C) 20 and 10. **Recommended: A:** with ±1 day a moon bucket fills in about 3 months; every figure shows its count, and nothing is compared in words.
288. **Moon buckets** (ashtanga-expert 2026-11-11: A; ±1 day absorbs the one-day city / shala differences, and including the moon day never singles out who practised on it). (A) Near full moon and near new moon separately, each = the day, the day before and the day after; all other days as the third column. (B) The moon day alone (stays nearly empty: people rest). (C) ±2 days. (D) Full and new merged into one "near a moon day". **Recommended: A.**
289. **Calendar.** The city followed today, for the whole window (no history of follows exists). **Recommended: yes**, with the city named in the note.
290. **Tags.** (A) Not in this version. (B) Plain counts per tag for the window, in the PR-06 order, never ranked. **Recommended: A:** the requirement does not ask for them and "Sore muscles: 14" is the line most likely to read as a health statement; the response can gain a `tags` field later without a break.
291. **Figures.** (A) Average to one decimal plus the number of check-ins. (B) Dots only, no figures. (C) Counts of each value 1–5. **Recommended: A:** the count is what keeps a small sample honest.
292. **Names.** "Check-ins over time" / «Самочувствие за год» (ashtanga-expert: «со временем» reads as "eventually") and "Near full and new moon" / «Около полнолуния и новолуния»; the closing line `trends-note`. **Recommended:** accept as working copy; ux-writer and ashtanga-expert finalise (the moon wording must describe, never assert an effect).

## 11. Build notes (2026-11-11)
- **As built:** domain `domain/check_in_trends.py`, use case `GetCheckInTrends`, `SqlCheckInTrendsRepository` (one statement; about 6 ms on the 9 000-day test account), `GET /api/v1/me/check-in-trends` (schemas `CheckInTrendsOut`, `TrendsMonthOut`, `TrendsMoonOut`, `ScalesOut`, `AvgOut`), lazy `screens/trends/Trends.tsx` (3.3 KB gzip; initial JS unchanged at 147.1 KB), `trends.ftl` (en, ru).
- **Copy (ux-writer):** mood is 💭 (🙂 is a value on the scale); `trends-count-hint` says the small number under each average is the number of check-ins behind it; a dash cell is read aloud as "no average"; `trends-empty` speaks of averages. Extra keys beyond §2: `trends-scale-icon`, `trends-count-hint`, `trends-none`, `trends-cell-none`, `trends-mood-ends`. `trends-n` was dropped: the visible count is a bare number, and the plural lives in `trends-cell-label`.
- **Deviations:** the visible count under a figure is the number alone (seven columns at 320 px leave no room for a word); no separate `tristhana_app` role test (no new table or grant: the role already reads `check_in`, `day_log` and `moon_day` in production).
- **Review (code-reviewer):** no blockers. Fixed: a second `MoonOut` schema renamed the stats one in the generated client (now `TrendsMoonOut`); the contract test now scans the right schemas; axis ends on the month strips; six added tests. Left as nits: emoji inside the read-aloud labels, `aria-label` on plain table cells.

