# ADR-0037: Teacher marks: a linked teacher gives one of the next three stops through the student's own write path; a student can undo a teacher's mark until the position moves on
- Status: accepted (owner, 2026-11-08)
- Date: 2026-11-08
## Context
PR-08 Phase 3 lets a teacher mark "new asana given" for a student. ADR-0026 keeps one position per account plus an append-only `progression_event` with `marked_by`, a compare-and-set (CAS) on `last_event_id`, and an undo that deletes **only the latest event**. Every link was confirmed under the ID-04/ST-06 consent: "any teacher on your list will also be able to mark a new asana for you. You can undo it." Q86 points out that this promise breaks once anything follows the teacher's mark, because undo then refuses. The most likely thing to follow is the student ticking drop-backs. Teachers see the current position only, never `changed`/undo events or milestone items (ST-06, ADR-0031, Q59). A teacher's reply must not reveal any of these either. Spec: `docs/specs/PR-08-teacher-marks.md`.
## Decision
- **Same write, other actor.** A teacher mark is an ordinary `given` event with `marked_by` = the teacher, written by the existing `apply` statement. That statement gains a guard, `EXISTS teacher_link(student, teacher)`, so the link check and the write happen in one snapshot. There is no new event kind, table or migration. The policy is `can_mark_progression(actor, link)`: the link's teacher, one hop, one direction. Shala staff without a link can't mark.
- **One of the next three stops (owner, 2026-11-08).** A teacher picks a target among the next stop and up to two more, in catalog order. The first stop of the next series counts (Setu Bandhasana → Pasasana). The pick is **one** `given` event with `from` = the position the teacher saw, so the student gets one message, and the existing jump celebration ("New asanas: X → Y") covers it. It is dated on the student's local today. A teacher can't go further than three stops, set, change, mark back, start an unset record, touch milestone items or backdate. Those stay with the student.
- **The request names `from` and the target.** The write refuses unless the current position is still `from` and the target is among `from`'s next three stops. The CAS checks `last_event_id`, as before, and now also checks that `(series, last_key)` is still the position the change was computed from. This is what makes the undo rule below safe.
- **Undo (Q86).** One statement, as now. An event can be undone when either:
  - it is the latest event (unchanged), or
  - it is a `given` not marked by the student (a teacher's mark, including one from a deleted account, `marked_by` NULL), and no later `start`/`given`/`changed` event exists.

  In the second case, later item events are allowed. The undo then deletes that one event, sets the position back to its `from` (a pick of several stops goes back to where it started), keeps the items and `last_event_id`, and clears the "Not new" hint. Once the position has moved on since the mark, undo refuses, and ✏️ Change remains, as for any correction. The student's own marks keep latest-only undo.
- **Teachers can't undo.** A mark is confirmed once, on a screen that names the student and says they get a message. After that the mark belongs to the student's record.
- **The student is told once.** A silent direct message (`disable_notification`, 3 s timeout, no ledger, no cap, no retry) goes out in the teacher's request, like the ID-04 join note. It carries the celebration, computed from the student's history as for a self-mark, plus `[↩︎ Undo]` and `[🧘 My asanas]`. It is not an NT-01 category: it tells the student about a change to their own record.
- **The teacher's reply is the same in every case.** It shows the marked asana and the refreshed card. It never says whether the student celebrated, whether the message was delivered, or who made the last mark. Each of those would expose the hidden history.
## Consequences
- Statements: middleware 1 + mark read 1 + CAS 1 + card read 1, plus one outbound send. The undo stays 1. The student's history read stays 1, with the teacher's name added through a join on `teacher_link`.
- After a non-latest undo, `last_event_id` doesn't change. Stale clients are caught by the position check. The rare client that holds the same position and the same id still writes a correct state, because items never depend on the position.
- The history loses the retracted event entirely, so a real give later celebrates (as with ADR-0026's undo). The hint is cleared, because `last_event_id` no longer moves.
- The undo rule is pure and computed server-side (`undoable` per event). Clients only render it.
- The extra outbound call lengthens the teacher's tap. The callback is answered first, and the edit follows the send.
- Any later teacher write (items, jumps, set) needs its own consent line and its own ADR.
- If the message is lost, the student still sees the mark in My asanas, with the teacher's name and Undo.
## Alternatives considered
- **Undo stays latest-only, and ✏️ Change is "the undo":** no new rule. But it breaks the consent's "you can undo it" after a single drop-backs tick, and it leaves the teacher's mark in the history.
- **A compensating `changed` event:** append-only purity, but it keeps a trace the student asked to remove, and it never brings back a later celebration.
- **Undo any event (any author, any age):** the most flexible, but later position events chain on the deleted one's `from`/`to`, so the history becomes inconsistent.
- **A version column instead of the position check:** a new migration, and every writer would have to bump it. The position check needs no migration and catches the same races.
- **Teacher undo while latest (≤ 24 h):** fixes a teacher's slip, but the student already has the message. And a refusal would tell the teacher that the student changed something they can't see.
- **Notify through the tick and the ledger:** quiet hours and retries, but up to 10 minutes of delay, a new category, and a candidate query over events. The silent direct send already covers quiet hours.
- **Next stop only (the first proposal):** simplest, but two asanas given in one class would need two marks and send two messages.
- **Any later stop:** covers a teacher who is catching up, but a long jump is really a correction of the record, and the student owns those (✏️ Change).
- **One event per stop in a multi-stop pick:** one undo per stop and several messages. A single event with `from` already gives the range line.
- **A new `teacher_given` event kind:** clearer in SQL, but every reader of `given` (celebrations, Earlier, export, the ST-04 timeline) would need changes for no gain, since `marked_by` already holds the fact.
