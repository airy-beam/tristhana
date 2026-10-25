# ADR-0022: Auto-filled rest days are derived at read time, never stored
- Status: accepted (owner, 2026-10-25)
- Date: 2026-10-25

## Context
PR-09: moon days and the weekly day off are "pre-marked as rest (the user can override)". Constraints already decided:
- **Explicit always wins** (Q21, ashtanga-expert): practising on a moon day is allowed and must never be overwritten, and the same goes for a 🌸 day on the day off.
- `day_log` rows are the person's own statements. Every `rest` row carries a seal (ADR-0016). Teachers (ST-06) will read projected `day_log` rows.
- Stats (ADR-0020) treat unmarked days as "not counted". Runs bridge up to 7 unmarked days, so someone who stops logging sees their run end.
- Moon calendars are stored per city and can change: an `ALGO_VERSION` recompute (ADR-0019), the MD-05 official import, or the person picking another city.
- Cost: no new job. The tick already has a 40 s budget (ADR-0018). Bot taps should take one statement.

## Decision
1. **Auto-rest is a pure domain function evaluated at read time.** It is never written to `day_log`. It covers a local date `d` with `joined ≤ d ≤ today` that has **no `day_log` row**, where `joined` is the local date of the account's creation in its zone (no auto days before someone joined). If `d` is a moon day of the followed calendar, the result is `moon`, flagged `also_day_off` when it is the day off too (one rest day: nothing is shifted or added). Else, if `d`'s ISO weekday is in the day off in effect on `d`, the result is `day_off`. Otherwise there is none. A logged row always wins, because the function only looks at unlogged dates. Overriding is just normal logging. Clearing a log brings the auto status back. Moon auto-fill applies to everyone, with no toggle.
2. **The day off is an ISO-weekday set with an effective-from date**, stored on `account` as bitmask `smallint`s (bit `d-1` = weekday `d`): `day_off` (NULL = never chosen, 0 = no fixed day off), `day_off_since` (local date of the last choice) and `day_off_before` (the set before `day_off_since`; NULL = `day_off` applies to all history from `joined`, as after the first choice). A correction on the day of the first choice stays retroactive (a mis-tap must not leave old weeks on the wrong day; ashtanga-expert, 2026-10-25). The API exposes `day_off: list[int] | null`. One day is allowed for now. Two days off later only raise a domain limit; no column or schema change is needed. The first choice applies to all history. A later change applies from that local day, and earlier dates keep the previous set. Two or more changes fold the oldest periods into `day_off_before` (accepted limit, cosmetic only). Never chosen means no day-off auto-fill (nothing is guessed).
3. **Auto days are a separate output, never a `DayStatus` of a logged day.** APIs return them next to the logged days (`auto: [{date, kind, also_day_off}]`), and stats count them apart from logs (in the rest buckets plus a separate `auto` count, never in `unlogged`). The two rules that make inactivity visible stay as they are: consistency ("possible days" = practiced + "No practice") and the run bridge.
4. **Run-bridge semantics:** auto days stay *unmarked* for the 7-day bridge, so a weekly auto day off never keeps a dormant run alive.
5. **Reminder days follow the day off:** stored `practice_days = NULL` means "every day except the day off" (except Saturday while never chosen). Choosing a day off resets custom reminder days to follow it.

## Consequences
- No writes, no job, no crypto, no backfill. The account row (already loaded by every request's auth step) carries the day off and the join date, and moon dates join the existing range query, so bot taps keep one statement and stats keep two.
- Settings and calendar changes show up immediately and consistently: city changes, recomputes and the MD-05 import need no rewrite, and neither does a day-off change.
- History is stable across one day-off change; the history before that is approximate (only one previous set is kept).
- PR-10's "already logged" check sees logged rows only: an unlogged auto day counts as not logged for the tick.
- A teacher view (ST-06) gets the same derived auto days from the student's settings, clearly labelled as not logged, so it never mistakes auto-fill for a statement. **Privacy:** ST-06 must project a *logged* plain rest or 🌸 on the day off exactly like an auto day off, so the teacher can't tell that something was logged on that day.
- Every reader that wants auto days must call the domain function (`GetDays`, `GetYearStats`, later teacher/share views). Raw `day_log` exports (ST-09) contain only what the person logged.

## Alternatives considered
- **Materialised rows written by the tick at local day start** (`source = 'auto'`). Rejected for these reasons:
  - The tick writes daily for every account, dormant ones too.
  - Every auto rest row needs a seal (ADR-0016).
  - A day-off change, a city change or a moon recompute needs a rewrite job.
  - Backfilling history needs a one-off job.
  - "Explicit wins" depends on every writer using insert-if-absent.
  - Rows would look like the person's own logs to PR-10's "already logged" check, to exports and to teachers.
- **Fully retroactive day off (no effective-from)**. This is simpler, but switching Saturday → Sunday would recolour a year of history and bring back past "unmarked" invitations for this month.
- **A `day_off_period` table with full history**. Exact, but it costs a join or an extra statement on every read. It's the upgrade path if people change their day off often.
- **A single weekday `smallint` (0–7)**. Simpler today, but two days off would need a migration and an API change. A bitmask costs nothing extra now.

## Amendment (2026-10-25, owner)
One day setting: up to two days off; the other days are the practice days, and practice reminders come on them only. Reminder days are no longer stored or chosen (migration 0008 clears `practice_days`, 0009 drops the column). This removes the "custom days reset" note and its extra statement: setting the day off is one statement.

