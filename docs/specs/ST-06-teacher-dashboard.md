# ST-06: teacher dashboard

- Status: **accepted** (owner, 2026-11-07; ashtanga-expert fixes applied) · Date: 2026-11-07 · Size M, Phase 3
- Requirements: **ST-06** (students' activity today/week, progression overview, gentle). Touches ID-04 (the §11 handoff, one callback change in §5, one column in §7), PR-08 (Q13 closed here). Closes rows deferred to ST-06 from ST-09, PR-06, PR-07 and GM-01 (§9).
- Related: ADR-0016, 0020, 0022, 0023, 0026, 0030. New: **ADR-0031** (accepted). Fixed inputs: Q78, Q79, Q80, Q87, the ADR-0030 consent promises.

## 1. Scope
**In:** a read-only view for a person with students: a paged list (name and today's mark, the same in bot and app) and a student card (7 days with practice length, last asana, one quiet note). Policies, one new port, two use cases, two endpoints. Bot screens on the existing `t1:` list and card. A lazy Mini App screen and a neutral Home row. The copy that becomes false, a consent update for the quiet note, and one column recording that consent.
**Out:**
- **The "Teacher (opted in)" column.** There is no opt-in mechanism and none is built. ST-06 ships the default column only. Reasons: no requirement needs it beyond "unless shared"; it needs its own consent flow; and reading 🌸 needs the key, which would end the keyless teacher path (ADR-0031). It stays additive as `teacher_link` columns that die with the link.
- Stats of any kind for teachers: no run, consistency, count, heatmap or month view. **`domain/stats.py` is not reused:** consistency and runs depend on "No practice" versus unlogged, so any figure from them would reveal the difference that must stay hidden.
- `GIVEN` event timeline, milestones, teacher marks (PR-08), the Q79 reminder, the Q80 sick opt-in, any notification about inactivity, totals such as "N practiced today", filters, search, sorting by activity, a shala view, telling a teacher who is main.

**Departures from ID-04 §11, on purpose:**
- `can_view_*` get no link argument. They stay owner-only, and teachers get new, narrower policies (§3).
- ADR-0022's "project a logged rest on the day off exactly like an auto day off" no longer applies, because Q87 made auto days blank. A logged rest shows as rest. An unlogged day off is blank. No reason is exposed either way.
- ID-04 §11 and ADR-0030 say links are identifiable by `created_at`, so no consent-version column is kept. **That was wrong and is reversed here:** a consent screen stays tappable after a text change, so `created_at` can't show which text someone confirmed. Instead a boolean on `teacher_link` records it (§5, §7), the way §11 expected per-link opt-ins to work.

## 2. Flows
**Bot.** `/teachers` is unchanged, and `[👥 My students (12)]` still goes to `t1:s:<page>`. Each list button now reads `🧘 Anna` or `😌 Anna`, using the student's own today. **A blank today is the bare name**, so blanks carry no mark at all.
```
👥 My students (12)
Days follow each student's own time zone.
[🧘 Anna] [Dmitry] [😌 Maria] …  (one per row, 10 per page)
[◀] [▶]  [‹ Back]
```
Card (`t1:v:<id>:<page>`, edited in place):
```
Anna
Last asana, as marked in their log: Kapotasana (Intermediate)

Last 7 days
Today, Nov 7: 🧘 Practiced, Primary → Navasana
Yesterday, Nov 6: 😌 Rest day
Thu, Nov 5: ·
…
Not every day gets logged, rest days included. A blank says nothing about the practice.
Nothing shared for a while          (only when `quiet`)
[Remove…] [‹ Back]
```
- Dates come from `day_label` with the **student's** today, so "Today" means their today.
- All 7 days print, with `·` for every blank, so a blank day has one look. `·` is used only as the blank mark; the length follows a comma.
- **Last asana line:** carries the series. Standing only uses `students-last-standing`. A null position omits the line. Built from `PracticeLabels.stop` and `.series(lower=True)`, **not `position_text`**, which returns a practice length rather than an asana, and not `position`, which has no series. A stale series or key prints the raw value, as `length` does.

**Mini App.** Lazy `screens/teachers/Students.tsx` holds the list and the card in one chunk. The entries are a neutral Home row (`link-students-open`, no figures, only with at least one student, read from the shared `useLinks` after first paint) and a row in the Students part of `Links.tsx`. **List: name plus today's mark, the same as the bot,** with `[Show more]` (no infinite scroll). **The 7 days live on the card only.** Card: same content as the bot, with `Remove…` through the existing `confirmDestructive`. A 404 `not_linked` silently returns to the list and refetches, like the bot. Removal stays silent (ID-04 Q8).

**Order:** by name, then id, never by activity. A list sorted by activity is the "who hasn't practiced" list Q78 rules out.

**New copy** (⚑ = drafted here, ux-writer pass before release; the rest are the owner's or the expert's wording; «ты»; RU gender-neutral; names nominative; `учитель` and `ученик` per ID-04 Q15):

| Key | Where | EN | RU |
|---|---|---|---|
| `students-days-note` ⚑ | both | Days follow each student's own time zone. | Дни считаются по часовому поясу каждого ученика. |
| `students-week` ⚑ | both | Last 7 days | Последние 7 дней |
| `students-last-asana` | both | Last asana, as marked in their log: { $asana } ({ $series }) | Последняя асана по отметкам в журнале: { $asana } ({ $series } серия) |
| `students-last-standing` | both | As marked in their log: sun salutations and standing | По отметкам в журнале: Сурья Намаскар и стоячие |
| `students-blank-note` | both | Not every day gets logged, rest days included. A blank says nothing about the practice. | Не каждый день попадает в журнал, в том числе дни отдыха. Пустой день ничего не говорит о практике. |
| `students-quiet` | both | Nothing shared for a while | Какое-то время показать нечего |
| `students-mark` ⚑ | both | `{ $state -> [practiced] 🧘 *[rest] 😌 }` | same |
| `students-day` ⚑ | both | { $date }: { $state } | { $date }: { $state } |
| `students-day-length` ⚑ | both | { $date }: { $state }, { $length } | { $date }: { $state }, { $length } |
| `students-day-blank` ⚑ | both | bot: `{ $date }: ·` (app: `students-day-blank-mark`, the lint rule bans text in JSX); app `aria-label`: { $date }: nothing to show | bot: `{ $date }: ·`; app `aria-label`: { $date }: показать нечего |
| `students-more` ⚑ | app | Show more | Показать ещё |
| `students-card-load-failed` | app | Couldn't load this page. Try again in a moment. | Не получилось загрузить страницу. Попробуй ещё раз чуть позже. |
| `students-load-failed` ⚑ | app | Couldn't load your students. Try again in a moment. | Не получилось загрузить учеников. Попробуй ещё раз чуть позже. |

`$series` is `series-lower`, which already exists on both surfaces: EN "Intermediate", RU «вторая».

**Reused, by surface:**

| Purpose | Bot (`bot.ftl`) | App (`app.ftl`) |
|---|---|---|
| Day states | `status-practiced`, **`status-rest`** (must stay the exact word the private notes promise) | same keys |
| Length, series | `length-summary`, `series-lower` | same keys |
| Empty list, no name | `links-no-students`, `link-no-name` | same keys |
| Remove | `links-remove`, `link-remove-ask`, `links-remove-yes` | same keys, plus `delete-cancel` |
| List title | `links-students` | **add** `links-students` (same text) |
| Home row | not used | **add** `link-students-open` (same text as the bot) |
| Day label | `day-label` | **add** `day-label` (same text; `$date` from Intl) |
| Back | `log-back` | `stats-back` |
| Paging | `page-prev`, `page-next` | none: `students-more` |

No moon, 🌸, sick, travel or "No practice" key may appear on these screens.

**Copy re-checks flagged in ID-04:**

| Key | Verdict |
|---|---|
| `invite-consent` (bot) | **Replace.** "nothing more for now", "Later, when teachers get their own screen" and "then" all become false. Adds the quiet note and the "you log" wording. EN and RU below. Update the tests that pin the old text. Size test stays. |
| `settings-privacy-sharing` (app) | **Replace**, EN and RU below. |
| `export-readme-ladies` (bot) | **Keep.** "teachers see them as rest" is now literally true. |
| `settings-privacy-ladies` (app), `log-private-note` (bot), `today-private-note` (app, its twin, not listed in ID-04) | **Keep,** true only because the teacher's word is `status-rest` and period days show as rest (Q87). A test pins this. |
| `diary-private-hint`, `invite-share-text`, `delete-explain`, `/help`, `command-teachers` | **Keep.** No `set_webhook.py` run needed. |

`invite-consent` EN:
```
If you confirm:
• { $name } sees your name{ $me } and what you log from today on: practice or rest and your practice length.
• { $name } also sees your last asana as marked in your log.
• All rest you log looks the same, whatever the reason.
• If nothing shows for a while, { $name } sees a short note saying just that.
• Later, any teacher on your list will also be able to mark a new asana for you. You can undo it.
• Check-ins, diary notes and the reason for a rest stay private.
• You can remove { $name } from your list any time in /teachers. No one gets a message.
```
RU:
```
Если подтвердить:
• { $name } увидит твоё имя{ $me } и то, что ты отмечаешь с сегодняшнего дня: практика или отдых и объём практики.
• Ещё будет видна твоя последняя асана по отметкам в журнале.
• Любой отмеченный отдых выглядит одинаково, какой бы ни была причина.
• Если какое-то время показать нечего, { $name } увидит об этом короткую пометку.
• Позже любой учитель из твоего списка сможет отметить тебе новую асану. Это можно отменить.
• Самочувствие, заметки и причина отдыха остаются личными.
• Убрать из списка можно в любой момент в /teachers. Сообщений никто не получит.
```
`settings-privacy-sharing` EN: "Your log is yours. A teacher on your list sees your name, your last asana and what you log from the day you added them: practice or rest and your practice length. All rest you log looks the same, whatever the reason. If nothing shows for a while, your teacher sees a short note saying just that. Later, a teacher on your list will also be able to mark a new asana for you, and you can undo it. Check-ins, diary notes and the reason for a rest stay private. You can remove a teacher from your list any time."
RU: «Твой журнал принадлежит тебе. Учитель из твоего списка видит твоё имя, последнюю асану и то, что ты отмечаешь со дня добавления: практика или отдых и объём практики. Любой отмеченный отдых выглядит одинаково, какой бы ни была причина. Если какое-то время показать нечего, учитель увидит об этом короткую пометку. Позже учитель из твоего списка сможет отметить тебе новую асану, а ты сможешь это отменить. Самочувствие, заметки и причина отдыха остаются личными. Убрать учителя из списка можно в любой момент.»

The Settings line stays general: for a link confirmed under the older text it promises slightly more than happens, which is the safe direction.

## 3. Domain, policies, use cases, port
`domain/teacher_view.py` (pure):
```python
CARD_DAYS = 7; QUIET_DAYS = 21
class SharedDay(StrEnum): PRACTICED; REST        # blank = None. No other value exists.
SHARED: Mapping[DayStatus, SharedDay | None]     # exhaustive; moon, ladies, sick, travel, rest -> REST; skipped -> None
@dataclass(frozen=True, slots=True)
class StudentToday: id: UUID; name: str | None; today: SharedDay | None
@dataclass(frozen=True, slots=True)
class DayCell: date: date; shown: SharedDay | None; length: PracticeLength | None
@dataclass(frozen=True, slots=True)
class StudentCard: id: UUID; name: str | None; days: tuple[DayCell, ...]; last_asana: Position | None; quiet: bool
def card_days(shown, lengths, today: date) -> tuple[DayCell, ...]   # exactly 7, oldest first
def is_quiet(shown_dates: Collection[date], today: date, linked_on: date, agreed: bool) -> bool
```
**Structure, not hiding:** `SharedDay` has two members, no output type has a status, and neither has a zone, link date, milestones or context. `StudentToday` has no dates at all. The repository returns `SharedDay` from SQL, so `sick` or `moon` never becomes a Python value on this path. The adapter selects no sealed column and holds no cipher, like `db/notifications.py` today (ADR-0031). The student's `Account` is never loaded, so `last_seen_at`, `day_off`, `hide_ladies` and `moon_location` aren't in reach.

**Policies** (`application/policies.py`):
- New `can_view_activity(viewer, link)` and `can_view_last_asana(viewer, link)`: true when `link.teacher_id == viewer.id`. Rights are one hop, and the direction matters in a cycle.
- New `can_view_milestones(viewer, student)`: **owner only** (Q59). No teacher path calls it; a test pins False for a linked teacher.
- `can_view_check_ins`, `can_view_diary`, `can_view_progression`: **unchanged, owner-only.** The existing test at `test_teacher_links.py:451` stays. `can_view_progression` guards events and items, which teachers never get, so its docstring ("ST-06 adds linked teachers here") must be corrected.
- The SQL join is the first gate and the policy the second: a fake repository returning another teacher's row must raise `NotAllowed`.

**Port** `TeacherViewRepository` (`application/ports/teacher_view.py`, `Storage.teacher_view`):
```python
@dataclass(frozen=True, slots=True)
class StudentLink: teacher_id: UUID; student_id: UUID; name: str | None; timezone: str | None
                   locale: Locale; linked_on: date
@dataclass(frozen=True, slots=True)
class SharedLog: link: StudentLink; shown: Mapping[date, SharedDay]
@dataclass(frozen=True, slots=True)
class SharedPage: students: tuple[SharedLog, ...]; total: int
@dataclass(frozen=True, slots=True)
class SharedDetail: log: SharedLog; lengths: Mapping[date, PracticeLength]; position: Position | None
                    quiet_note_agreed: bool
class TeacherViewRepository(Protocol):
    async def page(self, teacher: UUID, offset: int, limit: int, since: date, until: date) -> SharedPage: ...
    async def student(self, teacher: UUID, student: UUID, since: date, until: date) -> SharedDetail | None: ...
```
`timezone`, `locale`, `linked_on` and `quiet_note_agreed` stop at the use case and appear in no output type. The flag is only on `SharedDetail`, so the list statement doesn't read it.

**Use cases** (`application/teacher_view.py`, both adapters, constructed with this port and `Clock` only, no `DayLogRepository`, no `ProgressionRepository`):
- `GetStudents.execute(principal, offset, limit) -> (students, total)`. Range `utc_today − 1 … utc_today + 1`, the three dates that can be someone's today on Earth. Then `today = local_today(now, zone or provisional_zone(locale))` per student and `shown.get(today)`.
- `GetStudent.execute(principal, student_id) -> StudentCard`, raises `NotLinked`. Range `utc_today − 21 … utc_today + 1`: a student's today is at least `utc_today − 1`, and `is_quiet` looks back 20 days from it. `card_days` and `is_quiet` then trim to the student's today.

**Query design** (one statement per call, built by one shared helper):
1. CTE `page`: `teacher_link` (index `teacher_id, student_id`) joined to `account`, listing only `display_name, timezone, locale`, plus `linked_on` and `count(*) OVER ()`. `ORDER BY lower(display_name) NULLS LAST, student_id LIMIT/OFFSET`. `student` uses the same CTE with `student_id = :id`.
2. CTE `shown`, a `UNION ALL` of:
   - `day_log` on PK range `local_date BETWEEN greatest(:since, linked_on) AND :until`, `status IN (…)`, with `CASE` giving only `practiced` or `rest`. The list and CASE come from `SHARED`, so a new status is excluded until mapped.
   - `rest_period` on PK range `start_date BETWEEN :since − 13 AND :until`, `generate_series` over the clipped dates (as the tick does), giving `rest`, **with `NOT EXISTS` on any `day_log` row for that date.** The 13 is the longest period (ADR-0023), not the read window, so it holds for both ranges.
3. `student` also selects `teacher_link.quiet_note_agreed` and left-joins `practice` (`series, end_item, first_part` only) and `progression` (`account_id, series, last_key` only). `account_id` is needed because NULLs alone can't separate "not set" (no row) from "standing only" (a row with NULLs).

**The `NOT EXISTS` is load-bearing.** "No practice" inside a period must stay blank (logged beats period, ADR-0023). Filtering `skipped` first and merging periods afterwards would turn it into rest. Doing the merge in SQL also means the read model never needs a value for "logged but blank", so "No practice" and unlogged are the same thing from the repository upward.

**`is_quiet`** (§6): `agreed`, `(today − linked_on).days >= 21`, and no shown date in `[today − 20, today]`.

**Writing the flag.** `_accept` in `db/teacher_links.py` is the only `INSERT` into `teacher_link`, and it adds `quiet_note_agreed = true` to its insert. That is correct because after this release `AcceptInvite` is reached only from `t1:a` (§5). `ON CONFLICT DO NOTHING` stays, so an existing row is never upgraded. The port and `Accepted` don't change.

## 4. API (initData; `{code}` errors; `Cache-Control: no-store`; `gen:api`)
| Method, path | Request → Response | Policy |
|---|---|---|
| `GET /api/v1/me/students` | `?offset=0&limit=20` (≤ 50) → `StudentsOut {students: [{id, name, today: "practiced" \| "rest" \| null}], total}` | `can_view_activity`; own links only, empty list with 0 students |
| `GET /api/v1/me/students/{id}` | → `StudentCardOut {id, name, days: [DayOut × 7], last_asana: PositionOut \| null, quiet}`; 404 `not_linked` | `can_view_activity`, `can_view_last_asana` |

`DayOut {date, state: "practiced" | "rest" | null, length: Length | null}`. `Length` and `PositionOut` are reused. **The list carries no dates, no `days` array and no `quiet`,** so a client can't filter it for a run of blanks. `last_asana` null = not set; `{series: null, last: null}` = standing only. An unknown id and an unlinked id give the same 404, so the route can't be used to test whether an account exists. No new `ErrorCode`. `GET /me/links` is unchanged. An `offset` past the end returns `students: []`, `total: 0`; the bot then re-reads page 0.

## 5. Bot and Mini App details
**Bot, reading.** No new prefix. `t1:s:<page>` and `t1:v:<id>` keep their meaning, and `t1:v:<id>:<page>` (≤ 46 bytes) lets Back return to the same page, while old buttons still decode. `LinkScreens.students` and `.student` call the new use cases; the Remove flow stays on `GetLinks`. Answer first, edit in place, no state. A forged, unlinked or just-removed id re-renders the list (as today).

**Bot, consent callback (changes ID-04).** Consent screens are stateless and stay tappable in a chat for as long as the message exists, so a ✅ tapped after release can come from a screen showing the old text. So:
- The new consent screen's ✅ is **`t1:a:<code>`** (same length; `a` is free). It does what `t1:y:<code>` does today, and the row it creates has `quiet_note_agreed = true`.
- **`t1:y:<code>` stops accepting.** It stays decodable, permanently, and goes through `LinkScreens.invited`: the consent with the current text, or `invite-already` if a link exists. It writes nothing, so it can't set the flag. The student taps ✅ once more on text they can read.
- `t1:l:<locale>:<code>` needs no change: it already re-renders.

**Every path that creates a link, checked:** only `_accept`, called only by `AcceptInvite`, called only by `LinkScreens.accept`, reached only by the `Confirm` tap. The Mini App has no confirm: it reads links and fetches an invite, and handles no `startapp` payload. The REST API has no accept route (`api/v1/links.py`, ID-04 Q12). A future accept endpoint must show the current consent itself; the default of false keeps it safe until then.

**Re-link:** a new row, so it takes its value from the consent shown then. Remove plus `t1:a` gives true, and that is the only way an older link can gain the note. `/start t_<code>` on an existing link shows `invite-already`, not the consent, and changes nothing.

**Mini App.** `useStudents(offset)` and `useStudent(id)` from the generated client, `staleTime` 60 s, dropped on `useRemoveStudent`. `useLinks` gains a 60 s `staleTime` for the Home row. Dates are formatted with `Intl.DateTimeFormat(locale, {timeZone: "UTC"})`, as Stats and Progression do, so a date can't shift with the teacher's device zone. The client computes no "today" (`days` arrive complete). One CSS class for every blank row. 320 px: names ellipsize. Marks and day rows have an `aria-label` from `status-*` or `students-day-blank`. Bundle: lazy chunk, initial JS unchanged but for the Home row; `check:bundle`.

## 6. Cross-cutting checks
**Time zones.**
- **A student's day is the student's.** Today = the student's current zone, or the provisional zone from their locale when unknown (the same rule as `GetDays`). Never the teacher's. Two rows of the list can mean different dates; `students-days-note` says so. `local_date` is shown as stored, never shifted.
- **Link boundary:** a plain date comparison `local_date >= linked_on` in SQL, with `linked_on` as stored. Never derived from `created_at`, never the teacher's zone. A day logged earlier on the link date shows ("from today on"). A later backfill before the link date never shows. Periods clip to it. A re-link moves it forward.
- **Moving west:** a stored date can pass the newly computed today, and `linked_on` can too. Such days wait until that date arrives; `is_quiet` is False while `today − linked_on < 21`.
- No time of day is shown, so no zone label is needed. `timezone` is never returned.

**Privacy.**
- **Projection table:** practiced → practiced. Logged rest, 🌸, moon, sick, travel, and every rest-period day ≤ the student's today → rest (Q87). "No practice", unlogged, auto moon, auto day off → blank (Q87). Last asana is current state, visible from the start. Length only on shown practiced days from the link date.
- **Future period days never appear,** so a teacher can't read a planned end date. The clip is in the domain because today is per student.
- **Quiet note: card only, one boolean, named in the consent.** It is computed **only from projected dates**, after all kinds have become `rest`. So:
  - Rest of any kind counts as a shown day, so 🌸, sick and travel behave identically. A rest period can't trigger the note: its days are shown, and the note needs 21 blank days after the last of them.
  - "No practice" counts as blank. This is required, not a side effect: if it counted as a shown day, a blank week without the note would prove someone tapped "No practice". The wording holds for both cases, since in each there is nothing to show.
  - Blank moon and day-off days aren't excused. Excusing them would need the student's settings and would let the note reveal them.
  - It counts only since the link. It has no number, no date and no sort.
  - 21 days is a judgement: ordinary two-week holidays and illness shouldn't trigger it.
  - **It needs `quiet_note_agreed`.** Links confirmed under the older text stay false and never get it (§5, §7). The flag itself never reaches a teacher: a card with no note says nothing about why.
- **What the list can and can't show.** Anyone reading the list, or a client filtering it, can see who is blank *today*. That is the accepted "today" view of ST-06, not a defect. Our screens add no sort, filter or count over it. The list can't show a run of blanks: it carries one state and no dates, and multi-day silence is only on the card, one student per request. We can't stop a teacher from keeping their own daily record or opening every card.
- **Accepted residual leaks:**
  - (a) **Ordinary rest is often blank** (auto days are blank, Q87, and many people don't log them). So 😌 skews toward rest someone logged deliberately, and a run of it on weekdays could hint at 🌸. The owner accepted this and kept Q87. The 7-day limit and `students-blank-note` soften it but don't remove it, and the consent now says "all rest you log".
  - (b) Card dates and the list's today flip at the student's midnight, so someone polling could estimate their UTC offset. Unavoidable while days stay the student's.
  - (c) A changed last asana is visible, including a step back (ID-04 §11).
- **Nothing about viewing is stored or logged.** No read receipts, no view history, no cache table.
- **Export:** `teacher_link` is exported (ID-04), through an explicit column list in `db/export.py`: `mine`, `primary`, `created_at`, shown as `teacher_links: [{other_side, primary, linked_at}]`. It isn't a `select(teacher_link)`, so the new column doesn't appear by itself. **Nothing changes:** the coverage guard is per table, the schema stays `/1`, and the flag stays out. It holds no personal content, and on a teacher's rows it would show which students confirmed which text.
- **Unlink, delete:** both remove the `teacher_link` row, and every read depends on that row in one snapshot. So the next tap gets 404 or the list, including last asana. No message, no trace. A re-link is a new row: it starts from the new date and takes the flag from the consent shown then. An app screen already open keeps what was already seen until its next fetch (≤ 60 s stale).
- **0 students:** no role check and no 403 (ID-03). `GET /me/students` returns an empty page, the bot shows `links-no-students`, the Home row is absent, and the `/teachers` invite label is as in ID-04.

**i18n.** All copy in `.ftl`, en/ru parity, in the teacher's locale. Names not declined. Asanas and lengths through `PracticeLabels`.

**Responsiveness** (statements include the 1 from the middleware or auth):

| Tap | Statements | Day rows at worst |
|---|---|---|
| `/teachers` | 2, unchanged | none (≤ 520 names) |
| Student list, bot | 2 (3 only on a stale page) | 10 × 3 |
| Student card, bot | 2 | 23 |
| `GET /me/students` | 2 | 50 × 3 |
| `GET /me/students/{id}` | 2 | 23 |

Independent of list size: a 500-student teacher pays for one page of day rows plus a ≤ 500-row sort. Target < 300 ms p50 warm. Measure with 500 seeded students before calling it done.

## 7. Migration, release and ops
**Migration `0020_quiet_note_agreed`** (expand-only, down `0019`): `ALTER TABLE teacher_link ADD COLUMN quiet_note_agreed boolean NOT NULL DEFAULT false`, plus the column in `tables.py` with `server_default=text("false")`. No backfill: **existing rows stay false, so those links never get the note.** A constant default on Postgres 11+ doesn't rewrite the table, and the lock is brief. Table grants cover the new column. Downgrade drops it. No new index: `teacher_link (teacher_id, student_id)`, `day_log` PK, `rest_period` PK, `practice` PK and `progression` PK cover every read, and a DB test confirms with `EXPLAIN` on the seeded 500.

**One release, and the rollover is safe in both directions.** `backend.yml` runs the `migrate` step before `deploy` in one job, with the same image, and a failed migration stops the deploy. So the column always exists before the new image serves.

| During the rollover | What happens |
|---|---|
| Old image inserts a link | Its insert names `student_id, teacher_id, linked_on`, so the column takes the default: **false.** Correct, since that image shows the old text. |
| Old image reads `teacher_link` | It selects named columns and doesn't notice the new one. |
| Old revision gets `t1:y` | Accepts, flag false. Correct. |
| Old revision gets a `t1:a` from a new screen | Doesn't decode, so nothing happens. The student taps again. |
| New revision gets `t1:y` | Re-renders the consent. Nothing written. |

**A rollback needs no special step:** the column stays, an older image writes false, and a false row only means no note. Order of Mini App and backend deploys doesn't matter, because consent lives only in the bot.

**Other:** import-linter gains one rule: `infrastructure.db.teacher_view` and `application.teacher_view` may not import `infrastructure.crypto`, `ports.days` or `ports.progression`. No new setting and no `set_webhook.py` run.

**☁️ Owner steps:** none in production; migration 0020 runs in CI on deploy. Locally, the dev DB needs `uv run tristhana-migrate` once, as usual.

## 8. Test plan
- **Domain:** `SHARED` covers every `DayStatus`; `card_days` returns 7 oldest first, ends on today, drops later dates, handles month and year ends. **`is_quiet`:** 20 days since the link False, 21 True; last shown day 20 days ago False, 21 True; `linked_on` after today False; rest only False; **`agreed` False hides the note in a case that is otherwise True.**
- **Use case, fakes:** Kiritimati and Honolulu on one instant get their own today; both read ranges cover them; provisional zone; teacher's zone never used; a foreign row from the fake → `NotAllowed`; `None` → `NotLinked`; output types carry no zone, link date or flag. **Policies:** teacher yes, third party no, co-student no, the teacher's teacher no, reversed direction no; `can_view_milestones`, `can_view_check_ins`, `can_view_diary`, `can_view_progression` False for a linked teacher.
- **DB, real Postgres, privacy leaks first:**
  - **Kind matrix:** logged rest, 🌸, moon, sick, travel, and 🌸/sick/travel periods all give `rest`; **output is deep-equal when any kind is swapped for another.**
  - **Blank matrix:** "No practice", unlogged, auto moon and auto day off give blank; **output is deep-equal between 21 days of "No practice" and 21 days of nothing, `quiet` included,** with the flag true so the note is really in play.
  - **"No practice" inside a period stays blank.** Practiced inside a period stays practiced.
  - **A 14-day period:** no note during it, none 20 days after its last day, note at 21.
  - **The flag:** two students identical but for `quiet_note_agreed`, 21 blank days each: false gives `quiet` False, true gives True, and everything else is deep-equal.
  - **Writing it:** `accept` stores true; a duplicate accept on a false row leaves it false; unlink plus accept gives a new row with true.
  - **Migration 0020:** a row seeded at 0019 is false after upgrade; an insert naming only the old columns, as the old image does, gets false; up/down/up; `alembic check`. **Export:** `teacher_links` keys are unchanged, on both sides, and the flag is nowhere in `data.json`.
  - Future days of a current period are absent. Days before `linked_on` are absent, for logs, periods and backfills. A re-link hides the earlier link's days.
  - **Compiled SQL contains none of:** `sealed_status`, `sealed_kind`, `last_seen_at`, `context`, `online`, `duration_min`, `start_time`, `items`, `hint_`, `marked_by`, `is_primary`, `progression_event`, `check_in`, `diary`, `practice_milestone`. The rule still holds with the new column. The card statement may name `quiet_note_agreed`; the list statement must not.
  - **Runs with no cipher configured** (`MissingCipher`).
  - Statement counts per §6; paging is stable and independent of activity; unlink and account delete remove the student at once; app role (`test_db_app_role.py`); `EXPLAIN` on 500 students.
- **API:** 401; exact key sets, recursively, for both responses and in OpenAPI; **list item keys are exactly `id, name, today`, so no date, `days`, `quiet` or `last_asana`**; `quiet_note_agreed` in neither response nor OpenAPI; state enum is exactly two values plus null; unknown id, unlinked id and reverse-direction id give the same 404 body; a 0-student account gets 200 and an empty list; `limit` over 50 is 422; `no-store`; TS client builds.
- **Bot, through the webhook:**
  - List marks; blank is the bare name; a blank day reads the same for "No practice" and unlogged; card text in both locales; **no 🌙 🌸 🤒 ✈️ 🌱 and no `status-moon/ladies/sick/travel/skipped` output**; no main-teacher word; quiet only on the card.
  - **Last asana:** series in the line in both locales; standing-only line; **null position omits the line**; a stale key stays readable.
  - **Consent:** the new screen's ✅ is `t1:a:<code>`, which creates the link; **`t1:y:<code>` creates no link, can't set the flag, and shows the current text with a `t1:a` button**; on an existing link it shows `invite-already` and leaves the flag false; the language switch keeps `t1:a`. Update `test_teacher_links_bot.py`, which pins `t1:y`.
  - Back keeps the page; old `t1:v:<id>` decodes; forged and removed ids re-render the list; `answered` before the work; every callback ≤ 64 bytes; card ≤ 4096 with 64-character names.
- **Mini App, Vitest (also `TZ=UTC`):** Home row only with students, and no figure in it; list shows name and mark only; card shows 7 days; one class for all blanks; Show more; 404 returns to the list; Remove drops the cache; dates don't shift by zone; last-asana line variants; RU at 320 px; `check:bundle`.
- **i18n/architecture:** ftl parity, including the keys added to `app.ftl`; RU avoid-word and gendered-ending greps; old `invite-consent` and `settings-privacy-sharing` sentences gone, including "unless you choose"; the quiet sentence is in both; consent ≤ 4096; **the teacher's rest label equals what `log-private-note`, `today-private-note` and `settings-privacy-ladies` quote**; import-linter.
- **Owner on a phone:** RU narrow width, a real student in another zone across their midnight.

## 9. Decisions (owner, 2026-11-07; all as recommended, with these refinements)
1. **Mini App list:** name plus today's mark, the same as the bot. The 7 days live on the card only. The list API returns today's state alone.
2. **Quiet note:** kept, on the card only, one boolean, at 21 days, a judgement that ordinary two-week holidays and illness shouldn't trigger it. Wording "Nothing shared for a while" / «Какое-то время показать нечего», softening Q78's phrase.
3. **Consent for the note:** named in `invite-consent` and `settings-privacy-sharing`. A link gets the note only with **`teacher_link.quiet_note_agreed`**, set by the new ✅ alone (`t1:a`). Migration 0020 leaves existing rows false, so those links never get it. One release. This reverses ID-04's "no consent-version column", because `created_at` can't identify consent, and follows ID-04 §11's "per-link opt-ins become columns on `teacher_link`".
4. **No launch message:** already-linked students confirmed everything else they will see, and the note is suppressed for them.
5. **Q87 kept, side effect accepted:** rest-period days show as rest, unlogged auto days are blank, and `students-blank-note` explains blanks on the card.
6. **Q79:** no reminder about old visiting-teacher links during beta. Students see their teacher list and can remove anyone. Revisit after beta.
7. **Q80:** no sick or injury opt-in; they show as plain rest.
8. **Consent wording:** "All rest you log looks the same" / «Любой отмеченный отдых выглядит одинаково». This changes the Q82 wording.
9. **Progression:** current position only, no given-asana history. **Supersedes PR-08 spec row 13.** "Progression overview" in ST-06 means the last asana. `GIVEN` events would need new consent or ST-04's own decision.
10. **"Unless you choose to share them":** dropped from the consent and Settings. It described a control that doesn't exist. Dropping it shares nothing new, and a later opt-in would be the student's own explicit act.
11. **Opt-in:** the "Teacher (opted in)" column isn't built.
12. **History:** 7 days only, no month view, no teacher stats. A longer view would make monthly rest patterns readable. The consent would allow growing it later.
13. **Home row:** neutral, no figures, for teachers with at least one student. Closes ID-04 Q12.
14. **Time zone hint:** dates flipping at the student's midnight is accepted. The real zone is never returned.
15. **Policies:** new `can_view_activity`, `can_view_last_asana`; `can_view_milestones` owner-only (Q59); existing `can_view_*` stay owner-only.

**Rows deferred to ST-06:**
- **ST-09 row 10 ("🌸 as rest" export variant):** not built, and not needed by this feature: the teacher view projects 🌸 by itself, and no one shares an export through it. Stays deferred with no target; the honest `export-readme-ladies` line stays.
- **PR-06 decision (6) (check-in opt-in, scope mood vs body tags):** no opt-in, so check-ins stay hidden and the scope question moves to any later opt-in feature. "Never show check-in missing" holds, because this path reads nothing about check-ins.
- **PR-07 decision (8), spec row 9 (per-entry diary sharing):** not built. Notes stay owner-only, and this path never selects `diary_note`.
- **GM-01 decision (12) (count milestones):** decided: hidden from teachers, by `can_view_milestones` and by the read model having no field for them.

**For notes-keeper (not this spec):** Q59, Q78, Q79, Q80, Q87 outcomes; the `05 Domain Model` table; the `06 Time Zones` checklist; a pointer from ADR-0020, ADR-0022 and ADR-0030 to ADR-0031. Stale code comments to fix in the build: `policies.py`, `application/stats.py`, `application/teacher_links.py`, `api/v1/links.py`, `Links.tsx` ("names only"); `teacher_links_callbacks.py` (the `t1:y` line).
