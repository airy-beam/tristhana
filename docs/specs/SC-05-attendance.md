# SC-05: attendance (staff mark who came in bulk; students mark themselves; staff confirm)

- Status: **accepted** (owner, 2026-11-09: Q180–Q196 as recommended, with the ashtanga-expert review applied, see §9) · Size M, Phase 3
- Requirements: **SC-05** ("Teacher logs attendance for a class (bulk), or students self-log and the teacher confirms"). Builds on SC-01 (ADR-0033), SC-02 (ADR-0034, the occurrence key), SC-03 (ADR-0035, `GetMySchedule`). Resolves the deferred Q107/Q120 ("practises here"). Prepares ST-08 (shala dashboard) and the NT-03 "class attendees" audience (Q162).
- Related: ADR-0008, 0016, 0027, 0030, 0031, 0033, 0034, 0035, 0038. New: **ADR-0039** (proposed).

## 1. Scope
**In:**
- A student (or a staff member who practises) marks "🙋 I was there" on a class that has started, from today back 6 days. The mark is `claimed`.
- Staff open a roster for one occurrence, then mark or unmark people one tap at a time and "✅ Confirm all 🙋". Staff marks are `confirmed`.
- The student sees their own mark on their My schedule rows and can remove it.
- Staff see counts on the occurrence.
- The shala consent texts gain one bullet each.

**Out / later:**
- History and stats past 7 days, including per-class, per-weekday and growth views (ST-08).
- "I'm coming" and capacity (SC-04). Payments and passes. Arrival times. QR or geo check-in.
- Absence reasons and "no-show" lists. Pushes of any kind.
- An attendees audience for announcements (NT-03, which will read `class_attendance` by `(class_id, on_date)`).
- Prompting attendance from a logged practice. Linked teachers who aren't on the staff seeing attendance (ST-06 unchanged). Editing beyond 7 days.

**Unchanged:**
- The log. Attendance never reads or writes `day_log`, `practice`, rest periods, check-ins, the diary or progression (ADR-0039). Streaks, GM-01 counts and stats ignore it.
- Classes, their expansion and the moon policy.

## 2. Flows and screens
**Who can mark:**
- Claim: any member of the shala (`can_claim_attendance`).
- Take attendance: any staff seat, meaning owner, Manager, Teacher, Assistant or Front desk (`can_take_attendance`, Q181).
- Non-members get `NotFound`.
- 1:1 classes are staff-only (Q121), so only staff mark them.

**When:**
- The occurrence isn't cancelled (moon, closure or staff).
- It has started: `starts_at <= now`. A Mysore window counts from its opening time.
- Its `on` is ≥ the class zone's today − 6.
- Otherwise `not_attendable`.

**Moves and swaps:** a moved or swapped occurrence keeps its rule-date key. The kept original of a swap (cancelled on A) can't be marked.

**Student, bot.** My schedule (`c1:m`) gains `[🙋 I was there…]` (`v1:l`) for any member. Its screen lists the started classes of the last 7 days, newest first, at most 10, in my zone:
```
🙋 Mark a class you came to (today and the 6 days before)
[◻️ Mon 9 Nov 06:00 Mysore · Ashtanga Almaty]
[🙋 Sun 8 Nov 08:00 Led Primary · Ashtanga Almaty]
[✅ Fri 6 Nov 07:00 Pranayama · Ashtanga Almaty]
[⬅ Back]
```
- Tapping ◻️ claims (`v1:i`). The row becomes 🙋 in place (the keyboard is patched from the message itself), with `attend-claimed` above and `[🧘 Log this day]` (only after a Mysore, Led, 1:1, Workshop or Pranayama claim; never after Conference or Chanting, Q196). That button opens the existing day card (`d1`) for **my local date of the instant**. The bot logs nothing on its own (Q183).
- Tapping 🙋 or ✅ removes my mark (`v1:u`), shows `attend-removed`, and the row goes back to ◻️.
- No mark creates or changes a log entry.
- My schedule rows that carry a mark end with ` · 🙋` or ` · ✅` (`attend-row-mark`).

