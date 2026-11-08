# SC-03: my schedule (all my shalas, in my zone, with labels)

- Status: **accepted** (architect, 2026-11-08; ashtanga-expert review applied; owner accepted Q134–Q144 as recommended and the expert's review on 2026-11-08, see §10) · Size M, Phase 3
- Requirements: **SC-03** ("students see their teachers'/shalas' schedules in their own zone, with labels", see `06 Time Zones`). Builds on SC-01 (ADR-0033), SC-02 (ADR-0034), ID-04 (ADR-0030), ID-06/MD-04 (ADR-0021, ADR-0029), MD-02 (ADR-0032). Prepares SC-05 (attendance from a row) and SC-06 (a personal ICS feed from the same read).
- Related: ADR-0005, 0008, 0029, 0030, 0032, 0033, 0034. New: **ADR-0035** (accepted).

## 1. Scope
**In:** one combined, read-only **"🗓 My schedule"** across every shala where I am a member (student or staff, ≤ 15 by the SC-01 caps), shown in **my zone** with the class's own time as a second label when the offsets differ; weeks 0–3 from my today; the DST **"⚠ time shift"** line; **my own moon day on the day row** (owner, from my effective moon calendar, MD-02); filters **All · My teachers · I teach** (both surfaces) and **shala chips** (Mini App); a Home row for anyone with a shala; bot `/schedule`. **"My classes" folds into it** (Q137): `/classes` and the Home row open My schedule with the *I teach* filter, and `GetMyClasses` / `staff_windows` go away.
**Teachers (Q135):** a followed teacher's classes appear only from shalas **I am a member of**; rows they teach or cover get a "your teacher" mark and the *My teachers* filter. A followed teacher's shala I have not joined shows nothing (schedules stay member-only, Q106, SC-02 §1).
**Out → SC-04:** "I'm coming", capacity. **SC-05:** "I was there" from a row, attendance. **SC-06:** a personal ICS feed of this view (reuses `GetMySchedule`). **NT-03 / later:** cancellation pushes (Q122), "class in 1 h" reminders, a "next class" card on Home, a class-type filter, public schedules or "visible to my linked students" (Q135), personal schedules of teachers without a shala (Q115 stays), shala 🌙 / day-off day markers and "moved to" day lines in the combined view (Q142), any prompt about my moon day.
**Unchanged:** the per-shala schedule (`c1:w`, `GET /shalas/{id}/schedule`), staff actions, all writes, the log (a class is never a log entry), the moon rule itself.

## 2. Flows and screens
**Who sees it.** Any account with ≥ 1 membership: Home row "🗓 My schedule" (replaces "🧑‍🏫 My classes"); bot `/schedule` (+ `/help`, command menu ☁️ `set_webhook.py` after deploy); `/classes` = `/schedule` with *I teach*. No membership: the bot answers `my-schedule-none` (ask a shala for its link); no Home row.

**Bot (plain text, no `parse_mode`; answer first, edit in place):**
```
🗓 My schedule, 9–15 Nov
Times: Almaty (UTC+5)
⚠ From Sunday, 15 November, Yoga Berlin is 1 h later for you
Mon 9 Nov
  06:00–09:30 Mysore · Anna 👤 · Ashtanga Almaty
  21:30–23:00 Led Primary · Boris 🌐 · Yoga Berlin · 17:30 Berlin (UTC+1)
Fri 13 Nov 🌙
  🌙 06:00–09:30 Mysore · Anna 👤 · Ashtanga Almaty (moon day) · 🔁 Sat 14 Nov
  07:00–08:00 Pranayama · Anna 👤 · Ashtanga Almaty · 🌙
Sat 14 Nov
  06:00–09:30 Mysore · Dana (for Anna) 👤 · Ashtanga Almaty · 🔁 instead of Fri 13 Nov
Sun 15 Nov ⚠
  ❌ 08:00–09:30 Led Primary · Boris · Yoga Berlin · 16:00 Berlin (UTC+1) (cancelled)
[All ✓] [👤 My teachers] [🧑‍🏫 I teach]
[◀] [▶]
[Ashtanga Almaty] [Yoga Berlin]          (→ c1:w:<shala>:0, the SC-02 week; 2 per row)
```
- **Primary time = my zone** (header label once, `schedule-zone` with my home-city label, ADR-0029); a day whose own offset differs repeats it on the day row (my DST change; SC-02 rule). Rows sit under **my** local date of the instant.
- **Second label** `· 17:30 Berlin (UTC+1)` = the class's wall clock with its zone label (the shala's city, or the online class's city, Q124), on **any** row whose class offset differs from mine at that instant, offline included (Q136).
- **Shala name** on a row only when rows of ≥ 2 shalas are in the week. 1:1 rows only from shalas where I am staff (Q121, per-window policy).
- **My moon day (owner, expert item 2):** a day that is a moon day of **my own effective moon calendar** (my city, or one inherited from my main teacher or shala, MD-02) shows ` 🌙` after the date on the day row (`my-schedule-my-moon`, a11y "your moon day"). Read-only, no prompt, no text about practice. It is independent of the shalas' moon days (they can differ by a day; each row says what its shala does).
- **Row marks (expert items 1, 3, 4):** cancelled by the shala's moon policy → leading **🌙** with `(moon day)`; closure or manual cancel → leading **❌** with its reason. A row **held on its shala's own moon day** (policy `open`, or a "hold anyway" override, or a `pranayama`-policy class held) ends with a quiet ` · 🌙`. A cancelled row whose class **moved by a swap** shows the target inline: `(moon day) · 🔁 Sat 14 Nov` (the cancelled occurrence on A is kept for display; the swapped one on B carries `🔁 instead of Fri 13 Nov`). A moved row (override) keeps `schedule-moved`.
- **Teachers (expert item 5):** 👤 = the date's teacher is one of my linked teachers. A **substitute covering my linked teacher** reads `Dana (for Anna)` (`schedule-covering-for`; same shape as `my-classes-covering`, reused where the words fit), and 👤 stays on the row. Staff see their own role on their rows: "you're covering for Anna" / "Boris is covering" (`my-classes-covering/covered`).
- **⚠ shift line (Q140):** for each class zone in the shown rows, *class offset − my offset* is sampled at my local noon from the day **before** the week to its last day; each change gives one line under the header (`schedule-shift`: shala or city, day, hours, earlier/later; max 3, then "…") and `⚠` on that day row. Both sides shifting together shows nothing. Row times are always exact.
- **Filters** `a` all · `t` my teachers (shown when I have links) · `m` I teach (shown when I am staff anywhere); an empty filtered week says `my-schedule-empty` with the filter named. Text budget 3,800 characters, then `…` + `my-schedule-more`.
- **Zone unknown** (Q141): times in my first shala's zone (staff first, then by name: the `member_windows` order; build decision, §11), labelled, plus `my-schedule-zone-unknown` and `[🏙 My city]` (the existing `/settings` city entry). My moon day still shows (moon dates are calendar dates of my moon city, compared with the shown dates).

**Mini App ("🗓 My schedule", one lazy chunk):** header with the zone label, ⚠ lines, filter chips (All · 👤 My teachers · 🧑‍🏫 I teach · one chip per shala when ≥ 2; client-side on the same response; last choice in `localStorage`), ◀ week ▶ (0–3), day cards with 🌙 on my moon days; a row is two lines at 320 px: `🌙 06:00–09:30 Mysore · Anna 👤` / `Ashtanga Almaty · (moon day) · 🔁 Sat 14 Nov` (hint style). Tapping a row opens that shala's SC-02 schedule on the row's week. `MyClasses.tsx` is deleted; `useOccurrenceText` generalises to (display zone, second-label zone) and gains the 🌙/❌ lead, the held-on-moon ` · 🌙` and the inline swap target, so SC-02's shala view and SC-03 share one formatter (the SC-02 view adopts items 1, 3, 4 too).

**Copy** (⚑ drafts; «ты»; RU gender-neutral; ux-writer polishes; reuse `schedule-zone`, `schedule-reason`, `schedule-moved`, `schedule-swap`, `schedule-substitute`, `my-classes-covering/covered`, `time-label`, `class-type`, `context-*`, `page-prev/next`, `day-label`):

| Key | EN | RU |
|---|---|---|
| `my-schedule-open` / `-title` | 🗓 My schedule / 🗓 My schedule, { $range } | 🗓 Моё расписание / 🗓 Моё расписание, { $range } |
| `my-schedule-filter` | `{ $f -> [teachers] 👤 My teachers [mine] 🧑‍🏫 I teach *[all] All }` | Мои учителя / 🧑‍🏫 Веду / Все |
| `my-schedule-teacher-mark` | 👤 (a11y: your teacher) | 👤 (твой учитель) |
| `my-schedule-my-moon` | 🌙 (a11y: your moon day) | 🌙 (твой лунный день) |
| `schedule-held-moon` | · 🌙 (a11y: held on the moon day) | · 🌙 (проходит в лунный день) |
| `schedule-swapped-inline` | 🔁 { $day } | 🔁 { $day } |
| `schedule-covering-for` | { $name } (for { $teacher }) | { $name } (за { $teacher }) |
| `schedule-shift` | ⚠ From { $date }, { $where } is { $hours -> [one] 1 h *[other] { $hours } h } { $dir -> [earlier] earlier *[later] later } for you | ⚠ С { $weekday -> [1] понедельника [2] вторника [3] среды [4] четверга [5] пятницы [6] субботы *[7] воскресенья }, { $date }, { $where } на { $hours } { $hours -> [one] час [few] часа *[many] часов } { $dir -> [earlier] раньше *[later] позже } по твоему времени |
| `my-schedule-empty` | `{ $f -> [teachers] No classes with your teachers this week. [mine] You teach no classes this week. *[all] No classes this week. }` | … |
| `my-schedule-none` | Your schedule shows the classes of the shalas you join. Ask your shala for its link. | Здесь будут занятия шал, в которые ты вступишь. Попроси у шалы ссылку. |
| `my-schedule-zone-unknown` | Times are in { $zone }. Set your city to see your own time. | Время указано по { $zone }. Укажи свой город, чтобы видеть своё время. |
| `my-schedule-more`, `my-schedule-load-failed`, `cmd-schedule` | … | … |

**Notes for the ux-writer (expert item 6):** the staff filter is EN "I teach", RU «Веду» (not "Mine"). RU `schedule-shift` needs the **genitive** ("с воскресенья, 15 ноября"); **`day-label` can't give it**: `DateArg` formats with Babel `MMMEd` ("вс, 15 нояб."), nominative abbreviated weekday. So `schedule-shift` takes `$weekday` (ISO 1–7, genitive chosen in Fluent as above) and `$date` as a new `DateArg` style **`long`** = Babel `d MMMM` ("15 ноября", genitive month by CLDR; EN "15 November"). Implementation: `DateArg(day, style="long")` in `ports/i18n.py` + one branch in `fluent.py::_format_date`; the Mini App uses `Intl` `{day: "numeric", month: "long"}` (also genitive in `ru`). Half-hour shifts (rare): `$hours` decimal; check RU plural for 0.5.

## 3. Domain, use cases, ports
`domain/classes.py` (pure, `zoneinfo` only) gains:
```python
@dataclass Shift: zone: str; on: date; minutes: int   # change of (class − viewer) offset; > 0: earlier for the viewer
def offset_gap(zone: str, viewer: str, day: date) -> timedelta   # at the viewer's local noon of `day`
def shifts(zones: Set[str], viewer: str, start: date, end: date) -> tuple[Shift, ...]   # day d vs d−1, d ∈ [start, end]
def local_date(o: Occurrence, zone: str) -> date                  # the date of `o.starts_at` in `zone`
```
`Occurrence` gains `moon: bool` (its final date is a moon date of its shala's calendar, whatever the policy; set in `expand`, which already checks it) so "held on the moon day" = `moon and cancelled is None`. For the inline swap target, `expand(…, keep_swapped=True)` also returns the auto-cancelled occurrence on A with `swapped_to: date` (default False keeps SC-02's output unchanged).
`application/classes.py`:
```python
class Only(StrEnum): ALL; TEACHERS; MINE
@dataclass MyRow: shala_id, occurrence, zone (class IANA), city (class city slug), role: Teaching | None, my_teacher: bool
@dataclass MySchedule: zone, zone_known, today, days: tuple[MyDay(date, my_moon: bool), ...], shalas: tuple[ShalaRef(id, name, city, zone, staff)],
                       has_teachers, is_staff, rows: tuple[MyRow, ...], shifts, staff: Mapping[UUID, Mapping[UUID, str | None]]
class GetMySchedule: execute(principal, start: date | None, days=7, skip=0, only=Only.ALL) -> MySchedule
```
Algorithm: viewer zone V = `account.timezone`, else the first shala's (`zone_known=False`); window `[start, end]` in V's dates (default V's today + `skip`); `start ∈ [today−7, today+365]`, `days ∈ 1..7` else `BadWindow`. **My moon city** = `domain.accounts.moon_follow_of(principal.account, cities).city.slug`: pure, from the already loaded account (it carries the one-hop teacher/shala inheritance, ADR-0032), so no extra read and no import of `application.moon`. One read `member_windows(me, start−2, end+2, moon_city=slug)` (±2: offsets span −12…+14); per window `_expand` over `[start−2, end+2]` (per-window `can_view_private_classes`), keep `local_date(o, V) ∈ [start, end]`, attach `role` (existing `_role`) and `my_teacher = o.teacher_id ∈ teachers` (the date's actual teacher, a substitute included; when `o.substitute and o.planned_teacher ∈ teachers` the row names "for Anna"), filter by `only`, sort by `starts_at`; `days[i].my_moon = date ∈ my_moon_dates` (calendar dates compared with my shown dates, as MD-02 applies a followed calendar); then `shifts`. No new policy: membership per window is `can_view_schedule`; `my_teacher` and my moon dates are my own data.

**Port** `ScheduleRepository.member_windows(me, start, end, staff_only=False, moon_city: str | None = None) -> MyWindows(windows: tuple[ScheduleWindow, ...], teachers: frozenset[UUID], my_moon: frozenset[date])`: `_window_stmt` filtered by `exists(staff) OR exists(student)` (or staff only), staff first then name, plus two scalar subqueries in the **same statement**: `teacher_link` ids (`student_id = me`) and `moon_day.date` for `location = moon_city` in the window (PK range). It reads only `moon_day`, never `day_log`, `rest_period`, `check_in` or anything 🌸: no import-linter exception is needed, since `application.classes` keeps importing no log, rest or women's-health port, and the moon city comes from `domain.accounts`. A test asserts that contract. Replaces `staff_windows`. Indexes exist: `shala_staff/shala_student (account_id, created_at)`, `teacher_link` PK `(student_id, …)`, `moon_day` PK `(location, date)`.

## 4. API (initData; `{code}` errors; `no-store`; `gen:api`)
| Method, path | Request → Response | Policy |
|---|---|---|
| `GET /api/v1/me/schedule` | `?from=YYYY-MM-DD` (my date; default my today) `&days=1..7` (7) `&only=all\|teachers\|mine` → `MyScheduleOut {zone, zone_known, today, moon_city, days: [{date, my_moon}], shalas: [{id, name, city, zone, staff}], has_teachers, is_staff, shifts: [{zone, city, shala_ids, on, minutes}], occurrences: [OccurrenceOut + {shala_id, zone, city, role: "teaching"\|"covering"\|"covered"\|null, my_teacher, moon, swapped_to}]}`; 422 `invalid_range` | membership per shala; 1:1 per shala staff |
| `GET /api/v1/shalas/{id}/schedule` | `OccurrenceOut` += `moon`, `swapped_to` (additive, for items 1, 3, 4 in the SC-02 view) | unchanged |
| `GET /api/v1/me/classes` | unchanged shape, **`deprecated: true`**, served by `GetMySchedule(only=MINE)` regrouped per shala in shala dates; removed one release after the Mini App stops calling it | same |

`starts_at` is the UTC instant; the client formats both labels with `Intl` (`zoneLabel`, home-city name via `placeFor`). `zone` is the zone the server used (the client never re-guesses). `only=mine` keeps its wire name; only the label changed.

## 5. Bot (callback **`c1:m:<week>:<f>`**, `week` 0–3, `f` ∈ `a|t|m`; 8 bytes)
`/schedule` → `c1:m:0:a`; `/classes` → `c1:m:0:m`. Filter and paging buttons edit in place; shala buttons reuse `c1:w:<shala>:0` (31 bytes). The week is relative to my today **at tap time** (stateless, ADR-0008). Unknown `f` or week → `nothing()`. Memberships and the moon city are re-read on every tap.

## 6. DB
**No migration.** Reads only existing tables and indexes. If the §7 measurement misses the target, the fallback is code-only (a `LATERAL` per shala), still no schema change.

## 7. Cross-cutting checks
- **Time zones ✔.** Instants from `wall_to_utc` (spring gap forward, fall-back first). Primary labels in V per date; second label in the class zone per instant; rows bucketed in V; ±2-day read margin. Half-hour and 45-minute zones through the existing helpers. Shala moon cancellations stay per shala; my 🌙 is my calendar's date on my shown date; the two may differ by a day by design. Week bounds are **my** date.
- **Privacy ✔.** Only shalas I am a member of; staff names already visible to members (Q106); 1:1 per shala staff; no student data; `my_teacher` and my moon calendar from my own account only, never shown to anyone; no shala of a followed teacher leaks (Q135; test). No log, rest or 🌸 data read (port shape + import-linter contract unchanged, no exception). Titles plain, never logged.
- **i18n ✔.** New keys in `bot.ftl` and `app.ftl`, en + ru parity; RU plurals for hours and the genitive weekday in `schedule-shift`; new `DateArg` style `long`; names nominative except the `за { $teacher }` construction (name stays nominative, accepted for user-entered names).
- **Responsiveness ✔.** Per tap: **2 statements** (account load + `member_windows`, which now carries the teacher ids and my moon dates); expansion ≤ 15 × 40 series × 11 days, a few ms; no new imports (Babel is already lazy in `_format_date`). Mini App: one request per page, filters client-side, query key under `SHALAS_KEY`, `staleTime` 60 s; lazy chunk; RU at 320 px.
- **Measure before done:** local Postgres 17, worst case 15 shalas (10 staff, 5 student) × 40 daily series × 20 overrides, a 7-day page: statement p50/p95 and expansion time (target statement p50 < 60 ms, bot tap p50 < 150 ms warm), and the realistic case (2 shalas, 10 series); `EXPLAIN`; record in §11.

## 8. Test plan
- **Domain:** `offset_gap` / `shifts`: Almaty viewer × Berlin class across 25 Oct 2026 (one shift, 1 h later) and 28 Mar 2027; New York viewer × Berlin class 14–28 Mar 2027 (two shifts); Berlin × London (none); Berlin × Mysuru (mine shifts); a shift on the window's first day; Kolkata +5:30 and Kathmandu +5:45 viewers; `local_date` Los Angeles evening → Almaty next day, Kiritimati +14 × Los Angeles. **`expand` additions:** `moon` set on a held row under `open`, under `pranayama` (Pranayama on a moon day) and on a "hold anyway"; false off moon days; `keep_swapped=True` returns A's cancelled occurrence with `swapped_to = B`, default output identical to SC-02 (regression).
- **Use case (fakes):** viewer-today bounds; `start−2…end+2` read; edge bucketing; filters `all/teachers/mine`; 1:1 only from the shala where I am staff; `my_teacher` on a substitute date names the substitute, and a substitute for my linked teacher yields "for Anna"; `zone_known=False` fallback; `BadWindow`; no memberships → empty; **privacy**: a teacher I follow who teaches only at a shala I didn't join → no row, no shala; shala moon rows keep each shala's own moon date (Mysuru-following LA shala vs an Almaty shala in one week); **my moon day**: my own city, a city inherited from my main teacher (MD-02), and a never-chose fallback each mark the right day; my 🌙 differs by a day from a shala's moon row (both shown); `moon_city` passed comes from `moon_follow_of`.
- **Architecture:** import-linter: `application.classes` imports no `ports.practice/diary/check_in/rest_periods/progression` and not `application.moon` (no exception added); domain pure; aiogram only in `bots/telegram`.
- **DB (real Postgres):** `member_windows` equals the fakes for a seeded mix (incl. `my_moon` and `teachers`); staff-only variant equals old `staff_windows`; **2 statements per tap** (statement counter); the §7 measurement.
- **API:** 401; exact key sets (new fields on both schedule answers); `only`, `from`, `days` validation 422; `/me/classes` unchanged (SC-02 snapshot) and `deprecated`; TS client builds.
- **Bot (webhook):** `/schedule`, `/classes` (= *I teach*), filters, paging, shala buttons; EN and RU; my moon day 🌙 on the day row; 🌙 lead on a moon-cancelled row, ❌ on closure and manual cancel; ` · 🌙` on a held-on-moon row; `(moon day) · 🔁 Sat 14 Nov` inline; `Dana (for Anna) 👤`; a DST week shows ⚠ and RU "С воскресенья, 15 ноября"; second label for an Almaty viewer of a Berlin class, none for same-zone rows; shala names only with ≥ 2 shalas; zone-unknown hint; 3,800-char cut; every callback ≤ 64 bytes; answered first; forged `c1:m:9:z` ignored.
- **i18n:** ftl parity; RU plurals 1/2/5 and the 7 genitive weekdays; `DateArg(style="long")` → "15 ноября" / "15 November".
- **Mini App (Vitest, also `TZ=UTC`):** Home row for a student-only member, hidden with no shala; chips; my-moon 🌙 on day cards; the same row marks in the SC-02 shala view (shared formatter); second label and ⚠; row tap-through to the shala week; RU at 320 px; `check:bundle`.
- **Owner on a phone:** a student account in two shalas (one online in Berlin) sees its week in its own zone with its moon day, a moon-cancelled Mysore with the 🔁 target, the ⚠ line in a seeded DST week, and `/classes` on a staff account.

## 9. Risks
- Worst-case read (15 shalas) heavier than SC-02's; mitigated by the measurement and the code-only fallback.
- My 🌙 and a shala's 🌙 on different days in one week may confuse; mitigated by their placement (day row = mine, row = the shala's) and the a11y labels.
- "My classes" moving from shala time to my time; the second label keeps the shala time.
- Noon sampling can mark ⚠ a day late for a 01:00 class on the change night; row times exact.
- `/me/classes` deprecation needs a one-release grace period.

