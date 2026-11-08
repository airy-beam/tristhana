# SC-02: classes (series, exceptions, moon-day policy, closures, swap days)

- Status: **accepted** (architect, 2026-11-07; ashtanga-expert review applied; owner answered Q117, Q125 and Chanting, and accepted all other questions as recommended on 2026-11-07, see §10) · Size M, Phase 3
- Requirements: **SC-02** (type: Mysore window / Led / 1:1 / Conference / Pranayama / Workshop, plus Chanting (owner); online/offline; zone; recurrence; exceptions; moon days auto-cancel per the shala policy). Builds on SC-01 (ADR-0033). Prepares SC-03 (my schedules in my zone), SC-05 (attendance keyed by occurrence), SC-06 (ICS). Touches PR-09 (Q109 day off), MD-02 (shala moon city).
- Related: ADR-0005, 0008, 0019, 0022, 0032, 0033. New: **ADR-0034** (proposed).

## 1. Scope (Q114)
Classes without a reader repeat Q96's problem, so **members see the schedule in this slice**, read-only, in the shala's zone.
**In:** shala settings: weekly day off (0–2 weekdays) and moon-day policy (`closed` / `pranayama` / `open`, Q117); class series (type, optional title, teacher, online flag, start + length, weekly rule or one-off, start/end date); per-occurrence exceptions (cancel, hold anyway, move date/time, substitute teacher); closures (date ranges); swap days; a 4-week schedule on the shala card (bot + Mini App) with "your time" where the viewer's offset differs; staff quick cancel/restore in the bot; the Q109 one-tap day-off adoption.
**Moves to SC-03:** one combined "my schedule" across all my shalas (and solo teachers, Q115), a Home entry, the DST "⚠ time shift this week" chip, filters. **SC-05:** attendance, the "practises here" flag (Q107, Q120). **SC-06:** ICS feed (uses `to_rrule` and the same expansion). **Later:** bookings and capacity (SC-04), notifications about cancellations (NT-03, Q122), meeting links (Q123), led-class series content (e.g. "Primary + Intermediate"), a Mysore "last start time" option (expert nit), public schedules for non-members.
**Unchanged:** no practice data through a shala; the log, auto-rest and reminders are untouched (a class is never a log entry).

## 2. Flows and copy
**Shala settings (Mini App, owner/manager).** The shala edit form gains "😌 Day off" (weekday chips, max 2, Sat/Sun first as PR-09) and "🌙 On moon days" (`<select>`: closed · pranayama, chanting and talks only · classes as usual), with the note `shala-moon-policy-note` under it. Closures ("🏖 Shala closed", start–end dates) and swap days ("🔁 Hold the moon-day classes of {date} on {date}") are rows with ➕ and 🗑.

**Swap days (Q125, owner).** An explicit, manual staff action, never suggested by the app. Date B is within ±6 days of date A. Only the occurrences of A that were **cancelled automatically** (moon or closure) move to B at the same wall clock; classes held on A stay on A. B must be the shala's day off, or a date with no class of the same type; B may not be a moon day of the shala calendar or inside a closure. Otherwise `invalid_class`, checked at creation.

**Add / edit a class (Mini App, Q103, `can_manage_schedule`).** Form: type (7 chips), title (optional, ≤ 48, plain), teacher (`<select>` of staff with teacher/assistant role, or "—"), start (`<input type=time>`, labelled with the zone, e.g. `Almaty (UTC+5)`), length (Mysore: "until" time, giving a window `06:00–09:30`; others: minutes 15–480), days (weekday chips; preset for Mysore = all but the shala's day off, other types start with no day ticked; Led shows the hint `class-led-hint` "Often Friday or Sunday"; none = one date only), "every 1/2/3/4 weeks", from (date, default today), until (optional), 🌐 online, and for online only "Times in" (listed city, default the shala's city, Q124). A warning line if a chosen day is the shala's day off (allowed: e.g. a Sunday conference). Editing offers "Applies: all dates · from {date}" (from = end the old series the day before and start a new one; one statement). Delete = hard, native confirm; "End" sets `until`.

