# ADR-0048: A class edit applies from a date: the series is split, attendance follows the successor, and the app never rewrites the past
- Status: accepted (owner, 2026-11-16, with `docs/specs/UI-06-stage-4-shala-setup.md`; Q337 as recommended: no "all dates" choice)
- Builds on ADR-0034 (weekly rule, read-time expansion, split "from a date") and ADR-0039 (attendance keyed by class and rule date, with a snapshot). Amends both.
- Date: 2026-11-16
## Context
Classes are rules expanded at read time, so the past is recomputed from whatever the rule says now (ADR-0034). `PATCH /shalas/{id}/classes/{class_id}` has two paths: an in-place update of every date, and a split with `from` (the old row ends the day before, a new row with a new id starts). The Mini App never called it; UI-06 stage 4 adds class editing.

Reading the code before building showed what each path does to history. In place: the last week of the schedule and the calendar feed's back window change, past cancellations on dropped days are deleted, attendance on those days is stranded. Split: earlier dates are untouched, but attendance rows on dates from `from` on stay on the ended id (their occurrence now belongs to the new one), a class repeating every 2–4 weeks restarts its week count at `from`, and a series that someone else has already ended can get a second successor.
## Decision
- **The app's edit always applies from a date.** Saving a change to a weekly class that has started sends `from` (default: the rule date that was tapped; earliest: the shala's today). A class that has not started, and a one-off, change whole. There is no "all dates" choice in the app. The API keeps `from` optional.
- **Attendance follows the successor.** The split statement moves `class_attendance` rows of the old id with `occurrence_key ≥ from` to the new id when the new rule produces that date. Rows on dates the new rule drops stay on the ended series. Snapshots are not rewritten.
- **The rhythm survives a split.** When `every` is unchanged and above 1, the split date moves forward to the first day in one of the old rule's weeks (`domain/classes.split_start`).
- **An ended series cannot be split again past its end.** `ends_on < from` answers `NotFound`, in the use case and in the statement.
- **No link between predecessor and successor is stored.** Nothing reads one; the occurrence identity stays `(class_id, rule date)`.
- **Review amendments (2026-11-17).** The default date is the class's next date once the tapped date's class has begun. A split requires the series' last date to be the one the caller read (`read_ends_on`), so two edits cannot leave two successors. A series with no date before `from` changes whole. Overrides, restores and attendance claims are refused for a date outside the series' span (`NotFound` / `NotAttendable`), so nothing is written on an ended id. The roster's "regulars" are counted by shala and class type, across ids.
## Consequences
- History stays as it was shown: last week's schedule, calendars, cancellations and marks do not change when next week's class does.
- Every edit of a running class adds a row. Ended rows stop counting toward the 40-series cap the day after they end; `GET …/classes` returns them until a filter is needed.
- Occurrence ids change from `from` on: old bot buttons for later dates re-render with `class-gone`, and calendar apps replace those events at their next poll (new UIDs).
- A typo fix in a title also applies from the chosen date; last week keeps the old title.
- The merge of a partial body moves from the API route into `UpdateClass`, so any adapter can edit a class.
## Alternatives considered
- **Offer "all dates" beside "from a date"** (SC-02's drawing, the guide's current promise): one more choice on the form, and the one that changes history. Kept possible through the API.
- **In place for "label" fields (title), split for the rest:** fewer rows, but two code paths and a rule the person cannot see.
- **A `replaces` column linking the rows:** lets a future screen show a class's history; no reader today.
- **Leave attendance on the ended id:** no extra CTE, but today's marks vanish from the roster when today's class is edited, and a second claim doubles the count.
- **Materialised occurrences:** rejected in ADR-0034 and ADR-0039.
