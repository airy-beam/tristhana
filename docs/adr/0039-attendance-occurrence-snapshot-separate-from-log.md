# ADR-0039: Attendance stored per (class, rule date, person) with a snapshot; two states; kept separate from the practice log
- Status: accepted (owner, 2026-11-09)
- Date: 2026-11-09

## Context
SC-05 asks for attendance: "Teacher logs attendance for a class (bulk), or students self-log and the teacher confirms." Classes are weekly rules expanded at read time (ADR-0034). Overrides are keyed by `(class_id, rule date)`, and ADR-0034 set that rule date aside as the occurrence identity for attendance. Past schedules are recomputed from the current rules, so a rule edit, a split or a hard delete can change or remove a past occurrence. Shala membership never grants access to anyone's log (ADR-0033, `domain/shalas.py`). The join consent says staff see "your name. Nothing from your log." The teacher view (ADR-0031) is the only cross-account read of the log, and it goes through a personal link, never through a shala. ST-08 (shala dashboard) and NT-03's deferred "class attendees" audience will read attendance later. Spec: `docs/specs/SC-05-attendance.md`.

## Decision
- **One row per person and occurrence:** `class_attendance`, unique on `(class_id, occurrence_key, account_id)`, where `occurrence_key` is the rule date (`Occurrence.key`). Each row also **snapshots** what a later read needs: `shala_id`, `class_type`, `on_date` (the local date in the class zone where it took place), `starts_at` (UTC) and `zone` (IANA, never an offset). History stays readable after a rule edit. If the class is deleted, `class_id` becomes NULL and the snapshot keeps the row's meaning.
- **Two states:** `claimed` means the person said they were there; `confirmed` means a staff member marked or confirmed it. Staff marks write `confirmed` directly, and a staff member's own claim is `confirmed` too. A write never downgrades `confirmed` to `claimed`. There is no "declined" or "absent" state: removing a row is silent, and no absence is ever recorded.
- **Validity comes from the domain:** a row can be written only for an occurrence that `expand` produces, that isn't cancelled, that has started (`starts_at <= now`), and whose `on` is no more than 6 days before the class zone's today. The use case checks this from one read, so a forged key can only fail. Rows that already exist on an occurrence later cancelled are kept.
- **Separate from the log, both ways:** attendance never reads or writes `day_log`, `practice`, `rest_period`, check-ins, the diary or progression. `application.attendance` gets an import-linter contract like `application.classes`. A student's claim offers the existing day screen as a shortcut, and the student logs from there. Staff marks never touch the student's log and send no message.
- **"Practises here" is derived:** staff appear on a roster once they have attendance at that shala in the last 90 days, or a row on that occurrence. There's no column.
- **Who:** any member can claim for themselves. Any staff seat (owner, Manager, Teacher, Assistant, Front desk) can take attendance (`can_take_attendance`). Students see only their own rows. Linked teachers who aren't on the staff see nothing.
- **Leaving a shala, or being removed, deletes that person's attendance there** in the same statement. Deleting an account cascades. A claim racing the leave can still insert a stray row (READ COMMITTED); reads count current members only, so it's never shown or counted.

## Consequences
- No change to SC-02's expansion. Attendance reads add one scalar subquery to `member_windows` (my rows) and one aggregate to `window` (staff counts). A claim or toggle costs 3 statements: account, occurrence read, guarded write.
- Because nothing is materialised, ST-08 counts read `class_attendance` by `(shala_id, on_date)` and never need the rules.
- The 🌸 projection that SC-01 §9 asked for holds trivially: no absence reason exists and the log is never read. This is stricter than "show it as rest".
- Snapshot fields can disagree with today's rule (for example, a later "all dates" time change). By design, history shows what was true when the row was written.
- Deleting a person's rows when they leave loses some ST-08 history. That's accepted for privacy, and it matches ID-04's hard-delete unlink.
- The edit window is short (7 days). Older corrections need a later feature.

## Alternatives considered
- **Materialised occurrences** (a row per class date, attendance as a child): rejected in ADR-0034 for the same reasons. There would be regeneration on every rule, policy, closure or moon change.
- **Confirming attendance fills the student's log** (Practiced + Mysore/Led context): convenient, but someone else writes the student's private data. It can conflict with what the student logged (for example 🌸 rest), it mixes data that shala staff can see with data they can't, and it breaks the "never overwrite the student's own data" rule. The shortcut button gets most of the benefit.
- **Reading the student's day status to show "rest" on the roster:** it would need a consent that shalas don't have (ADR-0033), and it risks hinting at 🌸.
- **A "declined" state** visible to the student: it reads as a verdict, which is against the tone rules. Silent removal is enough.
- **A stored "practises here" flag on `shala_staff`:** needs a column, a setting and a UI for something the attendance itself shows.
- **Keeping rows after the person leaves:** better history for ST-08, but staff would keep seeing a former member's name. The ID-04 precedent is a hard delete.
- **Replace-set writes** (`PUT {present: [...]}`): a concurrent student claim could be lost. Delta writes (`present`, `removed`) don't have that problem.