**Staff, bot.**
- `[📋 Attendance…]` (`v1:p`) appears on the shala schedule (`c1:w`) and, for staff, on My schedule. It lists the started occurrences of the last 7 days at shalas where I'm staff, mine (teaching or covering) first, then newest, at most 10. Each row reads like `Mon 9 Nov 06:00 Mysore · ✅ 12 · 🙋 2`.
- Tapping a row opens the roster (`v1:r`):
```
📋 Mysore · Mon 9 Nov, 06:00–09:30 Almaty (UTC+5)
Ashtanga Almaty · ✅ 12 · 🙋 2 to confirm
Tap a name to mark who came. 🙋 = their own mark.
[🙋 Dana]  [🙋 Ilya]
[✅ Anna]  [✅ Boris · staff]
[◻️ Vera]  [◻️ Gleb]
[◻️ Oleg]  [◻️ Rita]
[✅ Confirm all 🙋 (2)]
[◀] [▶]   [⬅ Back]
```
- **Roster order (Q191):** claims, then **regulars** (rows on this class series in the last 28 days), then by name. 8 per page, 2 per row.
- **Who is on the roster:**
  - current students;
  - staff who "practise here", derived from attendance at this shala in the last 90 days (Q187);
  - anyone with a row on this occurrence.
- **Taps:**
  - ◻️ or 🙋 → `confirmed` (`v1:y`). ✅ → removed (`v1:n`). Each callback carries its target state, so a retry is idempotent.
  - `v1:a` confirms every current claim.
  - The counts line and the tapped button are edited in place from the write's `RETURNING`.
- A stale or forged tap re-renders the roster. A closed occurrence shows `attend-not-open`.

**Mini App:**
- **My schedule:** a ◀ page down to week −1, so rows from the last 7 days are visible.
  - A started, attendable row gets a small `🙋 I was there` button.
  - A marked row shows a `✅` or `🙋` chip. Tapping the chip asks "Remove your mark?" (native confirm), then sends DELETE.
  - After a claim, a status line shows `attend-claimed` and, for Mysore, Led, 1:1, Workshop or Pranayama only (Q196), a `🧘 Log this day` link to the day sheet.
- **Staff:**
  - The SC-02 occurrence sheet gains `📋 Attendance · ✅ 12 · 🙋 2`. It opens the lazy `Attendance` chunk.
  - The chunk shows a header with the zone label, the counts, a name search (server `q`), and `✅ Confirm all 🙋 (n)`.
  - Rows have checkboxes, with a "staff" tag and a 🙋 hint.
  - A sticky `Save (n changes)` sends one PATCH with the deltas. It isn't optimistic. A 409 refetches and shows `attend-not-open`.
- RU at 320 px: names wrap, and the buttons stack.

**Notifications: none (Q189).** No push to staff on a claim. No push to a student who is marked or confirmed. Pending claims show only as counts.

**Copy** (⚑ = draft for the ux-writer; «ты»; RU gender-neutral, so no «был/была» and no «сам/сама»):