**Occurrence sheet (Mini App, staff; tap a schedule row).** `[❌ Cancel this class]` · `[✅ Hold anyway]` (only on an auto-cancelled one: moon or closure) · `[↪ Move]` (date ±7 days and/or time, length) · `[👤 Substitute]` · `[↩ Restore]` (deletes the exception).

**Schedule (both surfaces, any member; bot `c1:w:<shala>:<week>` from `[🗓 Schedule]` on the shala card, weeks 0–3):**
```
🗓 Ashtanga Almaty: schedule, 9–15 Nov
Times: Almaty (UTC+5)
Mon 9 Nov
  06:00–09:30 Mysore · Anna
  18:30–20:00 Led Primary · Boris 🌐 (16:30 your time)
Fri 13 Nov 🌙 Moon day
  🔁 06:00 Mysore: moved to Sat 14 Nov (moon day)
  07:00–08:00 Pranayama · Anna
Sat 14 Nov 😌 Shala day off · 🔁 Instead of Fri 13 Nov
  06:00–09:30 Mysore · Dana (substitute)
Sun 15 Nov
[◀] [▶]   [❌ Cancel a class…]  (staff: occurrences of the next 48 h)   [⬅ Back]
```
Zone label once in the header (`07:00 Almaty (UTC+5)` rule); a day whose offset differs from the header's (DST week) repeats the label on its day row. "your time" appears only when the viewer's offset on that date differs (online classes in practice). 1:1 rows are shown to staff only (Q121). Cancelled occurrences stay visible with a reason. Plain text, no `parse_mode` (titles are user text).

**Bot staff quick action.** `[❌ Cancel a class…]` lists the next 48 h's occurrences as buttons → `c1:o` card → `c1:x` confirm → edits back into the schedule; `[↩ Restore]` / `[✅ Hold anyway]` on a cancelled one. Silent: no one gets a message (Q122).

**Day off adoption (Q109, Q119).** On the shala card, for a member whose own day off is never chosen and whose shala has one: `😌 Day off: Saturday` and `[😌 Make Saturday my day off too]` (`c1:d:<shala>`, Mini App: same button) → the existing PR-09 `SetDayOff` use case (first choice applies to all history). No silent inheritance.

**Copy** (⚑ drafts; «ты»; RU gender-neutral; reuse `context-mysore/led/private`; ashtanga-expert + ux-writer pass):

| Key | EN | RU |
|---|---|---|
| `class-type` | `{ $type -> [conference] Conference [pranayama] Pranayama [chanting] Chanting *[workshop] Workshop }` (others via `context-*`) | Конференция / Пранаяма / Чантинг / Семинар |
| `class-led-hint` | Often Friday or Sunday | Часто в пятницу или воскресенье |
| `schedule-title` | 🗓 { $shala }: schedule, { $range } | 🗓 { $shala }: расписание, { $range } |
| `schedule-zone` | Times: { $zone } | Время: { $zone } |
| `schedule-your-time` | ({ $time } your time) | ({ $time } по твоему времени) |
| `schedule-moon-day` | 🌙 Moon day | 🌙 Лунный день |
| `schedule-reason` | `{ $reason -> [moon] moon day [closure] shala closed *[cancelled] cancelled }` | лунный день / шала закрыта / отменено |
| `schedule-swap` | 🔁 Instead of { $day } | 🔁 Вместо { $day } |
| `schedule-swapped-to` | 🔁 { $class }: moved to { $day } ({ $reason }) | 🔁 { $class }: перенесено на { $day } ({ $reason }) |
| `schedule-moved` | ↪ moved from { $day } { $time } | ↪ перенесено с { $day } { $time } |
| `schedule-substitute` | { $name } (substitute) | { $name } (замена) |
| `schedule-day-off` | 😌 Shala day off | 😌 Выходной в шале |
| `schedule-empty` | No classes these days. | В эти дни занятий нет. |
| `shala-moon-policy` | `{ $p -> [pranayama] 🌙 Moon days: pranayama, chanting and talks only [open] 🌙 Moon days: classes as usual *[closed] 🌙 Moon days: the shala is closed }` | 🌙 В лунные дни только пранаяма, чантинг и конференции / 🌙 В лунные дни занятия как обычно / 🌙 В лунные дни шала закрыта |
| `shala-moon-policy-note` | Dates follow the shala's moon city (lunar day at sunrise). If your shala observes another day, use Hold anyway or Cancel. | Даты считаются по лунному городу шалы (лунный день на восходе). Если в шале отмечают другой день, используй «Всё равно провести» или «Отменить». |
| `shala-day-off-line` | 😌 Day off: { $days } | 😌 Выходной: { $days } |
| `shala-day-off-adopt` | 😌 Make { $days } my day off too | 😌 Мой выходной тоже: { $days } |
| `class-cancel-ask` | Cancel { $class } on { $day }? It shows on the schedule. No one gets a message. | Отменить { $class } { $day }? Отмена будет видна в расписании. Сообщений никто не получит. |

