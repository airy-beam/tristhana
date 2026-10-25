# PR-09: weekly day off and auto-filled rest days (moon days + day off)

- Status: **accepted** (owner, 2026-10-25: "all yes"; ashtanga-expert review applied) · Date: 2026-10-25
- Requirements: **PR-09** (auto-fill: moon days and the weekly day off are pre-marked as rest; the user can override). Settles **Q21** (explicit always wins) and the 07 Moon Days question (moon day on the day off). Touches PR-01/04 (day screens), PR-10 (reminder days), ST-01..03 (cells, summary), ID-06 (settings). Budget: < 300 ms p50 per tap (warm).
- Related: ADR-0005, 0008, 0016, 0018, 0019, 0020, 0021. New: **ADR-0022** (auto-rest derived at read time; Accepted).

## Amendment (owner, 2026-10-25, after go-live): one day setting
Two settings (the day off and the reminder days) were confusing. Now:
- **Days off: up to two** (`MAX_DAYS_OFF = 2`; e.g. Mysore Mon–Fri shalas). The other days are the **practice days**, and **practice reminders come on them only**: reminder days are never chosen separately.
- Stored custom reminder days are dropped (migration **0008** sets `practice_days` NULL; the column stays until a later contract migration). `PATCH /me/notification-settings` `practice.days` is deprecated and ignored; `DayOffOut` = `{day_off, practice_days}` (no `reminder_days_reset`).
- Bot: the day-off picker toggles days (😌 = day off) and stays open (`s1:o:<digits|0>`, `r1:dt:<digits|0>`); with two days off a third tap just reshows the picker. `/remind` has no day buttons: a "They come on your practice days" line and a [😌 Day off] button (`r1:dp`). Old `r1:w:*` keyboards reshow `/remind`. `/settings`: "😌 Days off: Saturday, Sunday".
- Mini App: Day off chips toggle (pressed = day off, a third is disabled until one is unpressed); the reminder card shows "On your practice days: …".
- Sections below that describe custom reminder days, the "now follow your day off" note and one day off are superseded by this amendment.

## 0. Implementation plan (in order; TDD per step)
1. **Domain**: new `domain/rest_days.py`; `domain/accounts.py` (`Account` fields); `domain/notifications.py` (`reminder_days`, `defaults_for`, `day_off_question`); `domain/stats.py` (`auto` input). Tests: `tests/domain/test_rest_days.py` (new), `test_notifications.py`, `test_stats.py`, `test_accounts.py`.
2. **Application**: `ports/days.py` (`RangeView`, `range_with_moon`), `ports/accounts.py` (`set_day_off`, `dismiss_day_off_question`), `ports/notifications.py` (`reset_practice_days`); `application/days.py` (`GetDays` + `Cities`), `application/stats.py`, new `application/rest_days.py` (`SetDayOff`, `DismissDayOffQuestion`); `settings.py`, `remind.py`, `moon.py`, `tick.py` pass `defaults_for(account.day_off.days)` instead of `DEFAULTS`. Wiring: `main.py`, `api/deps.py`, `bots/telegram/runtime.py`.
3. **Infra + migration**: `infrastructure/db/migrations/versions/0007_day_off.py`; `db/tables.py`; `db/accounts.py` (columns, mask helpers, 2 methods); `db/days.py` (`range_with_moon`, one statement); `db/notifications.py` (`reset_practice_days`, `candidates` selects `account.day_off`); `db/storage.py` (stub).
4. **API**: `api/v1/me.py` (`Me.day_off`, `PUT /me/day-off`, `DELETE /me/day-off-question`), `api/v1/days.py`, `api/v1/stats.py`, `api/v1/moon.py` (`day_off_question`); `uv run tristhana-openapi`.
5. **Bot**: `settings_callbacks.py`, `remind_callbacks.py`, `settings.py`, `remind.py`, `days.py`; `locales/{en,ru}/bot.ftl`.
6. **Mini App**: `npm run gen:api`; `settings/DayOffSection.tsx` (new), `Settings.tsx`, `PracticeReminderCard.tsx`, `TodayCard.tsx`, `stats/{Stats,Heatmap,DayEditor,cells}.ts(x)`, `api/client.ts` hooks, CSS, `locales/{en,ru}/app.ftl`.

