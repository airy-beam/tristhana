# MD-02: moon calendar inheritance (teacher → student)

- Status: **accepted** (owner, 2026-11-07; ashtanga-expert copy fixes applied) · Date: 2026-11-07 · Size M, Phase 3
- Requirements: **MD-02** (teacher → own; student → main teacher's; all overridable). Touches MD-03 (reminders, picker), MD-04 (FYI, "Same as my city"), PR-09 (auto moon days), PR-10 (reminder skip days), ST-01 (stats markers), ST-09 (export), ID-04 (accept, make main, remove).
- Related: ADR-0019, 0022, 0029, 0030. New: **ADR-0032** (accepted). Fixed inputs: Q76, Q77, ID-04 §7 and §11.

## 1. Scope
**In:** one pure resolution rule for the **effective moon city**, used by every reader; a stored "Follow my teacher" choice; the source shown wherever the city is shown ("as {teacher}"); a notice to teachers that students follow their city; a one-line notice when the student's own tap changes their city; a one-tap "Keep" on the first-student note (§2); a reminder dedupe fix for a city that moves by a day.
**Out:** shalas (SC-01; the rule gains a shala step later, §3); per-event overrides (07 "an explicit choice can be overridden per event"); pushing a message to students when a teacher changes city; the MD-05 official import; any teacher view of a student's moon setting (ST-06 shows no moon).

## 2. Flows and copy
**Rule (Q76, Q77), read time, one hop:**
```
own choice is a listed city                      → that city               (CHOSEN)
own = "Follow my teacher", or own never chosen
  and the person has no students                 → main teacher's own
                                                   explicit city, if any    (TEACHER)
otherwise                                        → 📍 Mysuru default        (DEFAULT)
```
- "Main teacher" = ID-04 `effective_primary` (chosen, else oldest link). "Own explicit city" = the teacher's stored slug; a teacher's own "Follow my teacher" or NULL gives nothing (one hop), so the student falls to Mysuru.
- **"Own city" (Q76) = the person's own explicit choice, else the Mysuru default. It is never `home_city`** (decision 1). `07 Moon Days` ("No teacher → own city if known") and the resolution diagram are updated by notes-keeper. With this, a student following a teacher always sees what that teacher sees, except when the teacher has explicitly chosen "Follow my teacher".
- Never chosen includes legacy NULLs ("chose Mysuru before the ID-04 fix", not separable) and a slug removed from `cities.yaml`.

**Student (bot).**
- `/moon`: title unchanged (`moon-title`, effective city); under it, when TEACHER, `moon-source-teacher`. When the stored choice is "Follow my teacher" but the teacher has no city, `moon-source-teacher-none`.
- City picker (`m1:c`): first row `[👥 Follow my teacher (Anna)]` (`moon-follow-teacher`, new callback **`m1:f`**), shown only with a main teacher; ✓ when the effective source is TEACHER or the stored choice is follow. Then "Same as my city" (MD-04), then cities. Picking a city is a CHOSEN snapshot, as today.
- `/settings` line: `settings-moon-line-teacher` when TEACHER, else `settings-moon-line` as today.
- **Own-tap changes announce in place** (one lead line on the result screen, no message): ✅ on an invite (first link only, never-chose student), `[⭐ Make main]`, removing the main teacher (with `link-next-main`). `moon-follow-changed` when the new source is TEACHER, `moon-follow-ended` when it falls to Mysuru. Shown only when the effective **city slug** changes.
- **Changes the student didn't tap** (teacher changes city, teacher removes them, teacher deletes their account): **no message** (removal stays silent, ID-04 Q8). The label, the settings line, the Mini App card and every moon reminder name the current city (decision 4).
- The "🕐 Use {city} time?" button on `/moon` shows only for CHOSEN (`moon.py:182`): a teacher's city is not where the student lives (MD-04 Q3).

**Teacher (bot).** `/moon` and the Mini App card show `moon-teacher-shared` to anyone with ≥ 1 student. The invite screen adds `invite-moon-hint` under `invite-hint`, so a teacher is told before the first student links. A teacher who never chose shares nothing. **Q76 flip:** a never-chose student who gets their first student stops inheriting. The silent join note (`link-student-joined`) then carries `moon-teacher-own` and a one-tap **`[Keep 📍 Almaty]`** (`moon-keep-city`, decision 3):
- Callback **`m1:k:<slug>`** (≤ 29 bytes, stateless) carries the city the note named, i.e. the inherited one.
- `KeepMoonCity` validates the slug (unknown → `UnknownLocation`, re-render) and stores it as an **explicit choice**, only while `moon_location IS NULL`: one conditional `UPDATE … RETURNING`. Storing a slug the person saw is their own choice, so the one-hop and privacy rules hold.
- It is idempotent. A second tap, or a tap after any choice made since (a city or "Follow my teacher"), writes nothing.
- The note is edited in place: the Keep row goes, `[👥 My students]` stays, and one line is added: `moon-kept` after a write, `moon-keep-already` with the current city after a no-op. Answer first.

**Mini App.** Settings moon `<select>` gets a first option `moon-follow-teacher` (only with a main teacher), sending `{slug: null}`; the card and Settings show `moon-source-teacher` / `moon-teacher-shared`. Make main and Remove in `Links.tsx` invalidate `moon-days`, `days` and `stats`; no extra notice (the card label is the record).

**Copy** (⚑ all drafted here, ux-writer pass before release; «ты»; RU gender-neutral; names nominative, never after «у»):

| Key | Where | EN | RU |
|---|---|---|---|
| `moon-source-teacher` | both | 👥 Same as your main teacher, { $name }. You can choose another city. | 👥 Как у основного учителя: { $name }. Можно выбрать другой город. |
| `moon-source-teacher-none` | both | 👥 { $name } hasn't chosen a city yet, so the dates are for 📍 { $city } for now. | 👥 У учителя ({ $name }) пока не выбран город, поэтому даты считаются по городу 📍 { $city }. |
| `moon-follow-teacher` | both | 👥 Follow my teacher ({ $name }) | 👥 Как у учителя ({ $name }) |
| `settings-moon-line-teacher` | bot | 🌙 Moon days: 📍 { $city } (as { $name }) | 🌙 Лунные дни: 📍 { $city } (как у учителя: { $name }) |
| `moon-follow-changed` | bot | 🌙 Your moon days now follow { $name }: 📍 { $city }. You can change this in /moon. | 🌙 Лунные дни теперь как у учителя ({ $name }): 📍 { $city }. Поменять можно в /moon. |
| `moon-follow-ended` | bot | 🌙 Your moon days are now for 📍 { $city }. You can change this in /moon. | 🌙 Лунные дни теперь считаются по городу 📍 { $city }. Поменять можно в /moon. |
| `moon-teacher-shared` | both | `{ $chosen -> [yes] 👥 Students who haven't chosen a city follow yours: 📍 { $city }. *[no] 👥 Your students' moon days are for 📍 { $city }, like yours. You can keep it or choose your city in /moon. }` | `{ $chosen -> [yes] 👥 У учеников, которые не выбрали город, лунные дни как у тебя: 📍 { $city }. *[no] 👥 У учеников лунные дни считаются по городу 📍 { $city }, как и у тебя. Можно оставить так или выбрать свой город в /moon. }` |
| `invite-moon-hint` | bot | Students who haven't chosen a moon city will follow the city you choose in /moon. | У учеников, которые не выбрали город, лунные дни будут считаться по городу, который ты выберешь в /moon. |
| `moon-teacher-own` | bot | 🌙 Now that you have students, your moon days follow your own setting: 📍 { $city }. To keep 📍 { $kept } (as with { $name }), tap below. | 🌙 Теперь, когда у тебя есть ученики, лунные дни считаются по твоей настройке: 📍 { $city }. Чтобы оставить 📍 { $kept }, как у учителя ({ $name }), нажми кнопку ниже. |
| `moon-keep-city` | bot | Keep 📍 { $city } | Оставить 📍 { $city } |
| `moon-kept` | bot | 🌙 Done: your moon days stay with 📍 { $city }. You can change this in /moon. | 🌙 Готово: лунные дни остаются по городу 📍 { $city }. Поменять можно в /moon. |
| `moon-keep-already` | bot | 🌙 Your moon city is already chosen: 📍 { $city }. You can change it in /moon. | 🌙 Город для лунных дней уже выбран: 📍 { $city }. Поменять можно в /moon. |

`moon-calc-note` ("…follow your teacher") stays true. In the Mini App, `moon-teacher-shared` [no] ends "…or choose your own city." / «…или выбрать свой город.», since /moon is a bot command (ux-writer, 2026-11-07). A `[follow]` variant drops "like yours" / «как и у тебя» for a teacher who chose "Follow my teacher" (owner, 2026-11-07). `$name` falls back to `link-no-name`.

## 3. Domain, use cases, ports
`domain/moon.py` (pure):
```python
FOLLOW_TEACHER = "-teacher"  # account.moon_location; never a slug (loader: kebab-case, no leading "-")
class MoonSource(StrEnum): CHOSEN = "chosen"; TEACHER = "teacher"; DEFAULT = "default"
@dataclass(frozen=True, slots=True)
class TeacherMoon: id: UUID; name: str | None; moon_location: str | None   # the main teacher's own value
@dataclass(frozen=True, slots=True)
class MoonFollow: city: City; source: MoonSource; teacher: TeacherMoon | None; follow_chosen: bool
def moon_follow(own: str | None, teaches: bool, teacher: TeacherMoon | None, cities: Cities) -> MoonFollow
```
- `teacher` is set for TEACHER, and for `follow_chosen` with a teacher who has no city (for `moon-source-teacher-none`). `cities.find(teacher.moon_location)` makes FOLLOW_TEACHER, NULL and removed slugs all "no city", which is the one-hop rule.
- `Account` += `teaches: bool = False`, `main_teacher: TeacherMoon | None = None`; `moon_follow_of(account, cities)` in `domain/accounts.py`. **Every reader replaces `cities.get(account.moon_location) or default` with it:** `application/days.py:107`, `stats.py:62`, `moon.py:_city`, `export.py:196`, `bots/telegram/settings.py:207`, `moon.py:225` (picker ✓), and `api/v1/moon.py:202`.
- **Tick:** `ReminderCandidate` += `teaches`, `teacher_location`; `tick.py:98` calls `moon_follow`. Practice reminders' moon skip (`domain/notifications.py:248`) and moon reminders then follow the effective city with no other change.
- **Reminder dedupe:** `moon:<date>:<k>` is keyed on the date, so a city moving by a day could send a second "7 days before" for one event. `due_moon_reminders` treats a final key for `date ± 1` with the same `k` as sent (two moon days are never within 2 days). This was already possible after a manual city change.
- SC-01 later: a SHALA step between TEACHER and DEFAULT and `MoonSource.SHALA`; no schema here.

**Use cases** (`application/moon.py`, both adapters):
- `SetMoonLocation.execute(principal, slug | None)`: a slug as today; **`None` now stores `FOLLOW_TEACHER`** (ID-04 §7 reserved it). Nothing writes NULL any more. `"-teacher"` as a slug raises `UnknownLocation`.
- `GetMoonView`: `MoonView` += `follow: MoonFollow`, `shared: bool | None` (None = no students; else whether the teacher chose a city). `explicit` = `source is CHOSEN or follow_chosen`.
- `application/teacher_links.py`: `AcceptInvite`, `SetPrimaryTeacher` and `RemoveTeacher` return `moon: MoonFollow | None`, the new follow when the effective slug changed (before = principal; after = from the result). `AcceptInvite` also decides the teacher's `moon-teacher-own` line and Keep button (first student, never chose, inheriting a city before). It passes the inherited city to `Notifier.tell_student_joined(recipient, name, keep: City | None)`.
- `KeepMoonCity.execute(principal, slug) -> KeepResult(kept: bool, follow: MoonFollow)` (bot only): raises `UnknownLocation`; otherwise calls `AccountRepository.set_moon_location_if_unset(account_id, slug) -> Account | None`, which is one statement (`UPDATE … WHERE moon_location IS NULL RETURNING`; None = already chosen, in which case the principal is used for `follow`).

**Ports:** `Accepted` += `teacher_moon: str | None` and the teacher's own inputs (prior student count, own main teacher's slug and name); `Linked` (teacher rows only) += `moon_location`. Same statements, more columns.

