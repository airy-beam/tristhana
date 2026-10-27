# ADR-0026: Progression: one current position per account plus an append-only event history; celebrations derived from the history at write time
- Status: accepted (owner, 2026-10-27)
- Date: 2026-10-27
## Context
PR-08 keeps the student's "current last asana per series" plus a history, so presets can say "Primary + Intermediate → Kapotasana" in one tap and a "new asana given 🎉" can be celebrated (GM-01). The 05 domain model planned "current last asana per sequence + `progression_event`". In Ashtanga a student learns in order and gets the next series only after the full previous one, so the per-series values are not independent. Drop-backs and standing up are optional backbending items flagged `milestone: true` in the catalog (2026-10-18 decision), not stop points. Celebrations must never fire twice (double taps, stale keyboards, retries, re-given after a correction) and must stay inside one or two short statements per tap (< 300 ms p50). Teachers will mark asanas in Phase 3. The catalog is in memory and referenced by natural keys (ADR-0010, ADR-0017). Spec: `docs/specs/PR-08-progression.md`.
## Decision
- **State:** one row per account, `progression(account_id, series, last_key, items[], last_event_id)`. The position is the current series and its last given **stop point**; every lower confirmed series is implied full (the per-series view is a pure projection). Reason (ashtanga-expert): in the SYC line Pasasana is given only after full Primary (likewise for the next series), and a series with incomplete binds still counts as full once given. The row also holds the one "Not new" dismissal of the after-practice question (target + the `last_event_id` it was made at; it lapses when the position changes). `series`/`last_key` both NULL = sun salutations and standing only; no row = never set. A full series stores its last stop explicitly. Milestone items are a set of catalog keys.
- **History:** `progression_event` rows (`start`, `given`, `changed`, `item_given`, `item_removed`; from/to position or item; `occurred_on` local date; `marked_by`; `created_at` UTC), append-only except **undo, which deletes the latest event** and restores its `from` values in one statement.
- **Concurrency:** every write is a compare-and-set on `last_event_id` (`WHERE last_event_id IS NOT DISTINCT FROM :expected`) in the same statement as the event insert. The bot takes `expected` from its read; the Mini App sends the id it saw. A lost race writes nothing and celebrates nothing.
- **Celebrations are derived, not stored:** a `given` celebrates iff its global rank (stops of confirmed series in order) is above every earlier `start`/`given` target; series complete / series begins follow from the target being a series' last / first stop; an item celebrates on its first `item_given`. The event row is the marker, and the history read is part of the write's first statement. `start` and `changed` never celebrate.
- **Plain, owner-only** (`can_view_progression`), no reason field; not sealed.
## Consequences
- Two statements per give/set (read + compare-and-set), one per undo, zero extra on the practice screens (a join and a subquery). No celebration ledger and no backfill.
- Presets read from the position use only the series just below (full) + the current series, never every lower series (Advanced A → "Intermediate + Advanced A → X"), even though the record counts all lower series as full.
- The "lower series full" invariant can't represent a student given Intermediate asanas before finishing Primary, or custom sequences (AC-03); either would need per-series rows later (an additive migration: the events already carry series).
- A mistaken `start` above the real position raises the peak and can mute a later celebration until it is undone; undo is always available for the latest event.
- Practice-count milestones (GM-01 part 2) are not monotonic (days can be cleared or backfilled), so they will need a separate "seen" ledger; this ADR doesn't cover them.
- Stale keys after a catalog edit rank as unknown: no next button, no presets, no celebrations from them; slug renames rewrite both tables (ADR-0010).
- Phase 3: `marked_by` holds the teacher; a teacher projection can hide `changed`/undo events (a step back can hint injury or pregnancy).
## Alternatives considered
- **A row per series** (`progression(account_id, series, last_key)`): matches "per series" literally, but allows inconsistent states (Intermediate set, Primary half), needs multi-row writes and multi-event undo for one action, and a CAS per row.
- **Events only, current derived from the latest event:** one table, but no cheap compare-and-set target and an ordering question once events can be backdated.
- **A `milestone` ledger with `INSERT … ON CONFLICT DO NOTHING`:** robust "once ever", but a mis-tap followed by undo would block the real celebration later, and it duplicates what the history already says. Kept for practice counts (part 2).
- **Detecting new asanas automatically from logged lengths:** rejected; a longer practice can be a led class or a teacher's one-off. We only ask, with one tap.

## Notes (implementation, 2026-10-27)
- Every position reached (START, GIVEN **and CHANGED**) counts as held before, so a step back is never celebrated as new; Undo after a forward Change removes a mis-tap without trace.
- The event id is `GENERATED BY DEFAULT AS IDENTITY`; `apply` draws `nextval` first so state and event share it in one compare-and-set statement.