Plus buttons and states: `schedule-open`, `class-cancel`, `class-restore`, `class-hold`, `class-cancel-pick`, `class-gone` (stale button), `class-caps`, `class-invalid`; Mini App `class-form-*` (type, title, teacher, start, until, length, days, every, from, end, online, zone, applies), `closure-*`, `swap-*`, `occurrence-*`. Reused: `page-prev/next`, `log-back`, day-off weekday names.

## 3. Domain, use cases, ports
`domain/classes.py` (pure; `zoneinfo` only, **no dateutil**, ADR-0034):
```python
class ClassType(StrEnum): MYSORE; LED; PRIVATE; CONFERENCE; PRANAYAMA; CHANTING; WORKSHOP   # PRIVATE = "1:1"
class MoonPolicy(StrEnum): CLOSED = "closed"; PRANAYAMA = "pranayama"; OPEN = "open"
HELD_ON_MOON = {CLOSED: ∅, PRANAYAMA: {PRANAYAMA, CONFERENCE, CHANTING}, OPEN: set(ClassType)}  # Q117 (owner)
# Led is asana practice, so it stops on moon days too. OPEN: nothing auto-cancelled, 🌙 still shown.
MAX_CLASSES = 40; MAX_FUTURE_CLOSURES = 20; MAX_FUTURE_SWAPS = 20; WINDOW_MAX = 31; HORIZON = 365
MOVE_MAX = SWAP_MAX = 6   # days; CLOSURE_MAX = 92 days
@dataclass ClassSeries: id, type, title, online, zone, teacher_id, start: time, minutes: int,
                        weekdays: Weekdays (∅ = one-off on starts_on), every: 1..4 (weeks), starts_on, ends_on | None
@dataclass Override: on_date, status: CANCELLED | HELD | None, moved_to, start, minutes, teacher_id
@dataclass Occurrence: class_id, key: date (the rule's date), on: date, start/end: time (wall clock),
                       starts_at: datetime (UTC), type, title, online, teacher_id, substitute: bool,
                       cancelled: Reason | None (MOON | CLOSURE | CANCELLED), moved: bool, swapped_from: date | None
def check_series(...) -> ClassSeries          # InvalidClass: end past 24:00, weekdays ∉ ISO, until < from …
def rule_dates(s, start, end) -> Iterator[date]   # `every` counted in ISO weeks from starts_on's week (WKST=MO)
def check_swap(a, b, today, days_off, moon, closures, types_on: Mapping[date, set[ClassType]]) -> None
    # InvalidClass unless 0 < |b−a| ≤ 6, b ∈ [today, today+365], b not a moon date, b in no closure, and
    # b is a shala day off or has no class of a type that would move from a (Q125)
def expand(series, overrides, closures, swaps, moon: Set[date], policy, start, end, staff_only: bool) -> list[Occurrence]
def wall_to_utc(day, t, zone) -> datetime     # nonexistent (spring gap) → shifted forward by the gap; ambiguous → fold=0
def to_rrule(s) -> str | None                 # "FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,WE;UNTIL=…" for SC-06 and the API
```
**Expansion order (per occurrence; precedence: staff override > closure > moon):** rule dates in `[start−7, end+7]` → override (move, time, substitute; `CANCELLED` → cancelled) → on the resulting date: in a closure → `CLOSURE`; a moon date of the shala calendar and the type ∉ `HELD_ON_MOON[policy]` → `MOON`; `HELD` cancels both auto reasons → **swap** (Q125): an occurrence **auto-cancelled** (moon or closure, not by hand, not held) on a swap's `from_date` moves to its `to_date` at the same wall clock, uncancelled, with `swapped_from`; held classes stay on A; B is re-checked at read time only as a safety net (a closure added later cancels it again) → keep only `on ∈ [start, end]`, sort by `starts_at`. Under `open` no occurrence is auto-cancelled for the moon, so a swap moves nothing (the day still carries 🌙). **Moon dates** are the stored `moon_day` rows of `coalesce(moon_city, city)` (Q111 fallback to the city when removed), compared as calendar dates with the class's local date (as MD-02 applies a followed calendar). The stored date is already the observed one, kshaya included: no recomputation, no shifting. The weekly day off never cancels a class by itself; it drives the form preset, the card line and Q119.

