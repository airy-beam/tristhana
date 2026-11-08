# ADR-0034: Classes: a weekly rule stored as columns, expanded at read time in the domain; overrides keyed by the rule date; moon cancellation derived from the shala calendar
- Status: accepted (owner, 2026-11-07)
- Date: 2026-11-07

## Context
SC-02 asks for shala classes (Mysore window, Led, 1:1, Conference, Pranayama, Workshop; the owner added Chanting), online or offline, in a zone, recurring (RRULE), with exceptions, and moon days cancelled per the shala's policy. ADR-0005 says recurring things are wall clock + IANA zone + rule, expanded in their own zone. ADR-0019 stores moon calendars per listed city; ADR-0033 gives every shala a city (zone) and a moon city. ADR-0022 derives auto-rest at read time. The bot targets < 300 ms p50 per tap with one DB round trip where possible, and heavy imports are lazy. SC-03 (my schedule in my zone), SC-05 (attendance) and SC-06 (ICS) will read the same classes. Spec: `docs/specs/SC-02-classes.md`.

## Decision
- **Rule as columns, an RRULE subset.** A class series stores `start_time` (wall clock), `minutes`, `weekdays` (ISO bitmask; 0 = a single date), `every` (1–4 weeks), `starts_on`, `ends_on`, and a zone source (the shala's city; an online class may name another listed city). This is exactly `FREQ=WEEKLY;INTERVAL;BYDAY;UNTIL` with `DTSTART;TZID`, rendered by a pure `to_rrule()` for the API and ICS. No free RRULE text is parsed or stored.
- **Read-time expansion in `domain/classes.py`**, with `zoneinfo` only (no `dateutil`). A nonexistent wall time (spring gap) shifts forward by the gap; an ambiguous one takes the first instant. Occurrences are never stored.
- **Overrides keyed by `(class_id, rule date)`**: cancelled, held anyway, moved (±6 days, time, length) or a substitute teacher. The rule date is the stable occurrence identity for SC-05 attendance and callback data.
- **Auto-cancellation is derived, never written:** the final date of an occurrence is checked against shala closures, then the stored `moon_day` dates of the shala's moon city (no new computation; kshaya dates are already the observed day) and the shala's `moon_policy` (owner, Q117): `closed` (default, everything cancelled), `pranayama` (only pranayama, conference and chanting held; Led is asana practice and stops too), `open` (nothing auto-cancelled, the 🌙 marker still shown). A staff override wins over both. A **swap day** (owner, Q125) is an explicit staff action, never suggested: the occurrences of date A that were cancelled automatically move to date B (±6 days) at the same wall clock, while classes held on A stay. B is validated at creation: the shala's day off or free of the moving types, not a moon day, not in a closure.
- **One statement per schedule read:** membership, shala, series, overrides (window ± 7 days), closures, swaps, moon dates and staff names as jsonb aggregates; writes are guarded CTEs (SC-01 pattern).
- **Classes belong to a shala**; the teacher is a staff member (composite FK to `shala_staff`, set to NULL on removal).

## Consequences
- No dependency added, nothing heavy to lazy-import, and no job or backfill: changing a rule, a policy or a moon calendar (`ALGO_VERSION`) is visible on the next read.
- A tap costs the account load plus one indexed read; expansion of ≤ 40 series over ≤ 45 days is sub-millisecond.
- Monthly rules, "the 2nd Sunday", `COUNT` and free RRULE import are not expressible. Adding them later means new columns or a parser, not a migration of stored occurrences.
- Editing a series changes all its dates; "from a date" is a split into two series in one statement, carrying later overrides. Past schedules are recomputed from current rules, so SC-05 must store attendance with its own copy of the class time it needs.
- ICS (SC-06) and SC-03 reuse `expand` and `to_rrule`; SC-03's per-viewer labels need only the viewer's zone.
- Overrides on dates a changed rule no longer produces are deleted by the edit statement.

## Alternatives considered
- **Materialised occurrences** (a row per class date, filled by the tick): simple reads and natural attendance keys, but needs a fill horizon, regeneration on every rule, policy, closure and moon-calendar change, and a backfill job; more writes for no read gain at this size.
- **Free RRULE text + `dateutil.rrule` (lazy-imported):** full RFC 5545, but a parser and a dependency in the domain, validation of arbitrary rules from a form that only builds weekly ones, and RFC's UTC `UNTIL` rule with a local `DTSTART`.
- **`recurring-ical-events` / storing VEVENTs:** ICS-native, but heavier and couples the domain to iCalendar.
- **A `led` moon policy (Led held on moon days):** dropped by the owner; a Led class is asana practice.
- **Automatic or suggested swap days:** rejected by the owner; shalas differ, so a swap is always a staff decision.
- **Writing moon cancellations as override rows:** visible in the table, but goes stale when the policy or calendar changes and duplicates the moon calendar.
- **Classes owned by a teacher or a shala (polymorphic owner):** covers solo teachers without a shala, but doubles every policy and query; a one-person shala does the same.