| Key | EN | RU |
|---|---|---|
| `attend-me-open` ⚑ | 🙋 I was there… | 🙋 Отметиться… |
| `attend-me-title` ⚑ | 🙋 Mark a class you came to (today and the 6 days before) | 🙋 Отметка о посещении: выбери занятие (за сегодня и 6 предыдущих дней) |
| `attend-me-none` | No classes to mark in the last 7 days. | За последние 7 дней отмечать нечего. |
| `attend-claimed` ⚑ | 🙋 Marked: { $class }, { $day }. The shala's staff can confirm it. | 🙋 Отмечено: { $class }, { $day }. Сотрудники шалы могут это подтвердить. |
| `attend-removed` | Mark removed: { $class }, { $day }. | Отметка снята: { $class }, { $day }. |
| `attend-state` | `{ $s -> [confirmed] ✅ confirmed *[claimed] 🙋 your mark }` | ✅ подтверждено / 🙋 твоя отметка |
| `attend-row-mark` | · ✅ / · 🙋 (a11y: you were there, confirmed / your mark) | · ✅ / · 🙋 (a11y: посещение подтверждено / твоя отметка) |
| `attend-log-day` | 🧘 Log this day | 🧘 Записать этот день |
| `attend-staff-open` | 📋 Attendance… | 📋 Посещаемость… |
| `attend-staff-pick` | 📋 Which class? Last 7 days. | 📋 Какое занятие? Последние 7 дней. |
| `attend-roster-title` | 📋 { $class } · { $day }, { $time } | same |
| `attend-roster-counts` | ✅ { $confirmed } · { $claimed -> [0] nothing to confirm [one] 🙋 1 to confirm *[other] 🙋 { $claimed } to confirm } | ✅ { $confirmed } · { $claimed -> [0] подтверждать нечего [one] 🙋 { $claimed } ждёт подтверждения [few] 🙋 { $claimed } ждут подтверждения *[many] 🙋 { $claimed } ждут подтверждения } |
| `attend-roster-hint` ⚑ | Tap a name to mark who came. 🙋 = their own mark. | Нажми на имя, чтобы отметить посещение. 🙋 — собственная отметка. |
| `attend-confirm-all` | ✅ Confirm all 🙋 ({ $n }) | ✅ Подтвердить все 🙋 ({ $n }) |
| `attend-staff-tag` | · staff | · сотрудник |
| `attend-empty` | No one on the list yet. Students appear here once they join the shala. | Список пока пуст. Ученики появятся здесь, когда присоединятся к шале. |
| `attend-not-open` | This class can't be marked now: it hasn't started, it was cancelled, or it was more than 7 days ago. | Это занятие сейчас нельзя отметить: оно ещё не началось, отменено или было больше 7 дней назад. |
| `shala-join-consent` += bullet ⚑ | • The shala's staff can mark that you came to a class, and so can you. You see these marks and can remove them any time. | • Посещение занятий могут отмечать сотрудники шалы, и ты тоже. Эти отметки видны тебе, и их можно снять в любой момент. |
| `shala-staff-consent` += bullet | • You can mark who came to its classes. | • Можно отмечать посещение занятий. |

Reused: `class-type`, `context-*`, `day-label`, `time-label`, `schedule-zone`, `class-gone`, `log-back`, `page-prev/next`, `link-no-name`. Banned words: "absent", "missed", "no-show", «пропустил(а)», «прогул».

## 3. Domain, use cases, ports
`domain/attendance.py` (pure):
```python
class AttendanceState(StrEnum): CLAIMED = "claimed"; CONFIRMED = "confirmed"
BACK_DAYS = 6; REGULAR_DAYS = 28; PRACTISES_HERE_DAYS = 90; MAX_DELTA = 100; BOT_PAGE = 8; API_PAGE = 50
@dataclass Snapshot: shala_id, class_id, key: date, on: date, starts_at: datetime, zone: str, type: ClassType
class NotAttendable(ValueError)
def attendable(o: Occurrence, zone: str, now: datetime) -> bool   # not cancelled, starts_at <= now, o.on >= local_today(zone, now) - BACK_DAYS
def snapshot(o: Occurrence, shala_id, zone) -> Snapshot
def claim_state(may_take: bool) -> AttendanceState                # staff claim = CONFIRMED
def merge(current: AttendanceState | None, new: AttendanceState) -> AttendanceState   # never downgrades CONFIRMED
```
**Policies (`application/policies.py`, on the `Membership` from the same read):**
- `can_claim_attendance(m)`: any member.
- `can_take_attendance(m)`: `m.staff`.
- `can_view_roster` is the same as `can_take_attendance`.
- Removing your own row needs no membership check: it only ever deletes the caller's own row.

**Use cases (`application/attendance.py`, bot and API):**
- `ClaimAttendance(principal, class_id, key) -> MyMark`:
  1. `occurrence(me, class_id, key)`.
  2. `expand` that one series (the existing helper, made public).
  3. `attendable` → `snapshot` → `claim(…, claim_state(staff))`.
- `RemoveMyAttendance(principal, class_id, key)`: deletes your own row, 1 statement, idempotent.
- `GetRoster(principal, class_id, key, q, offset, limit) -> Roster`: `NotAllowed` for students.
- `MarkAttendance(principal, class_id, key, present, removed, confirm_claims=False) -> Counts`:
  - Raises `invalid_attendance` when ≤ 100 each is exceeded, when an id is in both sets, or when an id isn't on the roster.
  - Raises `NotAttendable` when the occurrence can't be marked.
- `GetMySchedule` (SC-03): `MyRow` += `attendance: AttendanceState | None`, `can_claim: bool`.
- `GetSchedule` (SC-02): for staff, `Occurrence` counts `(confirmed, claimed)`.
- Today is the **class zone's** local date, from the Clock.

