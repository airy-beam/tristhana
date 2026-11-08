# PR-08 Phase 3: a linked teacher marks a new asana for a student

- Status: **accepted** (owner, 2026-11-08: Q2 changed to "the next ~3 stops", all others as recommended; ashtanga-expert copy fixes applied) · Size S–M, Phase 3
- Requirements: **PR-08** ("…or the teacher marks for the student"). Touches **ST-06** (the student card is the entry point), **ID-04** (the consent promise, §251, Q86), **GM-01 part 1** (the student's celebration), **ST-09** (export, delete), **NT-01/02** (the student's message), **ST-04** (later timeline).
- Related: ADR-0008, 0012, 0026, 0030, 0031. New: **ADR-0037** (one of the next three stops, the CAS also checks the position, undo of a teacher's mark until the position moves on, one silent note; accepted).

## 1. Scope
**In:**
- On the ST-06 student card (bot and Mini App), a linked teacher picks a new asana from **the next three stops** after the student's position, then confirms once.
- The pick is one `given` event, so the student gets **one** silent bot message with the celebration and `[↩︎ Undo]`.
- The student's My asanas shows who marked it, and the student can undo a teacher's mark until the position moves on (Q86).
- The consent and Settings copy say "Later" today; that word is dropped.
- An unset student's card gets a neutral line.

**Who:** any person on the student's list of teachers, including an assistant whom the student added. Being on the list is the whole rule (Q1).

**Out:**
- Going further than three stops, set or ✏️ Change, marking back, starting an unset record, milestone items (Q3), backdating, and a teacher undoing their own mark (Q5).
- Shala staff who aren't on the student's list. A "marked by you" label (Q10). Showing the teacher any history, `changed`/undo event or celebration detail. Bulk marking. ST-04 timelines. An NT-01 toggle.

**Tone:** a teacher's mark reads as a gift, never a verdict. Undo is offered as fixing the record in the bot ("if this doesn't match your practice"), never as anyone's mistake. The banned-word list of PR-08 §7 applies to every new key.

## 2. Domain (pure, `domain/progression.py`)
```python
TEACHER_STEPS = 3
class Marker(StrEnum): SELF, TEACHER            # TEACHER also covers marked_by NULL (deleted account)
ProgressionEvent += by: Marker, by_name: str | None   # name only while linked; marked_by_self stays as a property
def teacher_targets(track, progression) -> tuple[Position, ...]
    # up to 3 stops after the position, in catalog order, across a series boundary; () if unset or stale
def teacher_change(track, progression, seen: Position, target: Position, on) -> Change
    # NotForward unless position == seen and target in teacher_targets; one GIVEN with before = seen
def undoable(events: Sequence[ProgressionEvent]) -> frozenset[int]
    # the newest event, plus every TEACHER `given` with no newer START/GIVEN/CHANGED (newer item events are fine)
def teacher_mark(events) -> ProgressionEvent | None   # the event that set the current position, if a TEACHER `given`
```
- **Stops:** stop points, as in PR-08. `teacher_targets` is the first three of `Track.after`'s order, but across a series boundary: Setu Bandhasana → Pasasana, Krounchasana, Salabhasana B. So "Intermediate begins" can be a teacher's mark. From standing only, the targets are the first three Primary stops. Close to the end of the confirmed series there are fewer.
- **Celebrations:** the existing `celebrations(track, earlier, change)`, unchanged. A multi-stop pick carries `first`, which gives the "New asanas: X → Y" line, and series lines appear for any stop in the range. A pick ending at a stop held before gets the quiet line (PR-08 Q3). The result goes to the student only.
- **`occurred_on`** = the **student's** local today (their zone, or the provisional zone from their locale), never the teacher's. **A late mark** (given in Monday's class, marked on Wednesday) lands on Wednesday. If that matters to the student, they adjust it with ✏️ Change. Teachers can't backdate.
- **Undo** restores the event's `from`, so undoing a three-stop pick goes back to where it started.

## 3. Application
- **Policy** `can_mark_progression(actor: Account, link: MarkLink) -> bool`: `link.teacher_id == actor.id`. Rights go one hop and one way, as `can_view_last_asana`. The SQL guard (§4) is the first gate and the policy the second; a fake that returns another teacher's link must raise `NotAllowed`. `can_view_progression` and `can_view_milestones` stay owner-only.
- **`MarkForStudent.execute(principal, student_id, seen, target) -> Marked(seen, target)`** in a new `application/teacher_marks.py`. It is built with `ProgressionRepository`, `Track`, `Clock` and `Notifier` only.
  1. `for_teacher(teacher, student)` returns `MarkLink` and `ProgressionView` in one statement. None → `NotLinked`.
  2. The policy check, then `teacher_change(...)`. If the position is no longer `seen`, or the target isn't among the next three → `ProgressionChanged` (the card was out of date).
  3. `apply(student, change, expected=last_event_id, before=seen, marked_by=teacher, link_teacher=teacher)`. None → `ProgressionChanged`.
  4. `notifier.tell_asana_marked(recipient, teacher_name, AsanaMarked(event.id, celebrations, target))`. A `BLOCKED` or `FAILED` result is ignored, as for the join note.
  5. Returns only `Marked(seen, target)`, with no celebrations, events, items or delivery status. The teacher then re-reads the card with `GetStudent`.
- **`GetStudent`**: `StudentCard` += `next_asanas: tuple[Position, ...]` = `teacher_targets`. `Track` is injected (in memory; no new port). The read model is otherwise unchanged, and the ST-06 compiled-SQL ban list still holds.
- **`UndoProgression`**: same signature, wider rule (ADR-0037); `NotLatest` when it can't be undone. **`GetProgression`**: the events carry `by`, `by_name` and `undoable`.

## 4. Ports and infrastructure (`infrastructure/db/progression.py`)
- `for_teacher(teacher, student) -> TeacherMarkView | None`: a CTE on `teacher_link` (PK), joined to the student's `account` (`timezone`, `locale` only) and `identity` (Telegram id), then the `get` select for that student. One statement.
- `apply(…, before: Position | None, link_teacher: UUID | None = None)`. The upsert's `WHERE` adds `(series, last_key) IS NOT DISTINCT FROM (:before)`, which every caller now passes. `link_teacher` gates the source with `EXISTS (teacher_link WHERE student_id = :account AND teacher_id = :teacher)`.
- `undo(account_id, event_id) -> bool`, still one statement. The `DELETE … WHERE` becomes `id = last_event_id OR (kind = 'given' AND marked_by IS DISTINCT FROM :account AND NOT EXISTS (a newer position-kind event))`.
  - Latest: the current restore logic.
  - Not latest: `series`/`last_key` := `from_*`; `items` and `last_event_id` kept; `hint_*` := NULL.
- `get`: the events gain `by` (`CASE marked_by WHEN :me …`) and `by_name`, from `LEFT JOIN teacher_link ON (student_id = :me, teacher_id = marked_by)` plus `account.display_name`. A teacher who was removed or deleted reads "a teacher". Still one statement.
- `Notifier.tell_asana_marked(recipient, teacher, mark) -> DeliveryResult`: one silent direct message (`disable_notification=True`, 3 s timeout), in the student's locale. It stays outside the ledger and the cap, with no retry (the ID-04 Q11 pattern; silence covers quiet hours).
- **No migration.** Kinds, columns, FKs (`marked_by … ON DELETE SET NULL`), the index `(account_id, id DESC)` and the grants already exist.

## 5. API (initData; `{code}` errors; `no-store` on teacher routes; regenerate with `gen:api`; additive)
| Method, path | Request → Response | Policy |
|---|---|---|
| `GET /api/v1/me/students/{id}` | `StudentCardOut` += `next_asanas: [PositionOut]` (0–3, in order) | unchanged |
| `POST /api/v1/me/students/{id}/new-asana` | `{from: PositionOut, to: PositionOut}` (`from` = the card's `last_asana`, `to` = one of `next_asanas`) → 200 `StudentCardOut` (refreshed). 404 `not_linked`. 409 `progression_changed` (out of date, or a lost CAS: refetch). 422 `invalid_progression` (not a stop, or not within the next three of `from`) | `can_mark_progression` |
| `GET /api/v1/me/progression` | `EventOut` += `by: "self" \| "teacher"`, `by_name: str \| null`, `undoable: bool`. `ProgressionOut` += `marked: {event_id, by_name, undoable} \| null` | own |
| `DELETE /api/v1/me/progression/events/{id}` | as now; the wider rule; 409 `not_latest` = can't be undone now | own |

No new `ErrorCode`. Unknown, unlinked and reversed ids give the same 404. A retried POST hits 409, and the card refetches.

## 6. Bot (answer first, edit in place, stateless; every value ≤ 64 bytes)
A position in callback data is `<n>:<i>`: the series number, then the stop's index in that series, with `0:0` = standing only. A key doesn't fit beside a uuid: `triang-mukhaikapada-paschimottanasana` is 37 bytes. `<k>` (1–3) is the number of steps from `<n>:<i>`.

| Data | Meaning | Longest |
|---|---|---|
| `t1:g:<uuid>:<page>` | open the picker (reads the card) | 46 |
| `t1:gp:<uuid>:<n>:<i>:<k>:<page>` | picked → the confirm screen | 54 |
| `t1:gy:<uuid>:<n>:<i>:<k>:<page>` | confirm and mark | **54** = 6 + 36 + `:6:99` 5 + `:3` 2 + `:9999` 5 |
| `g1:u:<event_id>` · `g1:o` | (existing) undo · My asanas, on the student's message | 24 |

- **Teacher card (`t1:v`):**
  - With targets, `[🎉 Mark new asana]` (`students-give`) sits above `[Remove…]`.
  - Unset: `students-give-unset` replaces the last-asana line, with no button. At the end of the confirmed series there is no button either.
- **Picker (`t1:g`):** `students-give-pick`, then one button per target in order: `[Supta Vajrasana]`, `[→ Bakasana B]`, `[→ Bharadvajasana]` (`students-give-option` / `-range`; owner, 2026-11-08: a range button names only its last stop, and the confirm names the whole range), then `[‹ Back]` to the card at its page.
- **Confirm (`t1:gp`):** `students-give-ask`, or `-range` for several stops, naming the student and the asana(s). Then `[🎉 Yes, mark]` and `[‹ Back]` to the picker.
- **Mark (`t1:gy`):**
  - Success: the card with `students-given` (or `-range`) on top.
  - `ProgressionChanged`, or a position that no longer resolves: the card with `students-give-stale`.
  - `NotLinked`: the list.
  - The server re-derives the target from `(n, i) + k` against the current catalog and checks `seen` itself, so a forged value can only fail.
- **The student's message:**
  - Text: `mark-received` (one stop), `mark-received-range` (several) or `mark-received-back` (held before), then any `celebrate-series-*` lines, then `mark-received-undo-hint`.
  - Buttons: `[↩︎ Undo]` and `[🧘 My asanas]`. Undo edits it into G with `progression-undone`. If the mark has been moved on from: G with `progression-mark-moved-on`.
- **G screen:** with `teacher_mark(events)`, `progression-marked-by` goes under `progression-current`, plus `[↩︎ Undo]` if undoable.
- **Statements** (the middleware counts 1):
  - Card, picker, confirm screen: 2 each.
  - Mark: 4, plus 1 silent send (≤ 3 s timeout).
  - The student's Undo: 2 + G's read.
  - G: 2, unchanged.

## 7. Mini App
- **`Students.tsx` card:**
  - `🎉 Mark new asana` opens an inline list of `next_asanas`, laid out like the bot picker.
  - A pick opens a native `showConfirm` (a new non-destructive `confirmAction` beside `confirmDestructive`) with `students-give-ask` / `-range`.
  - The POST sends `{from: last_asana, to}`. It is not optimistic; the response replaces the cached card, and `students-given` shows as `role="status"` with a light haptic.
  - 409 → refetch + `students-give-stale`; 404 → the list.
  - Unset → `students-give-unset`.
- **`Progression.tsx`:** teacher entries get `progression-event-by`; Undo shows on every `undoable` entry; the current line gets `progression-marked-by` from `marked`; 409 `not_latest` → refetch + `progression-mark-moved-on`.
- Both go into chunks that are already lazy, ≈ +0.6 KB gzip, with no dependency. Run `check:bundle`; check RU at 320 px (range buttons wrap).

## 8. Copy (⚑ = drafts for a ux-writer pass; the `mark-received*` keys and `students-give-stale` are the ashtanga-expert's wording; «ты»; RU gender-neutral; names nominative; asana and series names from the catalog)
| Key | EN | RU |
|---|---|---|
| `students-give` ⚑ | 🎉 Mark new asana | 🎉 Отметить новую асану |
| `students-give-pick` | { $name }: which new asana? { $name } gets one message, even for a few. | { $name }: какая новая асана? { $name } получит одно сообщение, даже если асан несколько. |
| `students-give-option` / `-range` | { $asana } / → { $asana } | same |
| `students-give-ask` ⚑ | { $name }: the next asana is { $asana } ({ $series }). Mark it as new? { $name } gets a message from the bot and can undo it. | { $name }: следующая асана — { $asana } ({ $series } серия). Отметить как новую? { $name } получит сообщение от бота и сможет отменить отметку. |
| `students-give-ask-range` ⚑ | { $name }: new asanas { $from } → { $asana } ({ $series }). Mark them? { $name } gets one message from the bot and can undo it. | { $name }: новые асаны — { $from } → { $asana } ({ $series } серия). Отметить? { $name } получит одно сообщение от бота и сможет отменить отметку. |
| `students-give-ask-across` | { $name }: new asanas { $from } ({ $from_series }) → { $asana } ({ $series }). Mark them? { $name } gets one message from the bot and can undo it. | { $name }: новые асаны — { $from } ({ $from_series } серия) → { $asana } ({ $series } серия). Отметить? { $name } получит одно сообщение от бота и сможет отменить отметку. |
| `students-give-yes` ⚑ | 🎉 Yes, mark | 🎉 Да, отметить |
| `students-given` / `-range` ⚑ | ✅ Marked: { $asana }. / ✅ Marked: { $from } → { $asana }. | ✅ Отмечено: { $asana }. / ✅ Отмечено: { $from } → { $asana }. |
| `students-give-stale` | This card was out of date, so nothing was marked. Here it is now. | Карточка устарела, поэтому ничего не отмечено. Вот актуальная. |
| `students-give-unset` ⚑ | { $name } hasn't set their practice yet. | { $name }: практика пока не указана. |
| `mark-received` | 🎉 New asana: { $asana }. Enjoy it! Marked by { $teacher }. | 🎉 Новая асана: { $asana }. Приятного знакомства! Отметка: { $teacher }. |
| `mark-received-range` ⚑ | 🎉 New asanas: { $from } → { $asana }. Enjoy them! Marked by { $teacher }. | 🎉 Новые асаны: { $from } → { $asana }. Приятного знакомства! Отметка: { $teacher }. |
| `mark-received-back` | { $asana } is in your practice. Marked by { $teacher }. | { $asana } — в твоей практике. Отметка: { $teacher }. |
| `mark-received-undo-hint` | If this doesn't match your practice, you can undo it. | Если это не совпадает с твоей практикой, отметку можно отменить. |
| `progression-marked-by` ⚑ | Marked by { $teacher } | Отметка: { $teacher } |
| `progression-event-by` ⚑ | · { $teacher } | · { $teacher } |
| `progression-by-teacher` ⚑ | a teacher | учитель |
| `progression-mark-moved-on` | Your practice has changed since this mark, so nothing was undone. To set where it ends now, use ✏️ Change. | С этой отметки практика уже изменилась, поэтому ничего не отменено. Чтобы указать, где она заканчивается сейчас, нажми ✏️ Изменить. |
| `progression-undo-mark` (bot only) | ↩︎ Undo the mark | ↩︎ Отменить отметку |
| `progression-undo-entry` (Mini App only, the Undo's `aria-label`) | ↩︎ Undo: { $entry } | ↩︎ Отменить: { $entry } |

- `$teacher` falls back to `progression-by-teacher`; `$name` to `link-no-name`.
- In `-range` keys, `$series` is the target's series. A range can cross a series boundary (Urdhva Mukha Paschimottanasana → pick 3 = Setu Bandhasana → Krounchasana; Mukta Hasta Sirsasana C → pick 3 = Baddha Hasta Sirsasana D → Visvamitrasana). Then the confirm uses `students-give-ask-across`, naming both series (owner, 2026-11-08). `$from_series` is the first new stop's series.
- The `students-give-*` keys don't clash with the existing `students-mark` day-state key.
- Reused: `progression-undo`, `progression-undone`, `celebrate-series-*`, `log-back`, `series-lower`.
- **Replace** ("Later" is false now; no new exposure, so no new consent column, ST-06 §5):
  - `invite-consent` bullet 5: "Any teacher on your list can also mark a new asana for you. You get a message and can undo it." / «Любой учитель из твоего списка может отметить тебе новую асану. Придёт сообщение, и отметку можно отменить.»
  - `settings-privacy-sharing`, the same sentence: "A teacher on your list can also mark a new asana for you: you get a message and can undo it." / «Учитель из твоего списка также может отметить тебе новую асану: придёт сообщение, и отметку можно отменить.»
  - Update the pinned tests and the 4096 size test.

## 9. Cross-cutting checks
- **Time zones:** `occurred_on` = the student's local today, including for a late mark (§2). Tests: Kiritimati vs Honolulu on one instant; the provisional zone. No time is shown, so no zone label. `created_at` is UTC and audit only.
- **Privacy:**
  - A teacher learns only the position they already see and their own mark. The reply is byte-identical whether the student celebrated or not, whether the message was delivered, and whatever items or `changed` events exist.
  - The picker derives from the shown position only. `Marked` carries `seen` and the target only.
  - Accepted residual: an undo or change by the student shows on the card as a different last asana (ST-06 residual c).
  - The unset line reveals nothing new: ST-06 already omits the last-asana line when unset.
  - The student sees the teacher's name only while linked. Nothing about a mark is logged beyond account uuids.
- **Export (ST-09):** no change. Marks export as `given` with `marked_by: "teacher"`, and a deleted account reads `"unknown"`. No other person's name or id appears. A teacher's own export holds none of the marks they made.
- **Delete:** a teacher's deletion NULLs `marked_by`; the mark still counts as a teacher's and stays undoable. A student's deletion cascades.
- **i18n:** en/ru parity. The student's message uses the student's locale; the teacher's screens use the teacher's.
- **Responsiveness:** §6. Target < 300 ms p50 warm, server-side with the send stubbed, measured with 500 seeded students.

## 10. Test plan
- **Domain:**
  - `teacher_targets`:
    - standing only → the first 3 Primary stops;
    - mid-series → 3;
    - Setu Bandhasana → Pasasana, Krounchasana, Salabhasana B;
    - near the end of the confirmed series → fewer;
    - at the end, unset or stale → ().
  - `teacher_change` refuses: `seen` ≠ the position, equal or earlier stops, a 4th stop, a non-stop.
  - A 3-stop pick is one `GIVEN` with `before = seen`, and its celebration carries `first` ("New asanas: X → Y"). A range crossing into Intermediate adds `SERIES_COMPLETE` and `SERIES_BEGINS`. A pick ending at a stop held before → no celebration.
  - `undoable`:
    - always the newest event;
    - a teacher's given followed only by items → yes;
    - followed by a change, a give or another teacher's give → no;
    - a self given that isn't newest → no;
    - `marked_by` NULL → teacher.
  - Undoing a 3-stop pick restores `from`.
- **Application (fakes, fixed clock):**
  - **Policies:** teacher yes (an assistant on the list too); the student themself, a third party, a co-student, the teacher's teacher, the reversed direction and unlinked shala staff no. A foreign link → `NotAllowed`.
  - **Flow:** unlinked → `NotLinked`; stale `seen` or a target out of range → `ProgressionChanged`; a lost CAS → `ProgressionChanged` and nothing sent; success sends exactly one note in the student's locale.
  - **Leaks:** `BLOCKED`/`FAILED` still succeed. **`Marked` is deep-equal across first time vs held before, and delivered vs blocked.** `occurred_on` is the student's today.
- **DB (real Postgres):**
  - `for_teacher` = 1 statement; None when unlinked or reversed.
  - Concurrency: a teacher mark and a student give at once → one event. Two teachers picking at once → one event. A mark and an unlink at once → a mark with the link, or nothing.
  - Undo: retract with later items restores `from`, keeps items and `last_event_id`, clears the hint; refuses after a later change. After a retract, a stale item write → None, and a later real give celebrates.
  - `by`/`by_name` (name gone after unlink, NULL after deletion). App role (`test_db_app_role.py`): mark and retract.
  - Export: no teacher id or name. `alembic check`.
- **API:** 401; POST 200/404/409/422 (a `to` outside the three is 422; `from` ≠ current is 409); the same 404 body for unknown, unlinked and reversed ids; `next_asanas` length 0–3 and in order; the new `EventOut`/`marked` fields; DELETE of a retractable non-latest event 200, of a moved-on one 409; `no-store`; OpenAPI and the TS client build.
- **Bot (through the webhook, fake use cases):**
  - The button only with targets; the unset line.
  - Picker → confirm → mark, edited in place, with Back keeping the page. Range buttons and range copy. The stale line on a changed position or catalog. Unlinked → list. `answered` before the work.
  - The student's message in both locales: single, range and back variants, both buttons, Undo, the moved-on line. G shows `progression-marked-by` with Undo.
  - **The longest `t1:gp`/`t1:gy` = 54 bytes (uuid, n = 6, i = 99, k = 3, page = 9999), asserted ≤ 64.** Malformed values or k ∉ 1–3 re-render.
  - Banned-word and RU gendered-ending greps.
- **Mini App (Vitest, also `TZ=UTC`):** the picker lists `next_asanas`; confirm and cancel; success replaces the card; 409 refetch with the stale line; the unset line; history entries "· Anna" and "· a teacher"; Undo on a non-newest teacher entry; old payloads render; RU 320 px; `check:bundle`.
- **Architecture:** import-linter (`application.teacher_marks` imports no crypto; aiogram stays in `bots/telegram`; ST-06 rules unchanged).

## 11. Decisions (owner, 2026-11-08; Q2 changed, the rest as recommended)
1. **Who can mark:** anyone on the student's list of teachers, an assistant included. Shala staff without a link can't (ADR-0033).
2. **What (changed by the owner):**
   - The teacher picks from the **next three stops** in catalog order, across a series boundary.
   - The pick is **one** `given` with `from` and one message ("New asanas: X → Y" for several).
   - No more than three, no marking back, no start, no items, no backdating.
   - The confirm names the student and the asana(s).
3. **Milestone items:** not by teachers now (Q59, the consent, the button would reveal state); revisit with ST-04.
4. **Confirm step:** yes, naming the student and the asana(s).
5. **Teacher undo:** no; the student undoes.
6. **Q86:** a teacher's mark is undoable until the position moves on (later items are fine). Undo restores `from` and leaves no trace; after that, ✏️ Change (ADR-0037).
7. **The student's own marks:** latest-only undo, unchanged.
8. **Telling the student:** one silent direct message, always, with Undo; no ledger, cap, NT-01 toggle or retry.
9. **Wording:** the colon form "… Marked by { $teacher }." / «Отметка: { $teacher }», which works with the "a teacher" fallback. The undo hint says it changes only the record in the bot. The stale line points at the card, not the student (ashtanga-expert).
10. **What the teacher sees:** "✅ Marked: …" plus the refreshed card. No "marked by you", no celebration, no delivery status.
11. **The teacher's name in the student's history:** while linked, otherwise "a teacher".
12. **Unset student:** no button, plus a neutral line on the card.
13. **Consent and Settings:** drop "Later", add "you get a message"; no re-consent.
14. **No cap** on marks or messages; revisit with beta feedback.
15. **Deleted teacher:** marks stay, read "a teacher" (`unknown` in the export) and stay undoable.

**Open, for the ux-writer (not blocking):** all ⚑ keys above, in particular the RU `students-give-pick` and the RU range button length at 320 px.

## 12. Build deviations
1. **Malformed `t1:gp`/`t1:gy`** (k ∉ 1–3, a non-digit, n > 6, `0:<i ≠ 0>`, a page of 5+ digits, missing or extra parts) only stop the spinner and change nothing, as every malformed `t1:` value. §10 said "re-render". A well-formed value that no longer resolves (`6:99`, an index past the series' end) shows the card with `students-give-stale`.
2. **`apply(…, *, before, link_teacher=None)`**: `before` is keyword-only and required. `None` means only "no stored row" (a START); the upsert then never overwrites an existing row.
3. **The link guard locks the link row** (`FOR KEY SHARE` in a CTE inside the EXISTS), not a plain EXISTS: an unlink racing the mark either waits for its commit or wins. So "a mark with the link, or nothing" holds strictly. Needs UPDATE on `teacher_link`, which the app role has (app-role test).
4. **The non-latest undo also requires the current position** (read under `FOR UPDATE`, so the newest row version) **to equal the mark's `to`**, so a give or change committing between the snapshot and the lock can't be overwritten.
5. **The confirm screen (`t1:gp`) re-checks the card it reads**: a changed position, or k beyond the card's targets, shows the card with the stale line (§6 defined it for `t1:gy` only).
6. **Wiring**: `MarkForStudent` is `LinkUseCases.mark` (bot) and `app.state.mark_for_student` (API), not part of `TeacherViewUseCases`, so `application.teacher_view` stays clear of the progression port. A new import-linter contract keeps `application.teacher_marks` off crypto and the log ports.
7. **`BotRuntime` carries `labels` and `catalog`** (from `LinkUseCases`) for the note's catalog names; without them `tell_asana_marked` returns FAILED (never in the app).
8. **API shape**: `ProgressionOut.marked` defaults to null, so the generated TS type is optional; `EventOut.by`, `by_name`, `undoable` are required; `marked_by_self` stays for older clients.
9. **Mini App**: the confirm popup's cancel reuses `delete-cancel`; an error uses `haptics.notify("error")`; only a 409 shows `students-give-stale` (and refetches), any other failure shows `progression-save-failed` and keeps the picks for a retry; the Undo moved-on line shows only for a teacher's entry, otherwise `progression-changed`; `LastAsana` formats through `get` (no isolation marks). Each history Undo has an `aria-label` naming its entry (`progression-undo-entry`).
10. **Bot G**: the mark's Undo uses `progression-undo-mark` ("↩︎ Undo the mark") and sits at the top; after a change just made, that change's `[↩︎ Undo]` goes above it. The moved-on line on a failed Undo appears only while the event is among the newest 20 and is a teacher's `given`. The student's message keeps `progression-undo`.
11. **Layout**: the note's gift line and series lines are joined by line breaks, the undo hint after a blank line; picker and confirm buttons are one per row.
12. **Range buttons** name only the last stop (`→ { $asana }`, owner); **a range across a series boundary** confirms with `students-give-ask-across` (owner: "name both series").
13. **A stale key on the card** (`_where`) shows the stale card instead of falling back to index 0. Today `GetStudent` gives a stale position no `next_asanas`, so this is a safety net.
14. **Review fix**: the first build rejected every `<n>:0` position (Pasasana `2:0`, UHP `1:0`); only `0:<i ≠ 0>` is malformed now, with full-flow tests from both.

**Known residuals (accepted):**
- (a) Bot G and `marked` see only the newest 20 events: after 20+ item events following a mark, "Marked by …" and its Undo leave G (DELETE still works, and the original message's Undo still works). The later fix, with ST-04, is a lateral subquery for the position's event.
- (b) The teacher's reply latency varies with whether a send happens (no Telegram identity). A weak signal; accepted.
- (c) The unset card repeats the name ("Anna / Anna: practice not set yet"): the spec copy, kept for now.

**Measured** (500 seeded students, a year of logs each, Telegram stubbed, warm): bot mark `t1:gy` p50 32.8 ms / p95 46.5 ms; API POST p50 31.9 ms / p95 46.4 ms; card, picker, confirm 11–12 ms p50. Longest callback: 54 bytes.
