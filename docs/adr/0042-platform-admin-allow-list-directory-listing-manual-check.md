# ADR-0042: Platform admins are an allow-list of account ids in the environment; the SYC directory listing is a manually checked, dated fact
- Status: accepted (owner, 2026-11-11)
- Date: 2026-11-11
## Context
ID-05 (spec `docs/specs/ID-05-authorisation-badge.md`) needs someone to check a teacher's name against the public Sharath Yoga Centre directory and record the answer. The code has no platform-admin concept: every policy in `application/policies.py` is about the caller's own data, a teacher link or a shala membership, and `can_delete_account` says "no admin path today". The notes (`05 Domain Model`) sketched "platform admin is a flag", never built. The first admin is the owner, there will be one or two, and the job is a few taps a month. Prod configuration lives only in the deploy step of `.github/workflows/backend.yml`; anything in Secret Manager or set by hand on the service is an owner cloud step.

Owner decision Q81 = A (2026-11-11): one fact is checked, "listed in the directory", with no level (the directory shows none); the level is the teacher's own words. The wording must not imply that SYC endorses the teacher or Tristhana. GM-02 already owns the word "badge" (ADR-0041).
## Decision
- **Who is an admin:** the setting `PLATFORM_ADMIN_IDS`, a comma-separated list of **account UUIDs** (not Telegram ids), parsed and validated at startup into a frozen set. Empty means the feature is off. The set is passed to the use cases at wiring; `application` never reads the environment.
- **What an admin may do:** exactly one policy, `can_check_listings(actor, admins)`. It gates the directory-listing review use cases and nothing else. No existing policy takes the admin set: a platform admin sees no one's practice, diary, students or shalas, and cannot export or delete anyone. A test pins this. Every later admin power gets its own named policy and its own decision.
- **Where:** bot only, behind `/admin`, which is in no menu and answers non-admins with the ordinary fallback text. No admin REST endpoint and no Mini App admin screen. Callbacks are stateless (`l1:`), each re-checks the policy, and each write carries the request's `revision`, so an old button can't decide a changed request.
- **The listing is stored, not derived:** one row per account in `directory_listing` with a status (`pending`, `listed`, `not_found`, `withdrawn`), the name as listed, the region, an optional self-declared level, `checked_on` (the admin's local date) and `checked_by` (`ON DELETE SET NULL`). The check is **manual**: the admin opens the public page in a browser. The server never calls the SYC site.
- **What crosses accounts:** only `ListingMark` (name as listed, check date, self-declared level), and only for `listed` rows, joined into the statements that already load a teacher's name (invite preview, links overview). The date is always displayed, so the statement stays true as it ages; nothing expires by itself.
- **Naming:** "directory listing" in code, API and copy; never "badge" or "verified teacher".
## Consequences
- No migration, no SQL in production and no cloud step to appoint an admin: it is a reviewed one-line repo change, and it disappears with a rollback. Dev and prod have different ids, as they have different databases.
- Changing admins needs a deploy. Fine for one or two people; a database-backed role is the upgrade path if admins ever become many or self-managed (supersede this ADR).
- An admin who deletes and re-creates their account silently stops being an admin (a new UUID): a safe failure. Their past checks keep `checked_by = NULL` and the lines stay.
- An account UUID in the workflow file is not a secret and not a Telegram identifier; it means nothing outside our database.
- The check is only as good as a person's judgement that the account belongs to the listed name. The line therefore states a narrow fact with a date, and the invite's "confirm only if you know this person" stays for everyone.
- Admin notes are direct silent messages outside the delivery ledger (as ID-04's join note); the `/admin` list is the record, so a lost note loses nothing.
- AC-01 ("catalog editable by platform admins") can reuse the allow-list with its own policy.
## Alternatives considered
- **`account.is_platform_admin` column:** free to read with the account, but appointing an admin means hand-written SQL against production (an owner cloud step, unreviewed, invisible in the repo), and a stray `UPDATE` grants the power. Rejected for now.
- **Telegram ids in the allow-list:** personal identifiers in a repo file, tied to one provider, and the `Principal` carries an account, not an identity, so the policy would need an extra lookup.
- **A Secret Manager value:** nothing here is secret, and it adds a cloud step for every change.
- **A separate admin group chat:** the bot handles private chats only (router filter); a group would need its own trust model.
- **An admin API and Mini App screen:** more surface to protect and build for a few taps a month.
- **Scraping the directory:** fragile against page changes, ambiguous name matching (transliteration, name order), outbound calls from the request path, and an automated answer would still not show that the account is that person.
- **Deriving the line at read time (no table):** there is nothing to derive it from; the fact comes from a person.