## 10. Questions for the owner (answered 2026-11-08: all as recommended, and the ashtanga-expert review accepted)
- **Q134 Scope.** ✅ One combined read-only schedule across my shalas in my zone, weeks 0–3, filters, the ⚠ line, a Home row for any member, bot `/schedule`; no new data, no migration.
- **Q135 Followed teachers.** ✅ Only from shalas I've joined (👤 + *My teachers*); their other shalas stay invisible until a later visibility option. Q115 stays deferred.
- **Q136 Which time first.** ✅ My zone first; the class's own time and label second whenever offsets differ, offline included.
- **Q137 Merge "My classes".** ✅ The Home row becomes "🗓 My schedule", `/classes` opens it with *I teach*, times in my zone with the shala time as the second label; `GET /me/classes` deprecated for one release.
- **Q138 Filters.** ✅ All · My teachers · I teach on both surfaces; shala chips in the Mini App only, remembered per device; no type filter yet.
- **Q139 Window.** ✅ 4 weeks from my today, one week per page.
- **Q140 Shift line.** ✅ A ⚠ line per affected shala plus ⚠ on the day; nothing when both sides shift together.
- **Q141 Unknown zone.** ✅ Fall back to my first shala's zone, labelled, with "Set your city".
- **Q142 Day markers.** ✅ No shala 🌙 / day-off / "moved to" day lines; rows carry their own marks. (My own moon day is shown, see below.)
- **Q143 Teacher mark.** ✅ 👤 on rows taught that date by a linked teacher, substitutes included; only I see it.
- **Q144 Home.** ✅ A single row; no "next class" card yet.
- **ashtanga-expert review (owner, accepted):** (1) ` · 🌙` on rows held on their shala's moon day; (2) **included now** (owner's choice): my own moon day 🌙 on the day row, from my effective moon calendar (MD-02 inheritance included), read-only, no prompt, reading only the moon city and `moon_day`; (3) a moved cancelled row shows `(moon day) · 🔁 Sat 14 Nov`; (4) 🌙 instead of ❌ for moon cancellations, ❌ for closures and manual cancels; (5) "Dana (for Anna)" for a substitute covering my linked teacher; (6) copy: "I teach" / «Веду», RU genitive in `schedule-shift` via `$weekday` + `DateArg` style `long`.