**Loading the inputs in the same round trip.** The middleware's account statement (`find_by_identity`, and every `RETURNING _COLUMNS`) gains, through one helper: `teaches = EXISTS(teacher_link WHERE teacher_id = account.id)` (index `teacher_id, student_id`) and the main teacher's `(id, display_name, moon_location)` via `ORDER BY is_primary DESC, created_at, teacher_id LIMIT 1` (PK prefix `student_id`, ≤ 20 rows) joined to the teacher's `account` PK. The tick's `candidates` adds the same (built: `teaches` and the main teacher's `moon_location` as correlated per-row subqueries on the same indexes, not a `DISTINCT ON` CTE; still 3 statements, `EXPLAIN` test). No reader gains a statement.

## 4. API (initData; `{code}` errors; `gen:api`)
| Method, path | Change | Policy |
|---|---|---|
| `GET /api/v1/me/moon-days` | `Location` += `source: "chosen" \| "teacher" \| "default"`, `follow_chosen: bool`, `teacher: {id, name} \| null`, `shared: {chosen: bool} \| null` (only for the caller with students) | own |
| `PUT /api/v1/me/moon-location` | `{slug: null}` = **Follow my teacher** (stores the sentinel; works with no teacher: then Mysuru until one links). Response = the new `Location` | own |
| `GET /api/v1/me/days` | `moon_location` = effective slug (unchanged meaning) | own |

`explicit` stays for old clients. The teacher's `moon_location` is never returned raw; only the resolved city. No new `ErrorCode`.

## 5. Migration
**None.** The CHECK `moon_location ~ '^[a-z-]{1,24}$'` accepts `-teacher`; no city slug can start with `-` (`cities_yaml.py` `_SLUG`). Existing indexes cover both lookups (`EXPLAIN` test with 500 students and 20 teachers). Release: one deploy, backend before Mini App, either order safe (old app ignores new fields).

## 6. Cross-cutting checks
- **Time zones.** The moon **date** is the followed city's local date (tithi at that city's sunrise), and the student's day stays in the student's zone. Auto-rest compares the student's `local_date` with that date; reminders fire at 19:00 in the student's zone. This is exactly what happens today for an Almaty student following Mysuru, and it matches 06 ("Moon days: location, separate from the user's zone") and 07 ("follow your teacher"). The tradition follows the shala's date, not the instant. Dates only, so no zone label. MD-04's ℹ line keeps comparing with the student's own home city.
- **Past days.** Logged 🌙 rows (`day_log.status = moon`, sealed) are statements and never rewritten. Auto moon days are derived at read time (ADR-0022), so a change of effective city re-derives past unlogged days by ±1 day in Days and the stats heatmap, as a manual city change already does. **Runs don't move:** auto days are unmarked for the 7-day bridge. **"X of Y possible days" can drop slightly in one rare case:** the moon date moves onto a day the person logged as practice, so the old date, unlogged, is no longer an auto moon day and becomes a possible but missed day. This is accepted (decision 5). An effective-from date, like `day_off_since`, is the later upgrade path.
- **Storage.** All 34 cities are already computed for previous year … current + 2 by the tick, so inheritance adds **no computation**; a teacher can only choose a listed city.
- **Privacy.** The first teacher data to cross a link is the teacher's **explicitly chosen** city, and only as the resolved city on the student's own screens. Never chose = nothing shared. Told to teachers before the first link (`invite-moon-hint`) and on `/moon` (`moon-teacher-shared`). The teacher's own teacher's city never crosses (one hop is a privacy rule too). `teaches` and the student's own setting never reach the teacher; ST-06 is unchanged. **Export:** `moon_city` += `source` (`default` kept), the effective slug, no teacher id or name (ID-04 Q14).
- **i18n.** All keys in `bot.ftl` / `app.ftl`, en + ru; RU names in parentheses or after a colon, never declined.
- **Responsiveness.**