## 1. Scope
**In:** one weekly day off (Mon…Sun or "No fixed day off"); auto-rest (an *unlogged* day from the join date to today shows 🌙 or 😌); reminder days follow the day off; a one-time "is that your day off?" question on `/remind` and the Mini App stats card (never in a push); the stats "Set your weekly day off" link.
**Out:** Q32 weekly count; future days; two days off (the API shape is ready); a moon auto-fill toggle; a full day-off history table; shala swap days (Phase 3 schedules); WH-01 ranges; MD-04; teacher views (ST-06 reuses the rule, see ADR-0022).

## 2. Rules and flows
- **Auto-rest (⚑ ashtanga-expert).** Only days with **no log**, in `[joined, today]`, where `joined` = the local date of `account.created_at` in the account zone (provisional if unknown). Moon day of the followed city → 🌙. If it also falls on the day off: still 🌙, with the "and your day off" clause (no shift, no extra day). Else the day off in effect on that date → 😌. A log always wins. "✕ Clear" brings the auto status back.
- **History.** The first choice (from never chosen) applies to all history from `joined`, and so does a correction made the same local day (a mis-tap). A later change applies from local today, and earlier dates keep the previous value (`day_off_since`/`day_off_before`).
- **Never chosen** = no day-off auto-fill. Reminders keep today's default (all but Saturday).
- **Reminder days follow the day off.** Choosing a day off sets `practice_days = NULL` (= follow). If the stored days were custom and differ from the new ones, the next screen shows `day-off-reminders-follow` + `[✏️ Reminder days]`. The per-weekday toggles still customise.
- **Bot.** `/settings` S gains `settings-day-off-line` / `-none-line` / `-unset-line` and `[😌 Day off]` → **O**: `day-off-pick` + `day-off-explain`, `[Sat] [Sun]` / `[Mon]…[Fri]` / `[No fixed day off]` / back, with ✓ on the current choice. `/remind` R: the `[Day off: Sat] [Day off: Sun]` presets set the day off (✓ iff `day_off == {d}`). **Question on R** (above `remind-explain`), shown iff `day_off` is never chosen, not dismissed, and the reminder days miss **exactly one** weekday `d` (skipped otherwise): `day-off-ask` + `[Yes]` (= d), `[Sunday]`/`[Saturday]` (the other weekend day; omitted when d is Mon–Fri), `[Other…]` (O, opened from R), `[Not now]`. Day screens (`/log`, `d1:o:`): on an auto day no chip has ✓, and `log-auto-moon`/`log-auto-day-off` goes above the prompt. Week picker: auto days show 🌙/😌.
- **Mini App.** Settings: a **"Day off"** section (between Time zone and Moon days) with chips `remind-weekday` 1…7 (Mon first) + `[No fixed day off]`, single-select, nothing pressed while unset, hint `settings-day-off-hint`. Today: on an unlogged auto day show `today-auto-moon` (replaces `moon-today` while unlogged) or `today-auto-day-off`, with no chip pressed. Heatmap/month: cell kind **auto** (rest hue at ~45 % with a dashed 1 px inner border; the moon ring stays on top), `aria-label` = `title` = `stats-cell-auto`, legend `stats-legend-auto`. DayEditor: the same `today-auto-*` line. Stats consistency card: the question (same rule) or, after dismissal/when skipped and still unset, `stats-day-off-link` → Settings#day-off. Reminder card presets → `PUT /me/day-off`.