**Port `AttendanceRepository` (`Storage.attendance`), one statement each:**
- `occurrence(me, class_id, key)`: a `ScheduleWindow` limited to this class over `[key−13, key+13]` (membership, shala, series, overrides, closures, swaps, moon dates), plus my row. None means not a member or unknown.
- `roster(me, class_id, key, q, offset, limit)`: the same, plus the people page (name, state, staff, regular) and the counts.
- Guarded writes (SC-01 `Guarded[T]` pattern; the CTE re-checks the seat and the target memberships):
  - `claim(me, snapshot, state)`: upsert that keeps `confirmed`.
  - `remove(me, class_id, key)`.
  - `mark(me, snapshot, present, removed, confirm_claims) -> Counts`.
- `ScheduleRepository.member_windows` += my rows in the window (scalar subquery). `window` += per-`(class_id, key)` counts when the caller is staff.
- `RemoveStudent` / `RemoveStaff` / leave also run `DELETE FROM class_attendance WHERE shala_id AND account_id` in their statement (Q186).

**Import contract:** `application.attendance` imports no `ports.practice/days/rest_periods/check_in/diary/progression` and no crypto (direct imports, as in SC-03).

## 4. API (initData; `{code}` errors; `no-store`; `gen:api`; additive)
| Method, path | Request → Response | Policy |
|---|---|---|
| `GET /api/v1/me/schedule` | `MyRowOut` += `attendance: "claimed"\|"confirmed"\|null`, `can_claim: bool` (`from` already allows today−7) | unchanged |
| `PUT /api/v1/me/attendance/{class_id}/{key}` | no body → 200 `{class_id, key, state}`; 404 unknown or not a member; 409 `not_attendable` | `can_claim_attendance` |
| `DELETE /api/v1/me/attendance/{class_id}/{key}` | → 204, idempotent | own row |
| `GET /api/v1/shalas/{id}/schedule` | `ScheduleOccurrenceOut` += `attendance: {confirmed, claimed} \| null` (null for non-staff) | unchanged |
| `GET /api/v1/shalas/{id}/classes/{class_id}/occurrences/{key}/attendance` | `?q=&offset=&limit=1..50` → `RosterOut {occurrence: {key, on, start, end, starts_at, zone, city, type, title, cancelled}, attendable, confirmed, claimed, people: [{account_id, name, state: "claimed"\|"confirmed"\|null, staff}], more}` | `can_take_attendance` (student 403, non-member 404) |
| `PATCH` the same path | `{present: uuid[] ≤ 100, removed: uuid[] ≤ 100, confirm_claims?: bool}` → `{confirmed, claimed}`; 409 `not_attendable`; 422 `invalid_attendance` | `can_take_attendance` |

`ErrorCode` += `not_attendable`, `invalid_attendance`. Times are `"HH:MM"` in the class zone, plus `starts_at` (UTC). The client labels them with `Intl`.

## 5. Bot (prefix **`v1:`**, free; uuids base64url 22 chars; dates `yyyymmdd`; answer first, edit in place)
| Data | Meaning | Bytes |
|---|---|---|
| `v1:l` · `v1:p` | my list · staff picker | 4 |
| `v1:i:<class>:<date>` · `v1:u:…` | claim · remove mine | 36 |
| `v1:r:<class>:<date>:<page>` · `v1:a:…` | roster page · confirm all claims | ≤ 40 |
| `v1:y:<class>:<date>:<acct>:<page>` · `v1:n:…` | mark present · unmark | **63** (page ≤ 999) |

Policies are re-checked on every tap, and malformed data does nothing (`nothing()`).

**Statements:**
- Lists and roster pages: 2 (account + read).
- Claim, remove and toggles: 3 for claim and toggles (account + occurrence read + guarded write), 2 for remove.
- Edited in place from the tapped message's keyboard and the write's `RETURNING`, with no re-read.

