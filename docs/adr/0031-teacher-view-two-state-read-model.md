# ADR-0031: Teacher view: a two-state read model built in SQL, with no key access and no reuse of stats
- Status: accepted (owner, 2026-11-07)
- Date: 2026-11-07
## Context
ST-06 is the first read of one person's practice data by another. ADR-0030's consent promises are binding: practice or rest, length, last asana; every rest kind looks the same; "No practice" and unlogged days are blank and identical; nothing before the link date. Q87 settled that rest-period days show as rest and unlogged auto-rest days are blank.

Three earlier notes no longer fit. ADR-0020 planned teacher stats through `public_status`, but that function only folds 🌸 into rest: moon, sick, travel and `skipped` pass through. ADR-0022 expected teachers to see labelled auto days, and a logged rest on the day off projected like an auto day. ADR-0023 left room for a later policy that decrypts a period's kind. `day_log.status` also holds `moon`, `sick` and `travel` in plain text, so a careless query leaks them without any key. A hidden field in the UI is not enough: a single wrong serializer would break the promise. Spec: `docs/specs/ST-06-teacher-dashboard.md`.
## Decision
- **Separate read path.** A `TeacherViewRepository` port and two use cases, built with that port and a clock only. They don't use `DayLogRepository`, `ProgressionRepository`, the student's `Account` or `domain/stats.py`.
- **Two states.** `SharedDay` has `PRACTICED` and `REST`; blank is absence. The exhaustive domain map `SHARED` from `DayStatus` is the single source, and the SQL is built from it, so a new status is excluded until someone maps it.
- **Projected in SQL.** The statement returns only `practiced` or `rest`. Rest-period days are expanded there with `NOT EXISTS` against `day_log`, so "No practice" inside a period stays blank and no value for "logged but blank" exists above the repository.
- **No key.** The adapter selects no sealed column and holds no cipher, and an import-linter rule pins that. The path works with `MissingCipher`.
- **The link is in the statement.** Every read joins `teacher_link` on the caller and clips at `linked_on`, in one snapshot, so unlink and delete take effect on the next read. A policy re-checks the returned link's teacher.
- **New narrow policies.** `can_view_activity` and `can_view_last_asana` for the link's teacher. `can_view_check_ins`, `can_view_diary` and `can_view_progression` stay owner-only, and `can_view_milestones` is added as owner-only.
- **Today only in the list.** `GET /me/students` returns one state per student and no dates. The 7 days live on the card, so a client can't filter the list for a run of blanks. It can see who is blank today, which is the accepted "today" view.
- **Derived values use projected data only, and must be named in the consent.** Anything computed for a teacher, such as the quiet note, takes the projected dates as input, so it can't vary with a rest kind or with "No practice". A new derived value is a new exposure, so it needs a consent line before it shows.
- **Consent for the quiet note is a column on the link.** `teacher_link.quiet_note_agreed boolean NOT NULL DEFAULT false` (migration 0020) records that the student confirmed the text naming the note. Existing rows stay false, so those links never get it. Only the new ✅ `t1:a:<code>` sets it. The old `t1:y:<code>` stays decodable and only re-renders the current consent, because a consent screen stays tappable in a chat. A re-link is a new row and takes its value from the consent shown then. The flag stops at the use case and is in no output type or export.
- **This reverses ADR-0030's "no consent-version column".** ADR-0030 held that links made before a change are identifiable by `created_at`. That was wrong: an instant can't show which text was on the screen someone tapped. The column follows ID-04 §11's "per-link opt-ins become columns on `teacher_link`", so it dies with the link.
## Consequences
- Leak tests can be structural: swapping any rest kind, or "No practice" for nothing, must give deep-equal output, and compiled SQL must name no private column.
- One statement per list page or card, one shared UTC date range clipped per student in the domain: 3 dates for the list, 23 for the card. One added column, no new index.
- ADR-0020's `public_status` rule stays for share cards and shala aggregates, but it isn't enough for teachers. ADR-0022's teacher notes are replaced by Q87: a logged rest on a day off shows as rest, an unlogged one is blank.
- Because ordinary rest is often blank, 😌 skews toward rest someone logged on purpose, and a weekday run could hint at 🌸. The owner accepted this. The consent says "all rest you log", and a card line explains blanks.
- One release. The default fails closed: during the rollover or after a rollback, an old image's insert names only the old columns and gets false, and false only means no note. Migrate runs before deploy, so the new image always finds the column.
- Any future path that creates a link must show the current consent before setting the flag. Today there is one path, the bot's confirm; the Mini App and API have no accept route.
- An older link gains the note only by being removed and confirmed again. It is never upgraded in place.
- Each later consent change that gates a feature needs its own column and a new confirm callback. If that becomes frequent, one `consent_version` integer would replace these booleans.
- `t1:y` stays decodable permanently, a small cost so that old buttons still lead somewhere.
- Teachers get no run, consistency or count figures. Those depend on "No practice" versus unlogged, so any teacher stat needs its own design.
- A rule now lives in two places: "logged beats period" in `covered_days` and in this SQL. A DB test covers it. The `generate_series` expansion itself follows the tick's.
- A per-teacher opt-in for 🌸 or check-ins can't be added to this path as it stands. It would need the key, so it needs a separate, explicit path and a new ADR.
## Alternatives considered
- **Reuse `GetDays` or `GetYearStats` and filter the output:** least code, but the kinds are decrypted and held in memory on a teacher's request, and every later field is exposed unless someone remembers to strip it.
- **Project in Python from raw `DayStatus` rows:** easier to unit test, but the private value reaches the application layer, and needs a third internal state for "No practice" inside a period.
- **Materialised teacher table:** fast reads, but a second copy of student data to keep in sync on every edit, unlink, delete and period change.
- **A Postgres view or role with column grants:** strong, but a new migration and a second DB role for a hobby-scale app. The compiled-SQL test gives most of the benefit.
- **Widen `can_view_progression` for teachers (as its docstring planned):** that policy guards events and milestone items, which the consent doesn't cover.
- **A `created_at` cut-off constant, set after a first release:** no migration, but two releases and a standing rule to move the constant after any rollback, and an early value would break consent. The owner chose the column, which records the fact directly.
- **A `created_at` cut-off at deploy time, with no callback change:** a student could confirm from an old screen after release, so the link would look new though the old text was on screen.
- **A `consent_version` integer now:** more general, but one boolean states this one fact plainly, and there is no second consent change yet.
- **A 7-day strip in the Mini App list:** a side-by-side week works as a "who hasn't practiced" list.