## 11. Build notes (2026-11-08)
- **Measured** (local Postgres 17, a 7-day page, warm): worst case 15 shalas (10 staff, 5 student) × 40 daily series × 20 overrides = 4,200 rows: `member_windows` p50 25.8 ms / p95 30.8 ms; `GetMySchedule` (read + expansion) p50 119 ms / p95 126 ms. Realistic 2 shalas × 10 series: statement 6.3 ms, use case 10.1 ms. A first build measured 177 ms: `expand` built every occurrence of the ±13-day margin; it now builds only the window's (and a swap's A/B when they fall inside), SC-02's output unchanged.
- **Statements per tap:** 2 (account load + `member_windows`), pinned by a DB test.
- **Fallback zone order (Q141):** staff first, then by name (the read's order), not `/me/shalas`'s join order; deterministic and needs no seat timestamp in the read.
- **`/me/classes` (deprecated):** served by `GetMySchedule(only=mine)` regrouped per shala; drops the kept swap originals so its shape stays SC-02's; `today` is now the viewer's.
- **API additions:** `ScheduleOccurrenceOut` (`moon`, `swapped_to`) on the shala schedule and the occurrence PUT; `swapped_to` is set in My schedule only (the shala view names swaps on its day rows). `MyRowOut.planned` (HH:MM) for "moved from …".
- **Copy:** `schedule-swapped-from` ("🔁 instead of …", lowercase mid-row); the bot's long week ends "…" + `my-schedule-more`; RU half-hour hours as «0,5 часа»; the bot's second label uses the offset at the class's instant (`time-label`), right on a change night.
- **Import contract:** direct imports only (`allow_indirect_imports`), as the teacher-view contract: `ports.storage` re-exports every port.
- **Open nits (not done):** a11y labels for 👤 and the held ` · 🌙` in the Mini App rows; the shift line's `where` derived from the zone label string; a row tap opens the shala week by my week index (may be a day off when the zones' todays differ).