## 6. Migration `0025_class_attendance` (expand-only, down `0024`)
- `class_attendance`:
  - `id uuid PK default gen_random_uuid()`
  - `shala_id → shala ON DELETE CASCADE`
  - `class_id uuid NULL → shala_class ON DELETE SET NULL`
  - `occurrence_key date NOT NULL`
  - `account_id → account ON DELETE CASCADE`
  - `state text NOT NULL CHECK IN ('claimed','confirmed')`
  - `class_type text NOT NULL CHECK IN (the 7 types)`
  - `on_date date NOT NULL CHECK |on_date − occurrence_key| ≤ 12`
  - `starts_at timestamptz NOT NULL`
  - `zone text NOT NULL` (IANA)
  - `created_at`, `updated_at timestamptz NOT NULL DEFAULT now()`
- `UNIQUE (class_id, occurrence_key, account_id)`.
- Indexes: `(shala_id, on_date)` (ST-08, practises-here), `(account_id, on_date)` (my rows, export).
- `op.f()` names. App-role grants. `alembic check`. No backfill.
- Account delete coverage: the new account FK is in the `is_account_gone` test.
- No `marked_by` column, so the row doesn't record which staff member marked it (less personal data).

## 7. Cross-cutting checks
- **Time zones ✔.**
  - Keys and `on` are class-zone dates. Started means `now (UTC) >= starts_at`. The 7-day window uses the class zone's today.
  - The snapshot stores the UTC instant and the IANA zone, never an offset. Labels are recomputed at that instant (`06:00 Almaty (UTC+5)`), so they're right across DST.
  - The student's list and rows use **my** zone (SC-03 rules, second label when the offset differs).
  - `Log this day` targets my local date of the instant. A Berlin 21:30 online class is the next day for an Almaty viewer.
  - Half-hour zones and the DST gap/fold go through `wall_to_utc`.
- **Privacy ✔.**
  - Attendance is shala data about presence. The person themselves and that shala's staff see it, and no one else does: no other students, no counts for students, no linked teacher unless they're on the staff.
  - The log is never read, so no rest, moon or 🌸 reason can appear. This is stricter than SC-01 §9's "🌸 as rest".
  - Nothing is encrypted, since nothing is sensitive (ADR-0016 unchanged).
  - Names are already visible to staff (Q106), and buttons use plain names.
  - Consent: one bullet each, no re-consent (Q190).
  - Leaving or removal deletes the rows; deleting an account cascades.
  - **Export (ST-09):** the person's own rows (`on_date`, `starts_at`, `zone`, `class_type`, shala name, state). A staff member's export holds none of the rows they marked.
- **i18n ✔.** Every key is in `bot.ftl` and `app.ftl` with en/ru parity. RU plurals go through Fluent (`ждёт/ждут`). RU is gender-neutral. Class names come from `class-type`/`context-*`, dates from `day-label`.
- **Responsiveness ✔.**
  - §5 statement counts. Expansion of one series is sub-millisecond.
  - The roster query is indexed (`shala_student (shala_id, …)`, the unique prefix `(class_id, occurrence_key)` for regulars).
  - **Measure before done:** 1000 students and 30 staff, 28 days of rows. Targets: roster statement p50 < 30 ms, tap p50 < 150 ms warm.
  - The Mini App `Attendance` chunk is lazy, initial JS is unchanged, and `check:bundle` runs.

## 8. Test plan
- **Domain:**
  - `attendable`:
    - a Mysore window that has started, and one that hasn't;
    - a Led class at its start minute;
    - today − 6 is in and − 7 is out, in the class zone (a Los Angeles shala seen at Almaty midnight);
    - cancelled (moon, closure, staff) is out;
    - a `pranayama`-policy Pranayama class on a moon day is in;
    - `open` policy Mysore on a moon day is in;
    - a staff "hold anyway" class on a moon day is in;
    - a moved occurrence keeps its key;
    - a swapped occurrence on B is in, and the kept original on A is out;
    - a spring-gap start is shifted.
  - `snapshot` round-trips the label across 25 Oct 2026 in Berlin.
  - `merge` never downgrades. `claim_state` gives staff `CONFIRMED`.
