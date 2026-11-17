# ID-07: one link for shala and teacher (the student asks, the teacher confirms)

- Status: **accepted** (owner, 2026-11-17: Q317–Q322 in §11 all as recommended, "All yes"; Q323 as recommended: M, Phase 3, before the public launch; the design in §1 is the owner's decision of 2026-11-16, Q305/Q308) · Size **M** · Phase 3, built after UI-06 stages 1, 2 and 4A
- Requirements: **ID-07** (new). Touches ID-04 (a second way a link comes to exist), ID-03, SC-01 (join flow, card), ST-06 (history boundary), MD-02, NT-02, ST-09, UI-05, UI-06 (Today, Menu, layered consent). PR-08 marks and NT-03 announcements begin at the approval, as for any link.
- Related: ADR-0008, 0018, 0027, 0030, 0031, 0032, 0033, 0038, 0045. New, accepted: **ADR-0046** (teacher requests: a pending row in its own table).

## 1. Scope
**The problem.** A student who joins by the shala link shares nothing; for a teacher to follow them, the teacher must also send a personal link and the student must confirm again. Owners expect one link.
**Decided (owner, not reopened here):** the shala link stays the only thing an owner shares · after joining, one screen asks who the student's teacher is · the tap on a name is the student's consent and sends a request · **the teacher must say yes; nothing from the log is visible to anyone before that** · a "no" and 7 days of silence look the same to the student · only the shala's **Teacher** role can be picked · the teacher sees days from the date the student asked · the personal link `t_` is unchanged, with no approval step.
**In:** table `teacher_request`; the question screen after `h1:a`; the same screen from the shala card (for people who joined earlier or tapped "Not now"); the teacher's note, waiting list, "Confirm all", "Not my student" with Undo; the student's waiting line and Withdraw; two closing notes sent by the tick; limits; export and delete; the Mini App parts in §2.
**Out:** a teacher starting this for students already in the shala (owner) · asking from the Mini App, and the Shala-tab placement (UI-06 stage 4) · any view of requests for owners, managers or other staff (Q322) · the ID-05 directory line on the question screen · a block list · a broadcast to existing members · a notification toggle for the two closing notes (one message per request the person made themselves).
**Unchanged:** `teacher_link`, the teacher read path and every `can_view_*` policy. A request is not a link: no reader of `teacher_link` learns it exists. SC-01's "joining a shala creates no teacher link" stays true.

## 2. Flows and copy
**Life of a request** (`ANSWER_WITHIN` = 7 days, `KEEP` = 30 days, both counted on `created_at`, UTC):

| Event | Row | The teacher | The student |
|---|---|---|---|
| Student taps a name | insert, `waiting` | one silent note; in the waiting list | Today with `request-asked`; "waiting" line on the card |
| Teacher: "Yes, my student" (within 7 d) | `approved` + `teacher_link` insert, **one statement** | student is on the list | quiet `request-confirmed`, next tick (≤ 10 min) |
| Teacher: "Not my student" | `declined` | leaves the list; Undo until day 7 | **nothing changes**; at day 7 the gentle note |
| 7 days, no answer | unchanged (read-time rule) | leaves the list | the gentle note, **in the same tick as a declined one would be** |
| Student withdraws | `withdrawn` | leaves the list, no message | line gone |
| Student leaves, is removed or becomes staff | unchanged, no longer valid | leaves the list | nothing, no note |
| Teacher loses the Teacher role, leaves or is removed | unchanged, no longer valid | leaves the list | still "waiting", then the gentle note |
| The two link by the personal link meanwhile | unchanged; the link wins in every read | "already your student" | linked by that tap; no note |
| Either removes that link later | `unlink` also sets `withdrawn` | | an old "Yes" can never bring back a removed link |
| Shala deleted, either account deleted | cascade | old buttons: `request-gone` | line gone, no note |
| 30 days after the ask | pruned by the tick | | may ask this teacher again (Q317) |

"Valid" = the student's `shala_student` row and the teacher's `shala_staff` row both exist, both older than the request, and the staff row has `teacher` in `roles`. It is a join in every read and in the approve statement, so nothing has to be cleaned up when a membership changes, and a leave-and-rejoin never revives an old request.

**Student (bot).** `h1:a:<code>` joins as today. If the shala then has at least one teacher to offer (Teacher role, not linked to me, no request row for the pair), the reply is the question instead of the card:
```
request-ask ("Who is your teacher here?")      one teacher: request-ask-one ("Is {name} your teacher?")
request-consent-short · request-until-yes · request-know-them
[Anna] [Boris] …                               one teacher: [request-yes]
[Details] [Not now]
```
- A name (or Yes) = consent + request → **Today** (UI-06 T0) with `request-asked`. "Not now" → the shala card, as a join ends today. "Details" → the full `request-consent` with the same name buttons and `consent-short-back`.
- No teacher to offer → the card, as today. Owners and managers see `request-no-teachers-hint` on their card when nobody holds the Teacher role.
- **Shala card, student side:** row `request-open` (same screen) while someone can be asked; one `request-waiting-line` per waiting request, each with `request-withdraw` (one confirm step). This is the path for members who joined before ID-07. No Menu change: the Menu renders from the account alone (UI-06).
- Refusals are one lead line on Today: `invite-already` (linked), `request-waiting` (asked, waiting), `request-recent` (asked in the last 30 days), `request-too-many`, `request-full`.

**Teacher (bot).** The note, sent at the student's tap, always silent:
```
request-note ("{student} from {shala} says you're their teacher. Confirm only if you know them.")
[Yes, my student] [Not my student]
[See all (N)]            (N ≥ 2)
```
- Yes → edited to `link-student-joined` + `[👥 My students]`. No → edited to `request-declined` ("the student isn't told") + `[Undo]`.
- **Waiting list** `t1:rl:<page>`: `request-list-title`, `request-list-hint`, 10 rows of `{student} · {shala}` (each opens the note's screen), `[Confirm all (N)]` → one confirm step naming N → `request-all-done`. Reached from the note, from a row on "My students" (`t1:s`, also when the list is empty), and from the teacher's shala card (`request-waiting-open`), each shown only while N > 0.
- **Confirm all carries the moment the list was drawn** (in the list's own button, `t1:rc:<unix>`, and unchanged through the confirm step, whose count is who was waiting at that moment) and approves only requests made before it, so someone who asked a second later is never confirmed unseen. The moment is whole seconds, rounded down, compared strictly: a request made in the list's own second stays waiting and is on the next list. It never touches declined ones.

**Student, closing notes (tick, silent):** `request-confirmed` (+ `[⭐ Make main]` when it is not their first teacher, as ID-04) · `request-no-answer` ("No answer from {name} yet. Ask them in class, or pick another teacher.") + `request-pick-another` → the question screen of that shala.

**Mini App, ships with ID-07:** teacher: a "Waiting (N)" block on the Students screen with Confirm, Not my student (Undo), Confirm all (native confirm). Student: waiting lines with Withdraw in the Teachers card of `Links`. The Shala tab's students card has a row "Waiting for your answer (N)" that opens that block. Undo in the app lasts until the screen is left (the bot's until day 7). **Waits:** asking from the app (the consent text stays in one place, the bot, as ID-04 Q12) and the move into the Shala tab → UI-06 stage 4; a "students are waiting" next-step card on Today → stage 2.

**Copy keys** (en + ru, intent only; ux-writer writes, ashtanga-expert checks). RU: «учитель» for the person asked, «Преподаватель» only as the shala role (SC-01 glossary); names nominative; no word for "declined" anywhere on the student's side.
- **`bot.ftl`, student:** `request-ask`, `request-ask-one`, `request-yes`, `request-consent-short` (what the teacher will see: the ADR-0045 item table of `invite-consent-short`, so it follows Q312), `request-until-yes` (nothing is shown until they confirm; they get one message with your name), `request-know-them`, `request-consent` (the full text, §3), `request-asked`, `request-waiting`, `request-recent`, `request-too-many`, `request-full`, `request-open`, `request-waiting-line`, `request-withdraw` / `-ask` / `-yes` (the ask says this teacher can't be asked again here for a while), `request-withdrawn`, `request-confirmed`, `request-no-answer`, `request-pick-another`.
- **`bot.ftl`, teacher:** `request-note`, `request-yes-mine`, `request-not-mine`, `request-see-all`, `request-declined`, `request-undo`, `request-gone` (one line for every reason, with the way out: your own link), `request-already-student`, `request-list-full`, `request-list-title` (Fluent plural), `request-list-hint`, `request-list-empty`, `request-all` / `-ask` / `-yes` / `-done`, `request-waiting-open`, `request-no-teachers-hint`, `export-readme-requests`.
- **`app.ftl`:** the waiting-list and waiting-line keys above, `request-load-failed`.
- **Reused:** `invite-decline`, `consent-details`, `consent-short-back`, `invite-already`, `link-student-joined`, `link-students-open`, `links-make-main`, `link-no-name`, `page-prev/next`, `log-back`. **Unchanged on purpose:** `shala-join-consent` (joining alone still shares nothing), `shala-staff-consent` (staff names and roles were already visible to members), `invite-consent`. **To check:** `delete-explain`, `staff/create-shala`'s sentence in the guide.

## 3. Domain, use cases, ports
`domain/teacher_requests.py` (pure):
```python
ANSWER_WITHIN = timedelta(days=7); KEEP = timedelta(days=30)
MAX_ASKING = 3      # a student's asks in any 7 days, all shalas (counts_as_asked)
MAX_WAITING = 100   # waiting requests per teacher
class RequestState(StrEnum): WAITING, DECLINED, WITHDRAWN, APPROVED          # stored
class AskState(StrEnum): CREATED, LINKED, WAITING, RECENT, TOO_MANY, FULL
class Closing(StrEnum): CONFIRMED, NO_ANSWER
def waiting_for_student(state, created_at, now) -> bool   # WAITING or DECLINED, inside the 7 days
def waiting_for_teacher(state, created_at, now) -> bool   # WAITING only, inside the 7 days
def answerable(state, created_at, now) -> bool            # WAITING or DECLINED, inside the 7 days
def closing_due(state, created_at, linked, now) -> Closing | None
def request_key(id: UUID) -> str                          # "req:<id>", the ledger's dedupe key
```
- **One projection for the student.** Everything the student can observe goes through `waiting_for_student`, which treats `DECLINED` as `WAITING`: the card, the question screen, `MAX_ASKING`, the API, the export, and the note's due time. A decline therefore frees no slot and moves no clock. The teacher's side uses `waiting_for_teacher`.
- **Limits (soft, like ID-04's).** At the ask: mine asked < 3, counting every request I made in the last 7 days in any state but `approved` (waiting, declined and withdrawn alike, so a withdrawal frees no slot; an approved one is a link and counts with the teachers); theirs waiting < 100; my teachers + mine waiting < `MAX_TEACHERS`; their students + theirs waiting < `MAX_STUDENTS`. At the approval both link caps are checked again; when full, the request stays waiting (`request-list-full`). One row per pair for 30 days, however it ended, so one student costs one teacher **at most one message a month** and at most three teachers a week. Shala caps are untouched: a request needs an existing membership, which `MAX_STUDENTS` (1000) and `MAX_STUDENT_OF` (5) already bound. The remedy for a persistent stranger is SC-01's: staff remove them and rotate the link.
- **Consent record.** The tap agrees to `request-consent`, a full text with **the same data items and rights as `invite-consent`** in "the teacher you pick" wording, plus three request lines: nothing is visible until they confirm; counted from today even if they confirm some days later; you can withdraw before, remove after. A test pins that the two texts name the same items (ADR-0045). The row stores `quiet_note_agreed` from the screen that was tapped; **the approval copies it and never sets it** (ADR-0031: a later consent column on `teacher_link` gets a twin here and a new callback letter).
- **The link born from a request:** `linked_on = asked_on` (the student's local date at the ask), `created_at = now()` at the approval, `is_primary = false`. So history starts at the ask; the order of teachers, the default main teacher and "joined before the announcement" (NT-03) follow the moment the link came to exist. The quiet note needs 21 days from `linked_on`, so it cannot appear at an approval.
- **Moon (MD-02, ADR-0032/0033).** No write and **no Keep offer**: an approver is always on a shala's staff, and never-chose staff follow their shala with or without students, so their first student flips nothing (`moon_follow` returns before `teaches` is read). The student's city can move in two cases only, both already promised: a never-chose member of an older second shala whose first teacher this is (Q108: "if your teacher teaches here, the shala's calendar comes first", in the join consent), and a stored "Follow my teacher" with no teacher before. Both are changes made by another person's tap, so they are silent and shown in labels and reminders (ADR-0032). A domain test pins that these are the only two.

**Port `TeacherRequestRepository`** (`Storage.teacher_requests`), one statement each: `choices(shala, me, now)` (teachers to offer + my waiting ones; None = not a student there) · `card(shala, me, now)` (the shala card's side read: `choices` for a student, the waiting count for a teacher of it, one statement for either) · `ask(shala, me, teacher, asked_on, agreed, caps, now)` (guarded insert; an existing row older than `KEEP` is recycled by `ON CONFLICT … DO UPDATE … WHERE`, so the rule does not depend on the prune; returns the state and the teacher's name, locale, Telegram id and waiting count) · `withdraw(me, teacher)` · `mine(me, now)` (my waiting requests + how many wait for me) · `waiting(me, now, offset, limit, student?, before?)` (`before`: only who asked before that moment, for Confirm all's count) · `approve(me, student, caps, now)` · `approve_all(me, before, caps, now)` (oldest first, as many as fit) · `decline(me, student, now)` · `reopen(me, student, now)` · `due(now, limit)` · `prune(before)`. `TeacherLinkRepository.unlink` gains one CTE (close the pair's request).

**Use cases** (`application/teacher_requests.py`; both adapters except `GetTeacherChoices` and `AskTeacher`, bot only for now): `GetTeacherChoices`, `AskTeacher` (computes `asked_on` with `caller_today`; then `Notifier.tell_teacher_asked`, direct, silent, 3 s, no retry: the list is the record), `WithdrawRequest`, `GetMyRequests`, `GetWaitingRequests`, `ApproveRequest`, `ApproveAllRequests`, `DeclineRequest`, `ReopenRequest`. `RunTick` gains `_close_requests` after `_announce` (claim → deliver → finish, category `request`, new `Notification` member `RequestClosed`), and the prune.

**Policies** (`application/policies.py`): `can_ask_teacher(actor: Membership | None, target: Membership | None)` = actor is a student there and target is staff with `ShalaRole.TEACHER` (an owner counts only with that role; assistants, managers and front desk never) · `can_answer_request(actor, teacher_id)` = the asked teacher alone, not the owner or a manager · `can_withdraw_request(actor, student_id)` = the asker. The SQL guards mirror them (`Guarded`); a non-member gets `NotFound`. **A test pins that a waiting or declined request grants nothing:** the student is absent from `GET /me/students`, the card is `not_linked`, no mark, no announcement, no moon effect.

## 4. API (initData; `{code}` errors; `no-store`; `gen:api`)
| Method, path | Request → Response | Policy |
|---|---|---|
| `GET /api/v1/me/links` | += `asked: [{teacher_id, name, shala: {id, name}}]` (waiting only, projected), `waiting: int` | own |
| `DELETE /api/v1/me/teacher-requests/{teacher_id}` | → 204, idempotent | `can_withdraw_request` |
| `GET /api/v1/me/student-requests` | `?offset&limit≤50` → `{requests: [{student_id, name, shala: {id, name}}], total, as_of}` | `can_answer_request` |
| `POST /api/v1/me/student-requests/{student_id}/approve` | → 204; 404 `request_gone`; 409 `list_full` | same |
| `POST …/{student_id}/decline` · `…/reopen` | → 204 (decline idempotent); 404 `request_gone`, also for an already-linked pair (a "no" never removes a link) | same |
| `POST /api/v1/me/student-requests/approve-all` | `{as_of}` → `{approved, left}` | same |

No state field, no date and no `declined` anywhere in a student-facing schema. `ErrorCode` += `request_gone`, `list_full`. No ask route yet (§2).

## 5. Bot (answer first, edit in place; ≤ 51 bytes)
| Data | Meaning |
|---|---|
| `h1:t:<shala>` · `h1:td:<shala>` · `h1:tn:<shala>` | question · details · not now (the card) |
| `h1:ta:<shala>:<acct>` | **the consent tap**: ask this teacher |
| `h1:tw:<shala>:<acct>` · `h1:tx:<shala>:<acct>` | withdraw: ask · do |
| `t1:ra:<uuid>` · `t1:rn:<uuid>` · `t1:ru:<uuid>` · `t1:rv:<uuid>` | yes · not my student · undo · one request's screen |
| `t1:rl:<page>` · `t1:rc:<unix seconds>` · `t1:rcy:<unix seconds>` | waiting list · confirm-all ask · confirm all asked before that moment (both carry the moment the list was drawn; a bare `t1:rc` only draws the list) |

An id in callback data is no capability: every write is keyed on the caller. **Stale buttons** (a note stays in the chat for good):

| Tap | State now | Reply |
|---|---|---|
| Yes | waiting, or declined inside the 7 days | the link; `link-student-joined` |
| Yes / No | already linked (personal link, or a double tap) | `request-already-student`; "No" never removes a link |
| Yes / No / Undo / a list row | expired, withdrawn, a membership or the role gone, shala or account deleted, pruned | **`request-gone`, the same line for all**, + `[➕ Invite students]` |
| Yes | a cap is reached | `request-list-full`; the request stays |
| Confirm all | the list changed since | confirms only what is still waiting and was asked before its moment; the count is in the reply |
| a name on an old question screen | left the shala · linked · asked already | the teachers screen · `invite-already` · `request-waiting` / `request-recent` |
| Withdraw | confirmed meanwhile | `invite-already` (remove is on the teacher card) |

## 6. Migration and ops
**`0029_teacher_requests`** (expand-only; down `0028`, UI-06's `welcomed_at`; renumber if that order changes):
- `teacher_request(id uuid NOT NULL DEFAULT gen_random_uuid() UNIQUE, student_id uuid NOT NULL → account ON DELETE CASCADE, teacher_id uuid NOT NULL → account ON DELETE CASCADE, shala_id uuid NOT NULL → shala ON DELETE CASCADE, state text NOT NULL DEFAULT 'waiting' CHECK IN ('waiting','declined','withdrawn','approved'), asked_on date NOT NULL, quiet_note_agreed boolean NOT NULL, created_at timestamptz NOT NULL DEFAULT now())`, **PK `(student_id, teacher_id)`**, CHECK `student_id <> teacher_id`; indexes `(teacher_id, created_at) WHERE state = 'waiting'`, `(teacher_id)` (plain: the teacher's delete cascade and export), `(shala_id)`, `(created_at)`. `op.f()` names. No backfill.
- `notification_delivery_category_check` += `'request'` (the 0005 / 0024 drop-and-recreate; downgrade deletes those rows first).
- **Delete (ADR-0027):** still one `DELETE FROM account`; three cascade paths reach the table (student, teacher, an owner's shala), none needs a trigger. `is_account_gone` learns `teacher_request_student_id_fkey`. In `approve`, a 23503 on `teacher_link_student_id_fkey` means the **student** vanished mid-tap: the repository catches it inside the connection block and returns "gone", or `is_account_gone` would report the teacher's own account as deleted.
- **Export (ST-09):** `teacher_request` joins `EXPORTED_TABLES` as `teacher_requests: [{other_side: "teacher" | "student", asked_on, state}]`. On my rows as the student, `state` is `waiting` / `no_answer` / `confirmed` / `withdrawn` through the projection, **never declined**; as the teacher, `waiting` / `declined` / `confirmed` / `closed`. No name, id or shala of the other person (ID-04 Q14).
- **Ops:** none in the cloud. Notes on acceptance (not done here): "Amended by ADR-0046" lines in ADR-0030, 0031 and 0033; the ID-07 row and priority in `02 Requirements.md` (Q323); `05 Domain Model.md`; SC-01's deferred "shortcut" item.

## 7. Cross-cutting checks
- **Time zones ✔.** `asked_on` is the student's local date at the tap (provisional zone if none, as ID-04), stored and never recomputed, so a zone change before the approval moves nothing. The 7 and 30 days are durations on a UTC instant, not local days. No time of day is shown anywhere, so no zone label. The gentle note falls due at the same wall-clock time as the ask a week before; it is silent in any case.
- **Privacy ✔, who learns what:**
  - *Link holder, before joining:* the shala's name and city, no person (SC-01, unchanged). **The teacher list appears only after joining**, and shows nothing the member's card does not already show.
  - *Student:* never that a request was declined, that a teacher's queue is full (`request-full` says only "not right now"), or how many others asked.
  - *Teacher, on a request:* a name they could already see as staff, plus the one new fact the student chose to send: "I say you are my teacher". Never whether the student asked someone else, has other teachers, or why a request closed (`request-gone` is one line).
  - *Owner, managers, other staff, co-students:* nothing. There is no list of who asked whom.
  - *Before the yes:* no `teacher_link` row exists, and the teacher read path joins that table (ADR-0031), so the promise is structural. *After it:* up to 7 days of days already logged become visible at once; the consent says "from today".
  - *Timing:* both silent outcomes become due at `created_at + 7 d` and go out in the same tick; a structural test swaps `declined` for `waiting` and expects equal output on every student surface. A declined student therefore waits the full week (the price of an honest "same").
  - *At rest:* `declined` is plain in the row for at most 30 days; nothing sealed is involved. Names are plain text (no `parse_mode`).
- **Notifications (NT-02) ✔.** All three messages are silent, so quiet hours need no zone maths and nothing is held (ADR-0038's rule). The closing notes skip the daily cap but their ledger rows count toward it. The teacher's note is direct and outside the ledger, as ID-04's join note; a full room means one silent message per student, bounded by `MAX_WAITING`.
- **i18n ✔.** Every string in `.ftl`, en + ru parity; the teacher's note in the teacher's language, the rest in the student's; Fluent plurals for counts; names never declined.
- **Responsiveness ✔** (statements after the middleware's one; the account load is untouched):

| Tap | Statements | Outbound |
|---|---|---|
| ✅ Join | 2 (join, choices) | none |
| A name / Yes on the question | 2 (ask, Today's read) | 1 silent send, ≤ 3 s |
| Details, back, withdraw ask | 1 | none |
| Shala card (student or teacher: one read serves either), My students (teacher) | +1, in parallel | none |
| Yes · Not my student · Undo · list page · Confirm all | 1 | **none** (the student's note is the tick's) |
| Tick | +1 due read, 2 per note, +1 prune | ≤ 500 notes a run |

## 8. Tests to write first
- **Domain:** the three predicates on both sides of the 7-day boundary; **every student-facing function gives equal results for `WAITING` and `DECLINED`**; `closing_due` (confirmed at once, no answer at day 7 exactly, nothing when linked, withdrawn or approved-then-unlinked); `AskState` for every cap; `moon_follow` unchanged for an approver in every staff row of the rule table, and the two student cases of §3.
- **Use case, fakes:** ask stores the student's local `asked_on` (Kiritimati vs Honolulu, provisional zone) and notifies once; a double tap notifies once; a failed send still succeeds; approve creates the link with `linked_on = asked_on`, the stored `quiet_note_agreed`, a fresh `created_at`; decline then approve works inside the window and not after; Confirm all skips declined, later-than-moment and over-cap rows; unlink closes the request; every policy as a role × action matrix (assistant, manager, front desk and an owner without the Teacher role can't be asked; an owner can't answer for a teacher); **no use case here reads `day_log`, `practice` or `progression`** (import-linter).
- **DB (real Postgres):** CHECKs and the PK; one statement per call (§7); approve is atomic under two concurrent taps (one link, one `approved`); approve vs withdraw, and approve vs the personal-link accept, end in one consistent state; validity joins (leave and rejoin, role removed and returned, student turned staff); recycling a row older than 30 days; cascades for student, teacher, shala and owner delete in **one statement**; the 23503 mapping in `approve` with a concurrent student delete; **with a waiting request the teacher-view statements return nothing for that student**; `due` returns a declined and a silent request in the same run and neither a second time; 0029 up/down/up; `alembic check`; app role; export: no `declined` on the student's side, no other person's name or id.
- **API:** 401; exact key sets (no state, no date on student-facing schemas); 404 `request_gone` identical for every reason; 409 `list_full`; `approve-all` honours `as_of`; a foreign id touches nothing; OpenAPI → TS client builds.
- **Bot (through the webhook):** join → question in en and ru, one-teacher and several-teacher forms, nobody to offer → the card; linked and already-asked teachers are not offered; Details and back; a name → Today with the line, the teacher's note silent and in the teacher's language; "See all" only from two; every row of the stale table; `request-gone` byte-identical across reasons; Undo; Confirm all with a late arrival left waiting; closing notes rendered silent, `[⭐ Make main]` only from the second teacher; short and full consent ≤ 4096 with 64-character names; the item table (ADR-0045) for `request-consent-short` and `request-consent` vs `invite-consent`; every callback ≤ 64 bytes, forged ids only re-render, `answered` first; the pre-UI-06 frozen callback list still passes.
- **Tick:** a note is claimed once across two runs; blocked marks unreachable; a request whose student left gets no note; `stopped_early` leaves the rest.
- **Mini App (Vitest, also `TZ=UTC`):** waiting block per state, Confirm, Not my student + Undo, Confirm all confirm step, 404 refetch, student's waiting line and Withdraw, RU at 320 px, `check:bundle` (initial JS unchanged).
- **i18n:** parity; no student-side key or RU string contains a word for refusal («отклон», «отказ», "declined", "rejected"); avoid-word and gendered-ending greps.
- **Owner on a phone:** join by QR from a second account, pick, confirm from the first; "Not my student" then wait for the note on a shortened clock in dev.

## 9. Guides and screenshots (`/guide-update ID-07`)
- **Pages, each with its `ru/` twin:** `students/my-shala` (the question after joining), `students/my-teacher` (asking, waiting, withdrawing, the "no answer yet" note), `teachers/invite-students` (two ways: the shala link plus your yes, or your own link), `teachers/what-you-see` (days from the date the student asked), `staff/create-shala` (replaces "a teacher shares their own link"; the Teacher role is what makes someone pickable), `reference/privacy`, `reference/faq`, `reference/whats-new`. `features:` gains `ID-07`.
- **Screenshots (en + ru):** new `bot-ask-teacher`, `bot-request-note`, `bot-requests`, `app-requests`; re-shot `bot-shala` and `bot-students` (the waiting row). The demo data gains one waiting request.

## 10. What waits
- **UI-06 stage 2:** a next-step card on Today for a teacher with people waiting. **Stage 4:** the waiting list and the student's waiting line move into the Shala tab; asking from the app, with the consent texts in `app.ftl` under the same item-table test.
- **Later, if the beta shows a need:** a teacher-started request for existing members (owner: out of scope), a block list (ADR-0030), the directory line beside a name on the question screen.

## 11. Questions for the owner
- **Q317. How soon may a student ask the same teacher again** after a quiet "no", a week of silence or their own withdrawal? It must be one rule for all three, or the student could tell them apart. **Recommended: 30 days.** Alternatives: 7 days (a declined stranger can ask weekly), or never (no way back after a mis-tap except the teacher's own link).
- **Q318. After the 7 days, can the teacher still say yes from the old message?** **Recommended: no.** The request is closed, the button says so and offers the teacher's own link; a consent is then never more than a week old and never reaches back more than 7 days. Alternative: answerable for the whole 30 days, which fits "no answer *yet*" better but lets a month of days appear at once.
- **Q319. Limits.** **Recommended: 3 waiting requests per student, 100 waiting per teacher**; the existing 20-teacher and 500-student caps count waiting ones too.
- **Q320. Undo for "Not my student".** **Recommended: yes, until day 7** (the student never saw anything, so nothing has to be taken back). Without it, a mis-tap silently costs a real student a month.
- **Q321. Mini App in this release.** **Recommended: the teacher's waiting list with answers, and the student's waiting line with Withdraw; asking from the app waits for stage 4**, so the consent text lives in one place. Alternative: bot only, and the app shows nothing until stage 4.
- **Q322. Does the shala's owner or a manager see who is waiting on which teacher?** **Recommended: no one but the two people.** A list would tell the owner which student picked whom.
- **Q323. Priority of ID-07** (not set in `02 Requirements.md`). **Recommended: M, Phase 3, before the public launch.**