| Tap | Statements | Note |
|---|---|---|
| Any tap (account load) | unchanged (1) | + 1 EXISTS + 1 ≤ 20-row index read, sub-ms |
| `/moon`, Today, days, stats | unchanged | rule is pure CPU |
| `m1:f` Follow my teacher | 2, as `m1:s` | |
| `m1:k:<slug>` Keep | 2 (account load + conditional UPDATE) | edit in place, no outbound |
| ✅ invite, Make main, Remove | unchanged | extra columns only |
| Tick candidates | unchanged (3) | + `DISTINCT ON` CTE |

## 7. Test plan
- **Domain:** `moon_follow` table test: CHOSEN listed / removed slug; never chose with and without students; follow chosen with and without students; teacher with a city / NULL / FOLLOW_TEACHER / removed slug (→ DEFAULT, one hop); no teacher; a cycle A↔B (both teach → own). `FOLLOW_TEACHER` can't be a city (loader rejects it). Dedupe: a sent `date−1`/`date+1` key with the same `k` suppresses; a different `k` doesn't.
- **Application, fakes:** every reader listed in §3 uses the effective city (parametrized over GetDays auto moon, stats markers, GetMoonView, settings line, export, tick); `SetMoonLocation(None)` stores the sentinel; `explicit` true for follow; AcceptInvite on a never-chose student returns the change, on a chose-Mysuru student returns none; second link returns none; make main and remove return the change only when the slug changes; the teacher-side `moon-teacher-own` and the Keep city only on the first student of a never-chose, inheriting teacher (none on a second student, for a teacher who chose, or one who had nothing to inherit); `KeepMoonCity` on NULL stores the slug and the person becomes CHOSEN; after a city or "Follow my teacher" choice it writes nothing and returns `kept=False` with the current follow; twice in a row it writes once; an unknown slug and `-teacher` raise; a logged 🌙 is unchanged after a city change.
- **DB (real Postgres):** the account load fills `teaches`/`main_teacher` identically in `find_by_identity` and each `RETURNING` method; its order matches `effective_primary`; teacher deletion cascades and the next oldest takes over; the tick CTE matches the domain for a seeded mix; `set_moon_location_if_unset` writes only on NULL, and two concurrent taps write once; statement counts as §6; `EXPLAIN` uses `teacher_link` indexes; app role.
- **API:** `Location` key set exact; `teacher` null unless TEACHER or follow; `shared` only with students; `{slug: null}` → `source` teacher; `"-teacher"` as slug → 422 `unknown_location`; no raw teacher `moon_location` anywhere in OpenAPI; TS client builds.
- **Bot, through the webhook:** `/moon` lines per source in both locales; picker row only with a main teacher, ✓ rules, `m1:f` ≤ 64 bytes and `m1:s:-teacher` re-renders; "Use … time" absent for TEACHER; ✅ / Make main / Remove lead lines; join note with and without `moon-teacher-own`; the Keep button sits on that note only, `m1:k:<slug>` ≤ 64 bytes, a tap edits the note in place (Keep row gone, `[👥 My students]` kept, `moon-kept`), a tap after a choice shows `moon-keep-already` and writes nothing, a forged or unknown slug re-renders `/moon` and writes nothing, `answered` before the write; teacher `/moon` shared line; settings line; `answered` first.
- **Mini App (Vitest, also `TZ=UTC`):** follow option only with a teacher, sends null; card source line; teacher line; cache invalidation after make main and remove; RU at 320 px; `check:bundle`.
- **i18n/architecture:** ftl parity; RU avoid-word and gendered-ending greps; no name after «у»; import-linter (domain pure, aiogram only in `bots/telegram`).
- **Owner on a phone:** a student linking to a teacher in Almaty; the teacher changing city; the label on both surfaces.

