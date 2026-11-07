# ADR-0032: Moon city inheritance is resolved at read time, one hop, from explicit choices only
- Status: accepted (owner, 2026-11-07)
- Date: 2026-11-07

## Context
MD-02: a teacher follows their own moon city, and a student follows their main teacher's, and everyone can override. ID-04 (ADR-0030) gives a link graph with cycles, a main teacher derived at read time (`effective_primary`), silent removal and cascade deletes. `account.moon_location` is a slug, and since ID-04 §7 NULL means "never chose" (mixed with "chose Mysuru before the fix"). The owner decided (Q76) that someone with students who never chose uses their own city, and (Q77) that a student copies only the teacher's own **explicit** city, never an inherited one. Readers of the city: auto-rest (ADR-0022), stats, `/moon`, settings, export, moon and practice reminders in the tick (ADR-0018). Spec: `docs/specs/MD-02-moon-inheritance.md`.

## Decision
- **Pure rule** `moon_follow(own, teaches, main_teacher, cities)` in `domain/moon.py`: a listed own slug wins; otherwise, when own is "Follow my teacher", or never chosen and the person has no students, the main teacher's **stored listed slug**; otherwise the Mysuru default. The teacher's own NULL or "Follow my teacher" yields nothing (one hop), so cycles can't loop and the teacher's teacher's city never crosses a link.
- **"Follow my teacher" is stored** as the sentinel `"-teacher"` in `moon_location` (no city slug can start with `-`; the DB CHECK already allows it). NULL keeps meaning never chosen and is no longer written. `PUT /me/moon-location {slug: null}` stores the sentinel.
- **Nothing is materialised.** The inputs (`teaches`, the main teacher's id, name and slug) come with the account in the middleware's existing statement and with the tick's existing candidate query. Every reader calls the rule.
- **"Own city" means the person's own explicit choice, else the Mysuru default. It is never `home_city`** (ADR-0029: a live link to the home city moves moon days on travel).
- **First-student flip:** the silent "new student" note offers `[Keep 📍 {city}]` (`m1:k:<slug>`). The tap stores the inherited city as the person's own explicit choice, only while `moon_location IS NULL`. It is idempotent and edits the note in place. Because the person chooses the city themselves, the one-hop rule holds.
- Only the student's own taps (accept, make main, remove) announce a change, in place. Changes made by others are silent and visible in labels and reminders.

## Consequences
- Link changes, teacher city changes and account deletions take effect on the next read, with no writes, triggers or jobs, and survive ST-09's cascade.
- No migration and no extra statement per tap; the account load gains an EXISTS and a ≤ 20-row index read.
- No new moon computation: teachers choose from the 34 pre-computed cities.
- A teacher's explicit city becomes visible to linked students; teachers are told on the invite screen and on `/moon`. Not choosing shares nothing.
- Past unlogged moon days re-derive with the current city (as for a manual change, ADR-0022). Logged days and runs (7-day bridge) are unaffected. "X of Y possible days" can drop slightly in a rare case: the moon date moves onto a logged practice day, and the old unlogged date becomes a possible but missed day. This is accepted; an effective-from date like `day_off_since` is the upgrade path.
- A never-chose person flips from the teacher's city to Mysuru on their first student (Q76) unless they tap Keep, and flips back silently on losing the last one.
- Moon reminder dedupe must tolerate a date moving by one day.
- SC-01 adds a shala step to the same rule.

## Alternatives considered
- **Write-time copy into the student's row** when a link, primary or teacher city changes: needs fan-out to up to 500 students, misses cascade deletes and the read-time primary takeover, and loses the difference between "inherited" and "chose".
- **Transitive resolution** (walk the graph): needs cycle guards, and leaks the teacher's teacher's choice; Q77 rules it out.
- **A separate `moon_follow` column or enum:** one bit, but a migration and two columns to keep consistent; the sentinel follows the `home_city = '-'` precedent.
- **`home_city` as "own city":** a live link to a value that travel clears (rejected in ADR-0029), and a mass switch on release.
- **A separate statement for the teacher's city in each reader:** more round trips on Today and `/moon`, against the one-statement target.