## 3. Domain (pure)
```python
# domain/rest_days.py
Weekdays = frozenset[int]            # ISO 1..7
MAX_DAYS_OFF = 1                     # raise to 2 later (additive)
@dataclass(frozen=True) class DayOff:
    days: Weekdays | None = None     # None = never chosen, frozenset() = no fixed day off
    since: date | None = None        # the local date of the last choice
    before: Weekdays | None = None   # in effect before `since`; None = `days` applies to all history
class InvalidDayOff(ValueError)
def check_day_off(days) -> Weekdays          # ≤ MAX_DAYS_OFF, ⊆ 1..7, no duplicates
def day_off_on(off, d) -> Weekdays           # before if it is set and d < since, else days; None → ∅
def change_day_off(off, new, today) -> DayOff
    # never chosen → DayOff(new, today); same → off; since == today → replace(days=new);
    # else → DayOff(new, today, off.days)   (older periods fold: accepted limit)
class AutoKind(StrEnum): MOON = "moon"; DAY_OFF = "day_off"
@dataclass(frozen=True) class AutoDay: kind: AutoKind; also_day_off: bool = False
def auto_days(start, end, today, joined, logged: Set[date], off, moon: Set[date]) -> dict[date, AutoDay]
    # dates in [max(start, joined), min(end, today)] not in `logged`
def joined_on(created_at: datetime, zone: str) -> date   # local_today(created_at, zone)
```
- `Account` += `created_at: datetime`, `day_off: DayOff = DayOff()`, `day_off_dismissed: bool = False`.
- `notifications`: `reminder_days(days_off)`: None → `{1,2,3,4,5,7}`, ∅ → all 7, else `WEEKDAYS - days_off`. `defaults_for(days_off)` = `DEFAULTS` with `practice.days = reminder_days(…)` (so `practice_days IS NULL` = follow; every repo call keeps its `defaults` parameter). `day_off_question(account, settings) -> DayOffQuestion(weekday, reminders_on) | None`.
- `stats`: `summarize(…, auto)` puts auto MOON in `rest[MOON]` and DAY_OFF in `rest[REST]`, adds `Summary.auto`, and leaves them out of `unlogged`. `possible` is unchanged. **`find_runs` unchanged** (auto stays unmarked for the 7-day bridge). `YearStats` += `auto`.

## 4. Application
- `GetDays(days, cities, clock)`: `range_with_moon(id, start, end, city_slug) -> RangeView(days, moon_dates)` in **one statement** (UNION ALL of the range query and `moon_day`). `DaysView` += `auto`, `city: City`.
- `GetYearStats`: `auto_days(…)` from the moon days it already loads (2 statements).
- `SetDayOff.execute(principal, days) -> DayOffSaved(account, settings, reminders_reset: bool)`: `check_day_off`, `change_day_off(…, local today)`, then `accounts.set_day_off` (UPDATE … RETURNING) and `notifications.reset_practice_days(id, defaults_for(new))` (one UPDATE with a CTE returning the previous `practice_days`; no row → nothing to reset). `reminders_reset` = the previous value was not NULL and ≠ `reminder_days(new)`. **2 statements.** Raises `InvalidDayOff`.
- `DismissDayOffQuestion`: `UPDATE account SET day_off_dismissed_at = now() WHERE … AND day_off_dismissed_at IS NULL RETURNING`. 1 statement, idempotent.
- Tick: `candidates` selects `account.day_off` → `effective(stored, defaults_for(mask))`. No new statement. `logged` stays logged rows only.

