# ADR-0036: Calendar feed: a per-account capability URL (hashed + sealed token), expanded UTC instances, a hand-written serializer
- Status: accepted (owner, 2026-11-08)
- Date: 2026-11-08

## Context
SC-06 asks for an ICS subscription of classes and moon days. Calendar apps (Google, Apple, Outlook) poll a URL from their own servers and cannot send Telegram initData (ADR-0015) or any header, so the URL itself must authorize. The feed is the SC-03 view (ADR-0035: my shalas' classes, 1:1 only where I'm staff, no followed teacher's other shalas) plus my effective moon calendar (MD-02, ADR-0032). Classes are weekly rules expanded at read time in their own zone (ADR-0034, which says ICS reuses `expand`/`to_rrule`). Privacy rules (ADR-0016, 0024, 0025, 0031) keep logs, rest, 🌸 and diary out of anything shared. Cloud Run is scale-to-zero; clients poll every few hours. Spec: `docs/specs/SC-06-ics-feed.md`.

## Decision
- **Capability URL** `GET /ical/v1/{token}.ics`, outside `/api/v1` auth, CORS and OpenAPI, versioned in the path. Token = `secrets.token_urlsafe(32)` (256 bits). Table `calendar_feed` (migration 0023), **one row per account** (PK `account_id`, cascade on delete): `token_hash` = SHA-256 (unique, the lookup key; no pepper needed at this entropy) and `sealed_token` (ADR-0016 format, AAD = account id ‖ "calendar-feed") so the owner can see the link again. Create and rotate are the same upsert (the old token dies in that statement); revoke deletes the row. Unknown, malformed, rotated, revoked and deleted all return the same 404. The token is never logged by the app; the Cloud Run request log is excluded for `/ical/` by a Logging exclusion filter (owner action).
- **The token is the principal.** `GetCalendarFeed` loads the account by token hash in one statement (which also stamps `fetched_on` at most once a day) and then reuses SC-03's read and row logic (`member_windows` + the extracted `_my_rows`, filter All), so membership and 1:1 policies apply exactly as in the app. Nothing reads the log, rest, 🌸, diary or check-in ports (import-linter contract). 1:1 titles are left out; every cancelled occurrence (moon, closure, staff) is omitted (owner). A class's own title wins over its type; the summary names the date's actual teacher (a substitute), the description "Dana (for Anna)". Moon events reuse the `moon-calc-note` text verbatim.
- **Expanded instances over a bounded window, in UTC.** Classes 14 days back to 56 ahead, moon days 30 back to 365 ahead, at most 2000 events. Each class event is `DTSTART/DTEND` in UTC (`…Z`) with UID `<class_id>-<rule date>@tristhana` (ADR-0034's stable identity: moved and swapped occurrences keep it). The class's own wall clock and zone label go in the description when its offset differs from mine. Moon days are all-day `VALUE=DATE` events. No `RRULE`/`EXDATE`, no `VTIMEZONE`, no `SEQUENCE`; `DTSTAMP` = the link's `created_at`, so identical content gives an identical body and ETag.
- **Hand-written serializer** in the API adapter (`api/ics.py`, pure, ~80 lines): CRLF, 75-octet folding on UTF-8 boundaries, TEXT escaping, control characters stripped. No runtime dependency; `icalendar` only as a dev dependency to validate golden fixtures.
- **Caching:** `ETag` from the body, 304 on match, `Cache-Control: private, max-age=1800`; no server-side cache, so rotate and revoke act on the next request.

## Consequences
- One migration, no new runtime dependency or secret (the existing keyring seals the copy); a new setting `PUBLIC_API_URL`. A poll is 2 statements plus expansion; realistic accounts render in tens of milliseconds.
- Anyone holding the URL sees the schedule (shalas, times, staff names, roughly my moon city), never my name, log or rest; rotating is the remedy. The link also lives in the person's chat and in their calendar provider by design.
- The published host must keep serving `/ical/v1` for as long as subscriptions exist (custom domain later: keep `run.app` or redirect).
- A DB dump plus the keyring would reveal live tokens (as it would reveal diary notes); a DB dump alone does not.
- `to_rrule` stays unused by ICS for now; recurring VEVENTs remain possible later without a schema change.
- `GetMySchedule` is refactored (its loop extracted) with no behaviour change; `member_windows` gains a moon range end and moon kinds.

## Alternatives considered
- **Show-once hashed token:** strongest at rest, but a lost link forces rotation and re-subscribing everywhere; Telegram users rarely keep such links.
- **Plain token in the DB (like the teacher invite, ADR-0030):** simplest, but a DB dump would expose live schedule links; the invite is meant to be shared, this link is not.
- **HMAC-derived token (`feed_id` + MAC with a server key):** re-showable without a sealed column, but needs a new secret and its rotation story; the keyring already exists.
- **Token per scope (per filter or shala):** more control, more links to manage; one link matches "My schedule".
- **Recurring VEVENTs with RRULE/EXDATE/RDATE + VTIMEZONE:** smaller bodies and native recurrence, but moves, swaps, substitutes and moon/closure cancellations become RECURRENCE-ID overrides, VTIMEZONE must be generated from tzdata, and clients differ in how they apply them. Expanded instances reuse `expand` verbatim and show exactly what the app shows.
- **`TZID` with IANA names, no VTIMEZONE:** accepted by Google and Apple but not RFC-conformant; UTC is unambiguous everywhere.
- **`STATUS:CANCELLED` events:** Google hides them and others render them inconsistently; omission is predictable and the moon day explains itself.
- **`icalendar` / `ics` at runtime:** correct folding and escaping for free, but an import on a cold path and more than we use; the subset we emit is small and golden-tested.
- **In-process response cache:** cheaper repeated polls, but scale-to-zero makes hits rare and a cache keyed by token delays revocation.