**Policies (`application/policies.py`, on the `Membership` read in the same statement):** `can_view_schedule` any member · `can_view_private_classes` staff · `can_manage_schedule` owner, or roles ∩ {admin, teacher, office} (Q118) · `can_edit_shala` (existing) for day off and moon policy. Non-members → `NotFound`; members without the right → `NotAllowed`.

**Use cases (`application/classes.py`, both adapters unless noted):** `GetSchedule(principal, shala, from, days)` (one read + `expand`), `ListClasses`, `CreateClass`, `UpdateClass(…, from_date?)`, `DeleteClass`, `SetOverride` / `ClearOverride`, `AddClosure` / `RemoveClosure`, `AddSwap` / `RemoveSwap`; `UpdateShala` gains `days_off`, `moon_policy`; bot also: `AdoptShalaDayOff` (calls PR-09's `SetDayOff` only if never chosen). "Today" for bounds is the **shala's** local date (`domain.days.local_today`).

**Port `ScheduleRepository` (`Storage.schedule`), one statement each:** `window(shala, me, start, end)` → membership + shala (zone city, moon city, policy, days off) + series active in the window + overrides with `on_date ∈ [start−7, end+7]` + closures and swaps overlapping + `moon_day` dates + staff names, as jsonb aggregates (None = not a member); guarded writes (`Guarded[T]`, SC-01 pattern) `create`, `update` (split with `from` moves overrides ≥ from to the new id and deletes overrides the new rule no longer produces), `delete`, `set_override`, `clear_override`, `add_closure`, `remove_closure`, `add_swap`, `remove_swap`, each with the cap check in the CTE.

## 4. API (initData; `{code}` errors; `no-store`; `gen:api`)
| Method, path | Request → Response | Policy |
|---|---|---|
| `GET /api/v1/shalas/{id}/schedule` | `?from=YYYY-MM-DD&days=1..31` (from ∈ [today−7, today+365], shala-local) → `{zone, city, moon_policy, days_off, days: [{date, moon, day_off, swap_from}], occurrences: [{class_id, key, on, start, end, starts_at, type, title, online, teacher: {id, name}\|null, substitute, cancelled: "moon"\|"closure"\|"cancelled"\|null, moved, swapped_from}]}` | `can_view_schedule`; 1:1 rows only for staff |
| `GET /api/v1/shalas/{id}/classes` | → `[ClassOut {id, type, title, online, city, teacher_id, start, minutes, weekdays, every, starts_on, ends_on, rrule}]` | `can_manage_schedule` |
| `POST /api/v1/shalas/{id}/classes` | `ClassIn` (ClassOut without id/rrule) → 201 `ClassOut`; 409 `class_caps`; 422 `invalid_class` | `can_manage_schedule` |
| `PATCH …/classes/{class_id}` | `ClassIn` partial + `from?` → `ClassOut` (new id after a split) | same |
| `DELETE …/classes/{class_id}` | → 204, idempotent | same |
| `PUT …/classes/{class_id}/occurrences/{key}` | `{status?: "cancelled"\|"held"\|null, on?, start?, minutes?, teacher_id?}` → `Occurrence`; 422 `invalid_class` | same |
| `DELETE …/classes/{class_id}/occurrences/{key}` | → 204 (restore) | same |
| `POST /api/v1/shalas/{id}/closures` · `DELETE …/closures/{closure_id}` | `{start, end}` → 201 `{id, start, end}`; 409 `class_caps` | same |
| `POST /api/v1/shalas/{id}/swaps` · `DELETE …/swaps/{from}` | `{from, to}` → 201; 422 `invalid_class` (`check_swap`, with the moon dates, closures and classes read in the same statement); 409 `class_caps` | same |
| `PATCH /api/v1/shalas/{id}` | += `days_off: int[] \| null`, `moon_policy` | `can_edit_shala` |
| `GET /api/v1/shalas/{id}` | `ShalaOut` += `days_off`, `moon_policy`, `me.schedule: bool` (server-computed `can_manage_schedule`) | member |

Times are `"HH:MM"` wall clock in the class zone; `starts_at` is the UTC instant (the client formats "your time" with `Intl`). `ErrorCode` += `class_caps`, `invalid_class`.

## 5. Bot (prefix **`c1:`**, free; base64url uuids as SC-01; dates `yyyymmdd`; answer first, edit in place)
| Data | Meaning |
|---|---|
| `c1:w:<shala>:<week>` | schedule, week 0–3 from the shala's today |
| `c1:p:<shala>` | staff: pick an occurrence of the next 48 h |
| `c1:o:<shala>:<class>:<date>` · `c1:x:…` · `c1:r:…` · `c1:h:…` | occurrence card · cancel (after the ask) · restore · hold anyway |
| `c1:d:<shala>` | make the shala's day off mine (Q119) |

Longest: `c1:x:` + 22 + `:` + 22 + `:` + 8 = 59 bytes (≤ 64). Policy re-checked on every tap; a stale button re-renders (`class-gone`). The shala card gains `[🗓 Schedule]` and the day-off line; `/teachers` is unchanged.

## 6. Migration `0022_classes` (expand-only, down `0021`)
- `shala` += `days_off smallint NULL CHECK 0–127` (ISO bitmask as `account.day_off`; NULL = not set; ≤ 2 days is a domain rule), `moon_policy text NOT NULL DEFAULT 'closed' CHECK IN ('closed','pranayama','open')`.
- `shala_class(id uuid PK default gen_random_uuid(), shala_id → shala CASCADE, type text CHECK IN ('mysore','led','private','conference','pranayama','chanting','workshop'), title text NULL CHECK 1–48, online bool NOT NULL DEFAULT false, city text NULL CHECK slug AND (city IS NULL OR online), teacher_id uuid NULL, start_time time NOT NULL, minutes smallint NOT NULL CHECK 15–480 AND start + minutes ≤ 24:00, weekdays smallint NOT NULL CHECK 0–127, every smallint NOT NULL DEFAULT 1 CHECK 1–4, starts_on date NOT NULL, ends_on date NULL CHECK ≥ starts_on AND (weekdays > 0 OR ends_on IS NULL), created_at, updated_at)`; FK `(shala_id, teacher_id) → shala_staff (shala_id, account_id) ON DELETE SET NULL (teacher_id)` (PG ≥ 15 column-list form; checked 2026-11-07: local and Supabase both run Postgres 17. Fallback, unused: `teacher_id → account ON DELETE SET NULL` plus a staff check in the write CTE and `RemoveStaff` nulling it in the same statement. Either way a removed or deleted teacher leaves the class untaught, never a dangling id); index `(shala_id, starts_on)`.
- `shala_class_override(class_id → shala_class CASCADE, on_date date, shala_id uuid NOT NULL, status text NULL CHECK IN ('cancelled','held'), moved_to date NULL CHECK |moved_to − on_date| ≤ 6, start_time time NULL, minutes smallint NULL, teacher_id uuid NULL, updated_at)`, PK `(class_id, on_date)`, same composite teacher FK with SET NULL, CHECK `status <> 'cancelled' OR all change fields NULL`, index `(shala_id, on_date)`.
- `shala_closure(id uuid PK, shala_id → shala CASCADE, start_date, end_date CHECK end ≥ start AND end − start ≤ 91)`, index `(shala_id, end_date)`.
- `shala_swap(shala_id → shala CASCADE, from_date, to_date, PK (shala_id, from_date), UNIQUE (shala_id, to_date), CHECK from ≠ to AND |to − from| ≤ 6)`.
- FK names via `op.f()`; no account FK, so `is_account_gone` is unchanged; no backfill. Past overrides/closures/swaps are kept (SC-05 history); tiny.

## 7. Cross-cutting checks
- **Time zones.** Series are wall clock + the class zone (shala city's IANA zone; an online class may name another listed city, Q124), never an offset. Instants are derived at read time (`wall_to_utc`): DST keeps 06:30 local; a start inside a spring gap shifts forward by the gap; an ambiguous one takes the first. Labels are computed per date (`07:00 Berlin (UTC+1)` → `(UTC+2)` across the change); the header names the zone, a day with a different offset repeats it. "Your time" uses the viewer's zone and home-city label (ADR-0029), per date, only when the offset differs. "Today", the 48 h list and window bounds use the shala's local date. Moon dates are calendar dates of the shala's moon city applied to the class's local date (a Mysuru-following shala in Los Angeles cancels on the Mysuru date). Half-hour zones (Goa, Mysuru) are covered by the existing label helper.
- **Privacy.** Only shala data and staff names (already visible to members, Q106) cross accounts; no student appears anywhere in a class. 1:1 classes are staff-only (their titles may name a person). Titles are plain text, no `parse_mode`, never logged. Export: no change (classes belong to the shala, not to a person); account delete cascades through `shala_staff` → teacher set NULL. No log data read: `application.classes` imports no day/practice/progression port (import-linter contract).
- **i18n.** All strings in `bot.ftl` / `app.ftl`, en + ru parity; weekday and date formats from the existing helpers; class types via one select key + `context-*`; names nominative only; RU gender-neutral («отменено», «замена»).
- **Abuse / caps (Q127).** 40 live series per shala, 20 future closures, 20 future swaps; overrides only for dates in [today, today+365]; window ≤ 31 days. Soft caps as SC-01.
- **Responsiveness.** Read-time expansion (ADR-0034): ≤ 40 series × 45 days is < 1 ms CPU; no dateutil import anywhere.

| Tap / request | Statements | Note |
|---|---|---|
| Shala card (+ day-off line) | unchanged (2) | `days_off`, `moon_policy` in the card row |
| Schedule week (bot or API) | 2 (account + `window`) | indexed: `(shala_id, starts_on)`, `(shala_id, on_date)`, `moon_day` PK range |
| Cancel / restore / hold (bot) | 3 (account + guarded write + the week's window) | edit in place; built 2026-11-08 |
| `PUT …/occurrences/{key}` | 3 (account + write + window for the answer) | built |
| `POST …/swaps` | 3 (account + window for `check_swap` + write) | built |
| `PATCH …/classes/{id}` | 3 (account + class list for the merge + write) | built |
| Other Mini App writes | 2 | then a cached `schedule` invalidation |

Measure with 40 series, 20 overrides, a 31-day window, before calling it done. Mini App: schedule and forms in one lazy chunk; initial JS budget unchanged; RU at 320 px (day rows wrap, buttons stack).

## 8. Test plan
- **Domain (`classes.py`, table-driven):** `rule_dates` for weekly, every 2/3/4 weeks (ISO week anchor, starts_on mid-week), one-off, until bound, empty window; `check_series` bounds (end exactly 24:00 ok, 24:01 rejected, until < from, one-off with until); **DST**: Berlin 06:30 Mysore across 29 Mar 2026 and 25 Oct 2026 (local stays 06:30, UTC moves 05:30→04:30), London and New York ditto, a 02:30 class on the spring-gap date → 03:30, a 02:30 class on the fall-back date → first instant, a class created in winter viewed for summer; Goa/Mysuru +5:30 labels; "your time" for an Almaty viewer of a Berlin online class, before and after the Berlin change (offset 4 h → 3 h); **moon**: each policy × each of the 7 types on a moon date (`closed` cancels all, `pranayama` keeps pranayama, conference and chanting, Led cancelled under both; `open` cancels nothing but the day still has `moon`); a kshaya date cancels exactly the stored date, not the next; a moon date on the shala's day off cancels nothing extra; a removed moon city falls back to the city (Q111); **swap** (expand): a moon Friday's Mysore moves to the Saturday day off with the same wall clock and `swapped_from` set, while the Friday pranayama (held under `pranayama`) stays on Friday; a class cancelled by hand or held on A doesn't move; under `open` nothing moves; a closure added after the swap cancels it on B; **swap** (`check_swap`, validation): B a moon day → `invalid_class`, B inside a closure → `invalid_class`, B neither day off nor free of the moving types → `invalid_class`, |B−A| = 0 or 7 → `invalid_class`, ±6 ok, a Monday moon day with a Sunday day off ok; **overrides**: cancel, held beats moon and closure, move ±6 days into and out of the window (the ±7 read margin), substitute, an override on a date the rule no longer produces is ignored; closures cover inclusive ends; 1:1 hidden when `staff_only` is False; sorting by `starts_at`; `to_rrule` strings.
- **Policies:** role × action matrix for `can_view_schedule`, `can_manage_schedule`, `can_view_private_classes` (owner, admin, teacher, assistant, office, student, non-member).
- **Use case, fakes:** bounds use the shala's local today, not the viewer's (a Los Angeles shala viewed from Bali near midnight); split with `from` keeps earlier dates and moves later overrides; caps raise; `AdoptShalaDayOff` writes only when never chosen and goes through `SetDayOff`; non-member `NotFound`, assistant `NotAllowed`.
- **DB (real Postgres):** every CHECK; composite FK SET NULL on staff removal and teacher account delete; shala delete cascades; `window` returns identical rows to the fakes for a seeded mix; statement counts per §7; `EXPLAIN` on 40 series; 0022 up/down/up; `alembic check`; app role grants.
- **API:** 401; exact key sets; non-member 404 = unknown id 404; assistant write 403 `not_allowed`; 1:1 absent for students; `from` outside bounds 422; `days` > 31 422; `rrule` in `ClassOut`; OpenAPI → TS client builds.
- **Bot, through the webhook:** schedule both locales, a DST week shows the repeated label, ≤ 4096 chars with 40 series and 64-char shala names; week paging; staff-only buttons; cancel ask → cancel → edit in place; restore and hold; stale/forged ids re-render; every callback ≤ 64 bytes; `answered` first; `c1:d` only for never-chose members with a shala day off.
- **Mini App (Vitest, also `TZ=UTC`):** class form validation (window vs minutes, days preset from the day off for Mysore only, empty for other types, Led hint, online zone select), moon policy select with its note, applies-from flow, occurrence sheet actions per role, zone and "your time" labels, RU at 320 px, `check:bundle`.
- **i18n/architecture:** ftl parity; RU avoid-word greps; import-linter (domain pure, no `dateutil`, aiogram only in `bots/telegram`, `application.classes` reads no log ports).
- **Owner on a phone:** create a Mysore Mon–Fri series and a Friday led class, see the next moon day cancelled on a student account, add a swap to the day off, cancel tomorrow's class from the bot.

## 9. Open questions for the owner (each with a recommendation)
- **Q114 Scope.** Recommend §1: classes + day off + moon policy + exceptions + closures + swaps, and members see a read-only 4-week schedule of each shala (both surfaces). SC-03 adds the combined "my schedule", Home entry and DST chip.
- **Q115 Whose classes.** Recommend classes belong to a shala only; a solo or online teacher creates a one-person shala (SC-01 allows it). Personal teacher schedules without a shala wait for SC-03 feedback.
- **Q116 Recurrence.** Recommend the weekly subset (weekdays, every 1–4 weeks, from/until) or a single date, stored as columns and expanded in the domain; `to_rrule` gives the RRULE text for ICS. No monthly rules, no `dateutil` (ADR-0034).
- **Q117 Moon policy meaning.** Answered by the owner, see §10.
- **Q118 Who manages classes.** Recommend owner, manager, teacher and front desk manage classes, exceptions, closures and swaps; day off and moon policy stay with owner/manager; assistants and students view.
- **Q119 = Q109 Day-off inheritance.** Recommend no silent inheritance: a never-chose member gets a one-tap "Make Saturday my day off too" on the shala card (PR-09 rules apply). Silent inheritance would recolour history and move reminder days without a tap.
- **Q120 = Q107 "Practises here".** Recommend keeping it deferred to SC-05 (attendance is its only reader).
- **Q121 1:1 visibility.** Recommend 1:1 classes are visible to staff only, with no student attached (booking is SC-04).
- **Q122 Cancellation notices.** Recommend none in SC-02 (shown on the schedule only); a silent push on a same-day cancel is a small follow-up with NT-03.
- **Q123 Meeting links.** Recommend not storing Zoom/meeting links in SC-02 (phishing and leakage risk; shalas share them in their own chats).
- **Q124 Online class zone.** Recommend the shala's zone by default; an online class may pick another listed city's zone; offline classes always use the shala's.
- **Q125 Swap days.** Answered by the owner, see §10.
- **Q126 Hold anyway.** Recommend staff can keep an auto-cancelled occurrence (moon or closure), e.g. when the shala observes the moon day a day off from the computed one.
- **Q127 Caps and horizon.** Recommend 40 live series, 20 future closures, 20 future swaps per shala; schedule from 7 days back to 365 ahead; window ≤ 31 days.
- **Q128 Words.** Recommend EN Conference / Pranayama / Workshop, RU «Конференция» / «Пранаяма» / «Семинар»; «замена» for a substitute; "Shala day off" / «Выходной в шале». (Chanting / «Чантинг» is decided, §10.)

## 10. Decisions (2026-11-07)
- **Q117 Moon policy (owner).** `closed` (default) / `pranayama` / `open`. `led` is dropped: a Led class is asana practice, so it stops on moon days too. `HELD_ON_MOON = {CLOSED: ∅, PRANAYAMA: {PRANAYAMA, CONFERENCE, CHANTING}, OPEN: all}`. Under `open` nothing is auto-cancelled; the 🌙 marker still shows and staff cancel by hand. Copy: "🌙 Moon days: classes as usual" / «🌙 В лунные дни занятия как обычно».
- **Chanting (owner).** A seventh class type, `chanting`: EN "Chanting", RU «Чантинг» (chosen over «Мантры»). Held under the `pranayama` policy.
- **Q125 Swap days (owner).** An explicit, manual staff action within ±6 days, never suggested. Only the occurrences of A cancelled automatically (moon or closure) move; classes held on A stay. B must be the shala's day off or have no class of the same type, and may not be a moon day or inside a closure; otherwise `invalid_class` at creation.
- **ashtanga-expert should-fixes (applied).** Days preset "all but the day off" for Mysore only, other types start empty; Led hint "Often Friday or Sunday" / «Часто в пятницу или воскресенье»; RU `shala-day-off-adopt` «😌 Мой выходной тоже: { $days }»; `shala-moon-policy-note` under the moon policy picker. Nit for later: a Mysore "last start time" option (§1 Later).
- **Q114–Q116, Q118–Q124, Q126–Q128 (owner, 2026-11-07):** accepted as recommended in §9.

## 11. Build notes (2026-11-08)
- **Measured** on local Postgres 17: one 31-day read of 40 daily series with 20 overrides (1,240 occurrences) is 15.4 ms p50, 16.9 ms p95, read plus expansion.
- **Deviations from the text above**, all reviewed: the longest callback is 59 bytes (the §5 sum was off by one); the read margin is ±13 days (a move of 6 and then a swap of 6); writes accept dates from the caller's yesterday (staff a date ahead of the shala); a `from` on or before the series start, or on a one-off, edits all dates and keeps the start; Hold anyway keeps an existing move, time and substitute; `ScheduleOut` also lists the closures in the window (the Mini App removes them from there); the class tables are export-excluded on purpose, like `shala`; times and days on both surfaces are shown in the shala's zone, from the instant (an online class elsewhere can fall on another day); the bot week stops at about 3,800 characters with "…".
- **Mini App, deferred:** editing a class (the "Applies: all dates · from" form) and ending a series. Delete (all dates, native confirm) is built. The API supports the edit (`PATCH` with `from`).