## 8. Decisions (owner, 2026-11-07; as recommended except 3; ashtanga-expert copy fixes in §2)
1. **"Own city" (Q76)** = the person's own explicit choice, else the Mysuru default. **Never `home_city`:** a live link to it would move moon days on travel (ADR-0029), and every never-chose person would switch on release. "📍 Same as my city" stays one tap. notes-keeper updates `07 Moon Days` ("own city if known") and the resolution diagram.
2. **Teacher with no explicit city (Q77 fallback):** the student gets the Mysuru default, labelled as the default with no teacher name. A student who chose "Follow my teacher" sees `moon-source-teacher-none`. Never the teacher's inherited value.
3. **First-student flip (changed from the recommendation):** the silent join note carries `moon-teacher-own` and a one-tap `[Keep 📍 {city}]` (`m1:k:<slug>`). The tap stores the inherited city as the person's explicit choice, only while they have none. It is idempotent, edits the note in place, and is a no-op with `moon-keep-already` if they chose in the meantime. Losing the last student flips back silently, because a notice would reveal a silent removal.
4. **Changes the student didn't make** (teacher changes city, removal by the teacher, account deletion): no message. Labels and reminders name the city.
5. **Past unlogged moon days re-derive** with the new city (ADR-0022). Runs don't move. "X of Y possible days" can drop slightly in the rare case in §6; accepted. An effective-from date is the later upgrade path.
6. **Teacher notice:** `invite-moon-hint` plus `moon-teacher-shared`, no opt-out. Not choosing shares nothing.
7. **"Follow my teacher"** is the sentinel `-teacher` in `moon_location`. No migration; `PUT {slug: null}` stores it.
8. **Release:** existing never-chose students linked to a teacher with a non-Mysuru city switch silently on deploy; accepted. The owner may count them first with a read-only query (☁️).
9. **Export:** the effective slug plus `source`, with no teacher id or name.
10. **Reminder dedupe:** a sent key for date ±1 with the same "days before" counts as sent.