- **Policies:** the role × action matrix (owner, Manager, Teacher, Assistant, Front desk, student, non-member, a linked teacher who isn't a member).
- **Use cases (fakes, fixed clock):**
  - claim → `claimed`;
  - staff self-claim → `confirmed`;
  - a confirmed row stays confirmed on a re-claim;
  - `not_attendable` before the start, after 7 days, and when cancelled;
  - a forged key is `NotAttendable`;
  - non-member → `NotFound`; student roster → `NotAllowed`;
  - `invalid_attendance` for an id that isn't a member, an overlap, or > 100;
  - `confirm_claims` confirms only the current claims;
  - a concurrent claim isn't lost by a staff delta;
  - a claim on a moon-day class leaves streaks, GM-01 counts and the 🌙 rest day unchanged (ashtanga-expert);
  - `Log this day` is offered after Mysore, Led, 1:1, Workshop and Pranayama claims and not after Conference or Chanting (Q196);
  - removing my own row is idempotent and needs no seat (a race with a leave can't fail).
  - **Privacy:** the roster shape has no log field, and a student who logged 🌸 that day looks the same as any other.
  - **Import contract:** no log ports.
- **DB (real Postgres):**
  - every CHECK and the unique key;
  - class delete → `class_id` NULL and the row stays; shala delete cascades; account delete cascades;
  - leave and remove delete the rows in the same statement;
  - the guarded CTE refuses a demoted or removed staff member;
  - roster order (claims, regulars, name);
  - practises-here staff appear after a row in the last 90 days;
  - statement counts per §5; the §7 measurement;
  - 0025 up/down/up; app-role grants.
- **API:**
  - 401; exact key sets; 404 vs 403 vs 409 vs 422;
  - `attendance` is null for students on the shala schedule;
  - `can_claim` on My schedule rows;
  - `limit` > 50 → 422;
  - the TS client builds.
- **Bot (webhook):**
  - EN and RU lists, the roster, toggles edited in place, confirm all, paging;
  - the `Log this day` target date for a cross-zone class;
  - a stale or forged tap; callbacks ≤ 64 bytes (63 asserted); answered first;
  - 64-character names; banned-word and RU gendered-ending greps.
- **Mini App (Vitest, also `TZ=UTC`):**
  - My schedule week −1, the claim button and chips, remove confirm;
  - the roster's search, deltas, Save, confirm all, 409 refetch;
  - RU at 320 px; `check:bundle`.
- **Owner on a phone:**
  - A student marks today's Mysore class, a teacher confirms it and marks two more people from the bot, and the counts show in the Mini App.
  - The student removes their mark.

## 8a. Changes from the build and the review (2026-11-09)
- **Names:** the staff PATCH body is `{present, removed, confirm_claims}` (was `absent`, ashtanga-expert: no "absence" even in the API). Staff counts on schedule rows are `attendance_counts`, because `attendance` already holds my own mark.
- **Staff writes** reject anyone who isn't a current member (student or staff) of the shala.
- **Bot:** the claimed/removed lines name the tapped row (`{ $what }`), so they edit in place with no read. The 🙋 list and the staff picker carry the zone line under the title (`schedule-zone`, or `my-schedule-zone-unknown` when my zone isn't known), like My schedule. The picker has `attend-staff-none`. Class titles and shala names render on one line, and new class titles are saved on one line, so the roster's counts line keeps its place.
- **Mini App:** removing my mark asks with `confirmDestructive`. The roster shows `attend-failed` for any failed save other than 409 (422, 5xx, offline) and keeps the ticks. "Confirm all" sends the pending ticks with it and then clears them. At 100 pending changes it asks to save first (`attend-save-first`). RU roster hint «Отметь посещение галочкой. 🙋 — собственная отметка.» (no past-tense verb).
- **Snapshot:** a re-claim or re-mark refreshes the snapshot columns, so a moved class shows its real time in the export.
- **Leaving vs a racing claim (accepted limit):** under READ COMMITTED a claim whose read predates a concurrent leave can insert after the leave's delete. Every read (roster people, counts, schedule counts, the PATCH tally) counts current members only, so such a stray row is never shown or counted; it goes with the account, or if the person rejoins it shows again as their own mark.
- **ICS feed:** the feed's window read skips the attendance subqueries (`member_windows(attendance=False)`).
- **Moon-day test:** on real Postgres, a claim and its confirmation on a Pranayama class held on a Purnima leave the student's day card, year stats (streak, GM-01 count) and 🌙 auto rest day equal.

## 9. Open questions for the owner (each with a recommendation)
- **Q180 Scope.** Recommend §1: claims, staff rosters with confirm-all, marks on My schedule, a 7-day window, no history screens (ST-08) and no pushes.
- **Q181 Who takes attendance.** Recommend **any staff seat**: owner, Manager, Teacher, Assistant and Front desk. Assistants run Mysore rooms, and the front desk checks people in. The alternative is the date's teacher plus `can_manage_schedule`.
- **Q182 States.** Recommend two states, `claimed` and `confirmed`. A staff mark or a staff member's own claim is confirmed at once. There's no "declined" or "absent" state; staff unmarking a claim removes it silently.
- **Q183 Relation to the log.** Recommend that attendance **never writes or reads the log**. After a claim, a `🧘 Log this day` button opens the existing day screen (my local date), and the student logs from there. Staff marks never touch the student's log. The rejected alternative auto-fills Practiced with Mysore/Led: it writes the student's private data on someone else's tap and can clash with a 🌸 or rest day (ADR-0039).
- **Q184 Window.** Recommend from the class start to today − 6 in the class zone, for both sides. No future marks and no cancelled classes. A class held on a moon day can be marked.
- **Q185 Removing your own mark.** Recommend that a student can remove their own row **any time**, confirmed included. It's silent and needs no confirmation from staff.
- **Q186 Leaving.** Recommend that leaving or being removed **deletes** that person's attendance at the shala, as ID-04's unlink does. Deleting the class keeps the rows (snapshot, `class_id` NULL), and deleting an account cascades.
- **Q187 "Practises here" (Q107/Q120).** Recommend it be **derived**, with no column. Any staff member can mark themselves, and staff with a row at the shala in the last 90 days appear on rosters, after the students. Staff and student stay exclusive seats.
- **Q188 Who sees attendance.** Recommend the person and that shala's staff only. Students see no counts or names, linked teachers who aren't on the staff see nothing, and no absence reason exists anywhere.
- **Q189 Notifications.** Recommend none. Pending 🙋 counts show on staff screens only.
- **Q190 Consent.** Recommend one bullet in `shala-join-consent` and one in `shala-staff-consent` (§2), with no re-consent for existing members, following PR-08 and NT-03.
- **Q191 Roster order and size.** Recommend claims first, then regulars (this class series in the last 28 days), then by name. The bot shows pages of 8; the Mini App has search and 50 per page.
- **Q192 Past rows.** Recommend that the Mini App's My schedule gains week −1, and the bot uses the `🙋 I was there…` list instead of a past week.
- **Q193 Export.** Recommend that your own rows go into your export with the shala name, and a staff member's export holds no rows of other people.
- **Q194 Words.** Recommend EN "🙋 I was there", "📋 Attendance", "✅ confirmed", "🙋 not confirmed yet"; RU «🙋 Отметиться», «📋 Посещаемость», «✅ подтверждено», «🙋 пока не подтверждено». Keep RU gender-neutral (no «был/была»). The ux-writer polishes these.
- **Q195 NT-03 attendees audience.** Recommend later (out of scope). The hook is "people with a row on this class in the last 28 days", read from `class_attendance`.
- **Q196 Log this day by type** (ashtanga-expert). Show `🧘 Log this day` only after Mysore, Led, 1:1, Workshop or Pranayama claims (Pranayama-only days are Practiced, decision #19). Hide it after Conference and Chanting, which are not asana practice.

**Owner, 2026-11-09:** Q180–Q196 all as recommended. Ashtanga-expert changes applied: "🙋 your mark" / «🙋 твоя отметка» replaces "not confirmed yet" (Q194); RU roster hint «🙋 — собственная отметка»; `attend-me-title` RU nit; a moon-day test; Q196. "Regulars" is a sort key only, never a visible label. **ST-08 note:** practice stats built on attendance must split by `class_type` (Conference and Chanting are not asana practice).

**For the ashtanga-expert:**
1. Mysore semantics: marking means "came during the window", with no arrival time and no practice length. Is that right for a Mysore room?
2. Led semantics, and whether Conference, Chanting and Pranayama should be "attendance" at all. The recommendation is yes, all types.
3. Moon days: held classes can be marked, while attendance stays out of streaks, counts and rest days.
4. Tone of "🙋 not confirmed yet", of the roster hint, and of silent removal (never a verdict).
5. Whether `🧘 Log this day` should preset the context (Mysore/Led). The recommendation is no for now, since it would couple attendance to the log flow.
6. The RU words in §2.