## 5. API (initData auth, own account via `Principal`; additive only)
| Method, path | Request → Response |
|---|---|
| `GET /api/v1/me` | `Me` += `day_off: list[int] \| null` (ISO 1–7 ascending; `[]` = no fixed day off; null = never chosen) |
| `PUT /api/v1/me/day-off` | `{day_off: list[int]}` → `DayOffOut{day_off: list[int], practice_days: list[int], reminder_days_reset: bool}`; 422 `invalid_day_off` (> 1 element, out of range, duplicates); a `null` or non-integer body fails the schema (plain 422). A re-tap of the current day off writes nothing (custom reminder days survive). The schema is `list[int]` with no `maxItems`, so 2 days later change only the domain limit. |
| `DELETE /api/v1/me/day-off-question` | → 204 (idempotent) |
| `GET /api/v1/me/notification-settings` | += `day_off_question: {weekday: int, reminders_on: bool} \| null`; `practice.days` follows the day off when not customised |
| `GET /api/v1/me/days` | `Days` += `auto: list[AutoDayOut]`, `AutoDayOut{date, kind: "moon" \| "day_off", also_day_off: bool}` (default `[]`), and `moon_location` (the followed city's slug: the Mini App names it in auto moon notes) |
| `GET /api/v1/me/stats` | `StatsOut` += `auto: list[AutoDayOut]` (the year, ≤ today); `SummaryOut` += `auto: int`; `unlogged` excludes auto; `rest.rest`/`rest.moon` include it |
`cells` keep their enum, so an old cached bundle draws auto days as "none".

## 6. Bot callback data (absolute values; ≤ 64 bytes)
| Data | Meaning |
|---|---|
| `s1:o` | O, opened from settings (picks `s1:o:*`, back `[⚙️ Settings]`) |
| `s1:o:6` / `s1:o:0` | set the day off (ISO digit; `0` = none) → S (+ follow note if reset) |
| `r1:d:6` / `r1:d:0` | set the day off → R (presets, question Yes/other weekend day, O from R) |
| `r1:dp` | O, opened from R (picks `r1:d:*`, back `remind-practice-link`) |
| `r1:dn` | question: not now → R |
Decoders accept one digit `0`–`7` only (multi-digit → None, reserved for two days off). Old `r1:w:*` keep working. Round trips: S/O/R = middleware + 1. A set = middleware + 2 + 1 (re-render read). Day screens = middleware + 1; "✕ Clear" = middleware + 2 (it reads the day back to show the auto note).

## 7. Migration `0007_day_off` (expand-only, down_revision `0006`)
- `account` add `day_off smallint NULL` (bitmask, bit `d-1` = ISO weekday d; 0 = none), `day_off_since date NULL`, `day_off_before smallint NULL`, `day_off_dismissed_at timestamptz NULL`. CHECKs: `day_off BETWEEN 0 AND 127` (`day_off`), `day_off_before BETWEEN 0 AND 127` (`day_off_before`), `day_off_before IS NULL OR day_off_since IS NOT NULL` (`day_off_period`), `day_off_since IS NULL OR day_off IS NOT NULL` (`day_off_since_set`). The DB allows any mask; the domain limits it to 1 day.
- Data: `UPDATE notification_settings SET practice_days = NULL WHERE practice_days @> '{1,2,3,4,5,7}' AND practice_days <@ '{1,2,3,4,5,7}'`. No day off is inferred (explicit only; the question covers the rest).
- The old revision ignores the new columns and reads NULL days as Sun–Fri, so it's safe while it still serves. Downgrade drops the 4 columns (the nulling is harmless). Mask ↔ set helpers live in `db/accounts.py`.

## 8. Copy (new keys; RU «ты»; never "missed"/"skipped")
Both files, unless marked. `$d` = ISO weekday. `$dayoff`/`$first`/`$reminders` are string selectors.
- `day-off-weekday`: Monday…Sunday / понедельник…воскресенье (lowercase). `day-off-weekly`: Mondays…Sundays / по понедельникам, по вторникам, по средам, по четвергам, по пятницам, по субботам, по воскресеньям.
- `settings-day-off-line` (bot): "😌 Day off: { day-off-weekday }" / «😌 Выходной: { day-off-weekday }». `settings-day-off-none-line`: "😌 No fixed day off" / «😌 Без постоянного выходного». `settings-day-off-unset-line`: "😌 Day off: not chosen" / «😌 Выходной: не выбран». `settings-day-off-button`: "😌 Day off" / «😌 Выходной». `settings-day-off` (app, section title): "Day off" / «Выходной».
- `day-off-pick` (bot): "😌 Which day is your weekly day off?" / «😌 Какой день у тебя выходной?». `day-off-none`: "No fixed day off" / «Без постоянного выходного».
- `day-off-explain` (bot) = `settings-day-off-hint` (app): "Your day off shows as rest in your log and stats, and practice reminders skip it. { $first -> [yes] Past weeks show it too. *[no] A change applies from today; earlier weeks keep the previous day. } If a day went differently, log it as usual. With no fixed day off, reminders come every day." / «Выходной отмечается как отдых в журнале и статистике, а напоминаний о практике в этот день нет. { $first -> [yes] Прошлые недели тоже отметятся. *[no] Изменение действует с сегодняшнего дня, прошлые недели остаются как были. } Если день прошёл иначе, просто отметь его. Без постоянного выходного напоминания будут приходить каждый день.»
- `log-auto-moon` (bot) = `today-auto-moon` (app): "🌙 Moon day (📍 { $city }), a traditional rest day{ $dayoff -> [yes] {""} and your weekly day off too *[no] {""} }. If you practiced, log it below." / «🌙 Лунный день (📍 { $city }) — традиционно день отдыха{ $dayoff -> [yes] , к тому же твой выходной *[no] {""} }. Если была практика, отметь ниже.»
- `log-auto-day-off` = `today-auto-day-off`: "😌 Your weekly day off, shown as rest. If the day went differently, log it below." / «😌 Твой выходной — отмечен как отдых. Если день прошёл иначе, отметь ниже.»
- `day-off-ask`: "{ $reminders -> [on] 😌 Practice reminders don't come { day-off-weekly }. Is that your weekly day off? *[off] 😌 Is { day-off-weekday } your weekly day off? }" / «{ $reminders -> [on] 😌 Напоминания о практике не приходят { day-off-weekly }. Это твой выходной? *[off] 😌 Твой выходной — { day-off-weekday }? }». `day-off-ask-yes`: "Yes" / «Да». `day-off-ask-instead`: "{ $d -> [6] Saturday *[7] Sunday }" / «{ $d -> [6] Суббота *[7] Воскресенье }». `day-off-ask-other`: "Other…" / «Другой…». `day-off-ask-later`: "Not now" / «Не сейчас».
- `day-off-reminders-follow`: "Reminder days now follow your day off." / «Дни напоминаний теперь подстроены под выходной.» `day-off-reminders-edit`: "✏️ Reminder days" / «✏️ Дни напоминаний».
- App only: `stats-legend-auto`: "Day off or moon day (not logged)" / «Выходной или лунный день (без отметки)». `stats-cell-auto`: "{ $date }: { $kind -> [moon] 🌙 moon day (📍 { $city }) *[day_off] 😌 day off }{ $dayoff -> [yes] , also your day off *[no] {""} }, not logged" / «{ $date }: { $kind -> [moon] 🌙 лунный день (📍 { $city }) *[day_off] 😌 выходной }{ $dayoff -> [yes] , к тому же твой выходной *[no] {""} }, без отметки». `stats-day-off-link`: "😌 Set your weekly day off" / «😌 Выбрать выходной».
- Reused: `remind-day-off`, `remind-weekday`, `remind-practice-link`, `settings-link`, `settings-save-failed`, `status-*`.

## 9. Cross-cutting checks
- **Time zones:** local dates only (`isoweekday()`), no instants. `joined` and "today" come from the account zone (provisional for display). `day_off_since` = local today at the change. Moon dates of the followed city apply as the same local date (MD-03). A later zone change can move `joined` by ±1 day (accepted).
- **Privacy:** the day off isn't sensitive. Auto days are never stored or sealed, and a 🌸 log always wins. ST-06 will project a logged rest/🌸 on the day off exactly like an auto day off (ADR-0022). Logs: account uuid + field names only.
- **i18n:** en/ru parity for every key above; RU weekdays lowercase mid-line; no new plurals. Mini App chips use `remind-weekday`, never Intl.
- **Responsiveness:** day screens and stats add no statement; a set = 2 short statements, callback answered first; the question adds no read (account + settings are already loaded). Mini App: optimistic chips/presets/dismiss; initial chunk ≈ +0.4 KB copy, lazy chunks ≈ +1.2 KB, no new dependency.

## 10. Test plan
- **Domain:** `auto_days`: logged wins (practice on a moon day, 🌸 / "No practice" on the day off); moon on the day off → MOON + `also_day_off`; never chosen / ∅ / each weekday; future → none; **a new account shows no auto days before `joined`** (moon and day off); `joined` at 23:30 local vs UTC. `change_day_off`: first choice retroactive; Sat→Sun keeps old Saturdays; two changes the same day; the fold on a second later change. `check_day_off`: 2 elements, 0, 8, duplicates → `InvalidDayOff`. `reminder_days`/`defaults_for`/`effective` (NULL follows, stored overrides). `day_off_question`: default days → Sat; custom days with one gap → that day; every day / two gaps / dismissed / chosen → None; `reminders_on` follows `practice.enabled`. `summarize`: auto in rest, not in unlogged, `auto` count. `find_runs`: 3 months unlogged with auto Saturdays → the run ends; `P(Fri) auto(Sat) P(Sun)` → 2. Zones: Kiritimati vs Honolulu at the same instant; Berlin DST Sunday moon day.
- **Use case (fakes, fixed clock):** `GetDays` auto only for unlogged dates in `[joined, today]`, default city Mysuru, one repo call; `SetDayOff` sets `since` to local today, resets reminder days, `reminders_reset` true only for differing custom days; `DismissDayOffQuestion` idempotent; `GetYearStats` auto + counts; **tick: an unlogged auto day counts as not logged** (custom days including the day off still get the reminder, and `_silent` counts it as unanswered); the tick uses the day-off-derived defaults.
- **Infrastructure (real Postgres):** `range_with_moon` = one statement; mask round-trip (∅ ↔ 0, {6} ↔ 32); CHECKs (pair, range); `reset_practice_days` returns the previous value in one statement; `candidates` carries `day_off`; 0007 nulling (a Sun–Fri row reads the same before and after); upgrade → downgrade → upgrade; `alembic check`.
- **API contract:** `GET /me` `day_off` null/[]/[6]; `PUT /me/day-off` 200 + `reminder_days_reset`, 422 for `[6,7]`, `[8]`, `[6,6]`, `null`; `DELETE /me/day-off-question` 204 twice; `notification-settings.day_off_question`; `/me/days` and `/me/stats` `auto`, `unlogged`, `summary.auto`; OpenAPI regenerated and the TS client builds.
- **Bot handler:** S line for each state (RU «Выходной: суббота»); O ✓ from both origins and the back targets; `s1:o:*`/`r1:d:*`/`r1:dp`/`r1:dn` round-trip, ≤ 64 bytes, `s1:o:67`/`r1:d:9` ignored; the R question shown/hidden per rule, buttons per weekday, never in the reminder message; the follow note after a reset; the status picker auto note without ✓ (moon with 📍 city, moon + day-off clause); clear → auto note; week emoji; en/ru keys exist and format.
- **Mini App (Vitest):** Day off chips save optimistically and roll back on error; presets PUT the day off and show the follow note; Today auto hint (replaces `moon-today`); auto cell class + aria/title with the city; editor line; the stats question → Yes/Not now/Other… and the link fallback; an old stats payload without `auto` still renders; bundle check. **Manual:** the auto tone is readable next to the moon ring in light and dark themes (≥ 3:1 for the ring against the auto fill).
- **Architecture:** import-linter (domain pure, aiogram only in `bots/telegram`).

## 11. Open questions for the owner (answered 2026-10-25: yes to both)
1. ✅ The question gets a 4th button **[Not now]**: that's the "dismissed" path. Without it the question would stay on `/remind` until answered. Recommended: yes.
2. ✅ On an unlogged moon day, the Today card shows the auto-moon line *instead of* "🌕 Full moon today" (the city is shown once; the phase is still on the moon card). Recommended: yes.
