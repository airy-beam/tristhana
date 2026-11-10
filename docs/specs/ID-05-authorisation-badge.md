# ID-05: SYC directory listing (the teacher's "✔ listed" line)

- Status: **accepted** (owner, 2026-11-11: Q248–Q259 all as recommended, with the ashtanga-expert's changes, §12a; ux-writer on copy during the build) · Size S, Phase 3
- Requirements: **ID-05**, as narrowed by **Q81 = A** (owner, 2026-11-11): one verified fact, "listed in the SYC directory", no level; the level is the teacher's own words. Touches **ID-04** (consent screen, `/teachers`, `GET /me/links`), **ID-03** (who is a teacher), **ST-09** (export, delete), **ID-06** (display names, Q256).
- Related: ADR-0008, 0012, 0018, 0027, 0030. New: **ADR-0042** (accepted): platform admins as an allow-list of account ids in the environment; the listing is a manually checked, dated fact.

## 1. Scope and words
**In:** a teacher asks for the line (Mini App form); a platform admin checks the public directory by hand and answers in the bot (`/admin`); the line shows on the invite consent screen and in a student's list of teachers; re-check, removal and withdrawal; export and delete coverage; the smallest platform-admin mechanism.
**Out (Later):** verified levels (the directory has none); "Other lineage"; scraping or any automated read of the SYC site; shala staff lists, schedules, announcements, share cards (Q254); a bot form for the request (Q253); an admin API or Mini App admin screen; a public teacher directory or search; any filter or sort by listing; auto-expiry (Q255); a message to students when a line appears or goes.

**Naming (settled here):** GM-02 owns "badge" (`domain/badges.py`, `/me/badges`, `badges.ftl`, «Значки»). ID-05 is **"directory listing"** everywhere: code `directory_listing` / `Listing` / `ListingMark`, API `/me/directory-listing`, Fluent prefix `listing-` (admin: `admin-listing-`), table `directory_listing`. Copy never says badge, verified teacher, certified by, approved, official, endorsed; RU never «значок», «подтверждённый учитель», «официальный». The file name keeps the requirement's title only.

**Tone rules:** the line is one positive fact with no negative counterpart (ADR-0030). A teacher without it has a complete card: no empty slot, no "not listed", no "unverified", no prompt visible to students. Nothing sorts, counts or compares teachers by it. A removed line is told to the teacher only, gently, and to no one else.

## 2. What the line says
```
✔ Listed in the Sharath Yoga Centre teachers directory as Anna Petrova (checked: November 2026)
Level (in the teacher's own words): Authorised Level 2      ← teacher card only (§12a)
```
- **The checked fact:** this name is in the public directory of Sharath Yoga Centre, a person looked it up on that date, and the admin was satisfied the account belongs to that person (Q250). Not a level, not an endorsement.
- **The name as listed is part of the line** (Q251). It is public already, the teacher agrees to it on the form, and it closes the obvious trick: get listed, then change the display name to someone else's. The display name stays free.
- **Level** (optional): one of four fixed values (Authorised, Authorised Level 1, Authorised Level 2, Certified), always labelled as the teacher's own words, on its own line, plain text with no ✔. Shown only together with the line (Q252), and **only on the teacher card** (bot `t1:c`, Mini App tap-to-expand): never on the invite consent screen and never in lists (§12a).
- **Own line, never inline.** In the bot the mark is a separate text line (a display name can't contain a line break, so a name can't imitate it) and never a glyph on a button label. In the Mini App it is a separate element under the name. See Q256 for check marks inside names.
- `listing-about` (teacher card, Mini App tap-to-expand; ⚑): "The name is in the public teachers directory of Sharath Yoga Centre (SYC); it was looked up by hand on that date. This is not an endorsement by SYC, and Tristhana has no connection with SYC. The level is the teacher's own words: the directory shows no levels. Many experienced teachers are not in this directory; the line says nothing about a teacher who doesn't have it." / «Это имя есть в открытом списке учителей Sharath Yoga Centre (SYC); запись сверена вручную в указанную дату. Это не рекомендация от SYC, и Tristhana не имеет отношения к SYC. Уровень указан со слов учителя: в списке уровней нет. Многих опытных учителей в этом списке нет; отсутствие строки ничего не говорит об учителе.»

## 3. Flows
**Teacher (Mini App, lazy `screens/settings/DirectoryListing.tsx`).** Entry: one quiet row "SYC directory listing" in the invite part of Settings → 👥 Teachers and students. Bot: the same row on the invite screen (`t1:i`) opens `l1:o`, a status screen with `[Open the app]` (`?open=listing`, as `open=announce`) and `[Remove…]`. Anyone may ask (Q249); the row is hidden when no admin is configured.
- **Form:** name exactly as in the directory (1–100), country or region as in the directory (1–60), level (optional select), "How can we tell it's you?" (optional, ≤ 300; e.g. the website or Instagram shown in the directory that points to this Telegram account; seen only by the checker, deleted at the answer). Under the name: "Students will see this name in the line."
- **States** (`none → pending → listed | not_found`, plus `withdrawn`):

| From | Action | To | Notes |
|---|---|---|---|
| none / withdrawn / not_found | send | pending | admins get one silent note; refused (`listing_wait`) within 24 h of the previous send, so an account can cause at most one note a day |
| pending | edit | pending | in place, `revision + 1`, no note |
| listed | edit level only | listed | no check needed (self-declared) |
| listed | edit name or region | pending | native confirm first: the line hides until checked again |
| any | Remove (one confirm) | withdrawn | name, region, level and note are cleared; only the timestamps stay (for the 24 h rule); the line goes at once; no one is told |
| pending | admin: Listed / Not found | listed / not_found | note cleared; the teacher gets one silent message |
| listed | admin: Still listed / No longer listed | listed (new date) / not_found | re-check (§6) |

**Admin (bot only, prefix `l1:`).** `/admin` is in no menu and not in `/help`; for anyone else it answers the usual `fallback-text`, so it can't be probed. Screen: "Directory requests: N waiting · M listed, oldest check: March 2026", pending rows oldest first (10 per page), `[Listed: re-check]`. Request card: display name, name as listed, region, level (labelled self-declared), the note, the request date, `[🌐 Open the directory]` (URL button, the fixed public URL), `[✔ Listed]`, `[Not found…]` (one confirm). No Telegram id or `tg://user` button (it fails for people with strict privacy settings; Later). The new-request note is a direct silent message through the `Notifier` (as `tell_student_joined`: outside the ledger and the cap, no retry; `/admin` is the record).

**Student.** Nothing to do. The line appears (a) on the consent screen of `/start t_<code>`, between `invite-ask` and the consent bullets, and (b) on the teacher card (`t1:c`) and under the teacher's name in the Mini App list. `invite-know-them` stays for everyone, listed or not.

## 4. Domain (pure) `domain/directory_listing.py`
```python
DIRECTORY_URL = "https://sharathyogacentre.com/authorised-teachers-directory/"
NAME_MAX = 100; REGION_MAX = 60; NOTE_MAX = 300; RESEND_AFTER = timedelta(hours=24)
class ListingStatus(StrEnum): PENDING, LISTED, NOT_FOUND, WITHDRAWN
class DeclaredLevel(StrEnum): AUTHORISED, AUTHORISED_1, AUTHORISED_2, CERTIFIED      # "authorised", "authorised-1" …
class Outcome(StrEnum): LISTED, NOT_FOUND
@dataclass(frozen=True, slots=True)
class Listing: status; name_as_listed: str | None; region: str | None; level: DeclaredLevel | None
               note: str | None; revision: int; requested_at: datetime; checked_on: date | None
@dataclass(frozen=True, slots=True)
class ListingMark: name_as_listed: str; checked_on: date; level: DeclaredLevel | None  # all that crosses accounts
@dataclass(frozen=True, slots=True)
class Details: name_as_listed: str; region: str; level: DeclaredLevel | None; note: str | None
def clean(name, region, level, note) -> Details          # as normalize_display_name: bidi/control stripped, single-spaced; raises InvalidListing
def next_state(current: Listing | None, details: Details, now) -> Step  # SEND | EDIT | LEVEL_ONLY | RECHECK; raises ListingWait
def mark_of(listing: Listing | None) -> ListingMark | None   # LISTED only
def may_decide(listing: Listing, outcome: Outcome) -> bool   # pending → either; listed → either (re-check)
```
No rule reads practice data. The levels are a closed enum in code (four historical terms, not a catalog; plain "Authorised" is for teachers authorised before levels existed); the directory URL is a domain constant, shown to the admin only.

## 5. Application, ports, policies
- **Use cases** `application/directory_listing.py` (bot and API share them): `GetListing`, `RequestListing` (send/edit; notifies admins only on SEND and RECHECK), `WithdrawListing`, and for admins `ListRequests(page)`, `GetRequest(account_id)`, `DecideListing(account_id, revision, outcome)`. `checked_on` = the admin's local date (`caller_today`). Exceptions never carry the name, region or note.
- **Policies** (`application/policies.py`): `can_manage_listing(actor, owner)` = the owner; `can_check_listings(actor, admins: frozenset[UUID])` = `actor.id in admins`. A non-admin gets `NotFound` from the admin use cases, never `NotAllowed`. An admin may check their own request (Q258). The admin set comes from settings into the use cases at wiring; `application` reads no environment.
- **Port** `application/ports/directory_listing.py` → `Storage.listings`: `get(me)`; `save(me, details, step, now) -> Saved` (one upsert; on SEND/RECHECK its `RETURNING` joins `identity`/`account` for the admins' Telegram id and locale); `withdraw(me)`; `requests(page) -> RequestsPage` (pending page + both counts + oldest check, one statement); `request(account_id)`; `decide(account_id, revision, outcome, checked_on, by) -> Decided | None` (one `UPDATE … WHERE revision = :revision AND status IN (…) RETURNING`, joined to the teacher's Telegram id and locale; None = it changed, the admin sees `admin-listing-stale` and the fresh list).
- **Reads on existing screens, no new statement:** `TeacherLinkRepository.preview` and `overview` gain a `LEFT JOIN directory_listing … AND status = 'listed'` on the teacher's id (PK lookup). `InvitePreview`/`Previewed` and `Linked` gain `listing: ListingMark | None` (always None on student rows). The account load (middleware) is **not** touched.
- **Notifier** += `tell_listing_requested(recipient)` (to each admin; carries no name) and `tell_listing_checked(recipient, outcome, name_as_listed, was_listed)` (to the teacher). Both silent, direct, ≤ 3 s, outside the ledger and the cap; `BLOCKED`/`FAILED` ignored.
- **Settings:** `platform_admin_ids: str = ""` (comma-separated account UUIDs; a validator rejects anything else; ≤ 5) with a `platform_admins` property. Empty: the request row, the endpoints (503 `unavailable`) and `/admin` are off.

## 6. Staleness and removal
- The date is always part of the line, so the sentence stays true however old it is (Q255). No auto-expiry, no tick job.
- `/admin` → `[Listed: re-check]` lists listed accounts, oldest check first: `[Still listed]` sets `checked_on` to today (no message); `[No longer listed…]` (one confirm) sets `not_found`, hides the line at once and sends the teacher `listing-note-ended`. Working rule for the admin: go through the list about twice a year.
- What the teacher reads (⚑): "At today's check I couldn't find «{ $listed }» in the SYC teachers directory, so that line is no longer shown. Everything else stays as it is: your students, your link, your lists. If the directory shows the name again, or under another spelling, send the details any time." Students get nothing; their list simply has no line.

## 7. API (initData auth; `{code}` errors; `no-store`; then `gen:api`)
| Method, path | Request → Response | Policy |
|---|---|---|
| `GET /api/v1/me/directory-listing` | → `ListingOut {status: "none"\|"pending"\|"listed"\|"not_found"\|"withdrawn", name_as_listed, region, declared_level, note, requested_at, checked_on, can_send: bool}` (nullable fields null when absent) | `can_manage_listing` |
| `PUT /api/v1/me/directory-listing` | `ListingIn {name_as_listed, region, declared_level?: "authorised"\|"authorised-1"\|"authorised-2"\|"certified"\|null, note?}` → `ListingOut`; 409 `listing_wait`; 422 | `can_manage_listing` |
| `DELETE /api/v1/me/directory-listing` | → 204, idempotent | `can_manage_listing` |
| `GET /api/v1/me/links` (existing) | `teachers[]` += `listing: {name_as_listed, checked_on, declared_level} \| null`; `students[]` unchanged | own |

`ErrorCode` += `listing_wait`. No admin endpoint. Nothing new on shala or schedule payloads.

## 8. Bot (`bots/telegram/directory_listing.py`, `directory_listing_callbacks.py`; prefix **`l1:`**, free; answer first, edit in place)
| Data | Meaning |
|---|---|
| `l1:o` · `l1:w` · `l1:wy` | my status screen · remove ask · remove |
| `l1:a:<page>` · `l1:k:<page>` | admin: waiting list · listed list (re-check) |
| `l1:c:<uuid>` | admin: card (request or listed) |
| `l1:y:<uuid>:<rev>` · `l1:n:<uuid>:<rev>` · `l1:ny:<uuid>:<rev>` | Listed / Still listed · not-found ask · not found / no longer listed |

Longest `l1:ny:<uuid>:<rev ≤ 6 digits>` = 49 bytes. `<rev>` makes an old button harmless after an edit; a forged uuid matches no row; every admin callback re-checks the policy. `/admin` is registered before the catch-all and is absent from `COMMANDS` in `set_webhook.py`. The consent screen and teacher card add the mark lines from data they already hold.

## 9. Migration `0027_directory_listing` (expand-only, down `0026`), export, delete, ops
- `directory_listing(account_id uuid PK → account ON DELETE CASCADE [directory_listing_account_id_fkey], status text NOT NULL, name_as_listed text, region text, declared_level text, note text, revision integer NOT NULL DEFAULT 1, requested_at timestamptz NOT NULL DEFAULT now(), checked_on date, checked_by uuid → account ON DELETE SET NULL [directory_listing_checked_by_fkey], decided_at timestamptz)`.
- CHECKs: status and level value sets; lengths (100 / 60 / 300); `(status = 'withdrawn') = (name_as_listed IS NULL)` and the same for `region`; `status <> 'listed' OR checked_on IS NOT NULL`; `note IS NULL OR status = 'pending'`. Partial indexes `(requested_at) WHERE status = 'pending'` and `(checked_on) WHERE status = 'listed'`. `op.f()` names; grants from the defaults; no backfill; downgrade drops the table.
- **Export (ST-09):** `directory_listing` joins `EXPORTED_TABLES`; `data.json` gains `directory_listing: {status, name_as_listed, region, declared_level, note, requested_at, checked_on} | null` in the existing snapshot (schema stays `/1`, additive). `checked_by` is never exported (the `marked_by` rule), and rows an admin checked are not the admin's data. `export-readme` gets one line. **Delete:** the row cascades with the teacher; a deleted admin leaves `checked_by` NULL and the lines stay. `delete-explain` needs no change.
- **Owner steps:** read your account id (`id` in `GET /api/v1/me`, or the export) and give it to the developer: `PLATFORM_ADMIN_IDS=<uuid>` goes into `--set-env-vars` in `.github/workflows/backend.yml` (a repo change; an account uuid is not a secret) and into `backend/.env` for dev (the dev DB has its own id). No ☁️ step, no `set_webhook.py` run. Migration 0027 runs in CI.

## 10. Cross-cutting checks
- **Time zones:** `checked_on` is a `date` (the admin's local date at the tap) and is shown as month and year only, so no time and no zone label; Mini App formats the date string with `timeZone: "UTC"`. `requested_at`/`decided_at` are UTC instants; the 24 h rule is instant arithmetic, and the copy says "in a day", never a clock time.
- **Privacy:** across accounts only `ListingMark` travels, and only to people who hold the teacher's invite code or are linked. Region and note are admin-only; the note is cleared at the answer and on removal. Plain columns (public-directory data, and the checker must read them); not sealed. Logs carry the account uuid and the outcome only: no name, region, note or level (log-capture test). The admin never sees a Telegram id, practice data or student lists. No outbound request to the SYC site is ever made by the server.
- **i18n:** all copy in Fluent, en + ru, «ты», names nominative (RU «✔ { $listed } — в списке учителей Sharath Yoga Centre (сверено: { $when })», month in the nominative after a colon). Bot keys in `bot.ftl`; Mini App: the three mark keys in `app.ftl`, the form in a lazy `listing.ftl`. Admin copy is localized too. Notes use the recipient's locale.
- **Responsiveness:** consent, `/teachers`, teacher card, `GET /me/links`: same statement count as today (one more PK join). `l1:` screens: middleware 1 + 1. Send / decide: 1 statement + 1–2 silent sends (rare). Lazy chunk for the form; initial bundle + three short keys. Target < 300 ms p50 warm.
- **Layering:** new import-linter contract "The directory listing reads no log, diary, check-in, progression or key" (`application.directory_listing`, `infrastructure.db.directory_listing`); aiogram only in `bots/telegram`; domain pure.

**Copy keys** (⚑ all drafts; ux-writer, and ashtanga-expert for the level names):
| Key | EN | RU |
|---|---|---|
| `listing-mark` | ✔ Listed in the Sharath Yoga Centre teachers directory as { $listed } (checked: { $when }) | ✔ { $listed } — в списке учителей Sharath Yoga Centre (сверено: { $when }) |
| `listing-level` | Level (in the teacher's own words): { $level } | Уровень (со слов учителя): { $level } |
| `listing-level` values `authorised` / `authorised-1` / `authorised-2` / `certified` | Authorised / Authorised Level 1 / Authorised Level 2 / Certified | Authorised (авторизация) / Authorised Level 1 (авторизация, уровень 1) / Authorised Level 2 (авторизация, уровень 2) / Certified (сертификация SYC) |
| `listing-open` | SYC directory listing | Строка о списке SYC |
| `listing-intro` | If your name is in the Sharath Yoga Centre teachers directory, I can show that to your students next to your name. A person checks it by hand, so it can take a few days. Everything here works the same without it. | Если твоё имя есть в списке учителей Sharath Yoga Centre, я могу показывать это ученикам рядом с твоим именем. Проверяет человек, вручную, поэтому это может занять несколько дней. Всё остальное работает одинаково и без этой строки. |
| `listing-pending` | Sent. A person will look it up by hand. | Отправлено. Человек сверит запись вручную. |
| `listing-not-found` | I couldn't confirm the entry «{ $listed }» for this account yet. The name may be spelled differently, or the directory may have changed. You can look over the details and send them again. | Сверить запись «{ $listed }» с этим аккаунтом пока не получилось. Возможно, имя написано иначе или список изменился. Можешь поправить данные и отправить ещё раз. |
| `listing-note-listed` | ✔ «{ $listed }» is in the SYC teachers directory. Your students now see this next to your name. | ✔ «{ $listed }» есть в списке учителей SYC. Теперь ученики видят это рядом с твоим именем. |
| `listing-wait` | You can send it again in a day. | Отправить снова можно через день. |
| `listing-remove-ask` | Remove the directory line? Students will no longer see it. You can ask again later. | Убрать строку о списке SYC? Ученики перестанут её видеть. Позже можно отправить запрос снова. |

Also: `listing-field-name`, `-region`, `-level`, `-note`, `listing-shown-hint`, `listing-send`, `listing-edit-ask`, `listing-note-not-found`, `listing-note-ended` (§6), `listing-about` (§2), `export-readme-listing`, and `admin-listing-title`, `-waiting`, `-recheck`, `-card`, `-open-directory`, `-listed`, `-still-listed`, `-not-found`, `-not-found-ask`, `-stale`, `-new` ("A directory request is waiting: /admin").

## 11. Test plan
- **Domain:** `clean` trims, strips bidi/control characters, rejects empty and over-long values and an unknown level; `next_state` for every row of the §3 table, incl. 23 h 59 min vs 24 h, level-only edit stays listed, name edit → RECHECK; `mark_of` only for LISTED, carries exactly three fields; `may_decide` per status.
- **Use cases (fakes, fixed clock):** send notifies each admin once, edit notifies no one; no admins configured → unavailable; decide sets `checked_on` to the admin's local date (Kiritimati vs Honolulu on one instant); a stale revision → no write, no message; the teacher's note in the teacher's locale; `BLOCKED` still succeeds; withdraw clears the details and tells no one; exceptions carry no name. **Policies:** owner only for `can_manage_listing`; `can_check_listings` true only for a listed id, false for an empty set; a non-admin gets `NotFound`; **a pin test that no `can_view_*` and no shala policy takes the admin set** (a platform admin sees no one's practice).
- **DB (real Postgres):** statement counts as §10 (`preview` and `overview` unchanged, with and without a row); every CHECK; two concurrent decides → one wins; an edit between card and tap makes the decide return None; `not_found`/`pending`/`withdrawn` rows never produce a mark in `preview`/`overview`; deleting the teacher cascades; deleting the admin nulls `checked_by` and keeps the line; **app role** (`test_db_app_role.py`): send, edit, withdraw, decide and export as `tristhana_app`; 0027 up/down/up; `alembic check`; export coverage guard passes; `data.json` has the section and never `checked_by`.
- **API:** 401; GET for each status; PUT validation 422, 409 `listing_wait`; DELETE 204 twice; `GET /me/links` `teachers[].listing` exact key set and absent from `students[]`; 503 with no admins; `no-store`; OpenAPI lists the codes and the TS client builds.
- **Bot (through the webhook, fake use cases):** `/admin` as a non-admin equals the fallback reply byte for byte, and every `l1:` admin callback from a non-admin only answers; pending list paging; card; Listed / Not found (confirm step) / Still listed / No longer listed; stale revision → `admin-listing-stale`; forged and malformed `l1:` data; every value ≤ 64 bytes; `answered` before the work; the consent screen with and without the line, with a level, with 64-character names and a 100-character listed name ≤ 4096 in both locales; a teacher button label never contains the mark; teacher card line; `set_webhook.py` does not list `admin`; **log capture at DEBUG over send, decide and a handler error: no name, region, note or level.**
- **Mini App (Vitest, `TZ=UTC` too):** the row on the invite part, hidden on 503; form validation and the "students will see this name" hint; each status view; level-only edit without a confirm, name edit with one; remove confirm; 409 shows `listing-wait`; teacher rows with and without the line look complete (no placeholder element); the level never renders without the mark; month and year in en and ru; RU at 320 px; `check:bundle`.
- **i18n / architecture:** ftl parity and variables; avoid-word grep over `listing-*`: badge, verified, unverified, certified by, approved, official, endorse(d) (except the "not an endorsement" sentence), guru; RU значок, подтвержд, официальн, одобрен; import-linter incl. the new contract.

## 12a. Owner answers (2026-11-11) and ashtanga-expert changes
All of Q248–Q259: option (a), except **Q257: (b)** for the line ("Sharath Yoga Centre" spelled out; "SYC" only on the settings row) and **(b)** for RU levels (English titles with a gloss). Expert changes accepted:
- The decline message never claims the name is absent from the directory: "couldn't confirm the entry for this account" (it also covers identity doubt).
- `listing-about` and `listing-intro` say that many experienced teachers are not in this directory and a missing line says nothing about a teacher.
- The self-declared level shows only on the teacher card / tap-to-expand; never on the consent screen, never in lists. `GET /me/links` still carries `declared_level`; the invite preview does not.
- A fourth level value, plain "Authorised" (`authorised`), for teachers authorised before levels existed.
- `listing-note-ended` adds "the directory changes; this says nothing about your teaching". The ✔ is never coloured blue.

## 12. Open questions for the owner (recommended option first; answered, see §12a)
248. **Platform admin.** (a) An allow-list of account ids in the environment, checked by an application policy, bot-only screens (ADR-0042); (b) an `account.is_platform_admin` column set by SQL (what `05 Domain Model` says today: "a flag"); (c) a separate admin group chat.
249. **Who may ask.** (a) Anyone (a new teacher has no students yet, and the line matters most on the first invite); (b) only accounts with at least one student or a shala teaching role.
250. **What counts as "it's you".** (a) The admin's judgement, helped by the optional note (a site or profile shown in the directory that points to this Telegram account); unsure → "Not found" or leave it waiting; (b) the name alone is enough; (c) a stricter rule (the admin must reach the teacher through a contact shown in the directory).
251. **The name as listed in the line.** (a) Shown to students ("…as Anna Petrova"), which stops a rename after the check; (b) admin-only, and a display-name change hides the line until re-checked.
252. **Self-declared level.** (a) Shown only together with the line; (b) any teacher may state a level, listed or not; (c) no level in the first version.
253. **Request form.** (a) Mini App only (free text, no bot dialog state); the bot shows the status and Remove; (b) also a bot dialog with ForceReply (as the diary).
254. **Where the line shows first.** (a) The invite consent screen and the student's list of teachers (card), bot and Mini App; (b) also shala staff lists now; schedules and announcements stay Later either way.
255. **Old checks.** (a) The date is always shown, the admin re-checks by hand about twice a year, nothing expires; (b) the line hides by itself 12 months after the last check; (c) the tick reminds the admin.
256. **Check marks inside display names.** (a) Drop ✔ ✓ ☑ ✅ from display names when they are saved (existing names untouched until the next save); (b) leave names alone and rely on the own-line rule.
257. **Wording.** (a) "✔ Listed in the SYC teachers directory" / «✔ В списке учителей SYC», with Sharath Yoga Centre spelled out in the explanation; (b) the full name in the line itself; (c) other. Level names in RU: (a) «Авторизация, уровень 1/2», «Сертификация»; (b) keep the English terms.
258. **An admin's own request.** (a) Allowed while there is one admin (`checked_by` records it); (b) needs a second admin.
259. **Resend limit.** (a) One send per 24 h per account; (b) 7 days.

Notes for notes-keeper after the answers: reword the ID-05 row in `02 Requirements` to the Q81 = A scope; `05 Domain Model` "Platform admin is a flag" → per Q248; record Q81 and Q248–Q259 in `03 Open Questions & Decisions`.

## 13. Build notes (2026-11-11): where the code differs from the sections above
- **One admin note a day, re-checks included:** a listed name or region change (RECHECK) also waits 24 h since the last send (`next_state`), not only a new request.
- **`save` is a short transaction**, not one upsert: an advisory lock on the account, the row lock, the state rule run inside, then the write; admin recipients are read by a separate statement on a send. `decide` locks the row, checks the revision and moves it on (also for "Still listed"), so an old button decides nothing. "Still listed" tells the teacher nothing.
- **The mark travels on the links port** (`InvitePreview.listing`, `Links.listings` by teacher id), not on the domain `Linked`: `domain/teacher_links.py` stays stdlib-only (a pinned test).
- **"Off" refuses only new requests.** With no admin configured: `PUT` is 503 `unavailable`, the entry row and the form are hidden, `/admin` is the fallback text. `GET` answers 200 with `available: false`, and reading or removing one's own row always works in the bot and the API, so a dropped env var can never leave a line stuck on. `ListingOut` has the extra field `available`; 422 uses the code `invalid_listing`.
- **Callbacks:** revisions up to the integer maximum; the longest value is 53 bytes.
- **Dates:** `DateArg(style="month")` renders "November 2026" / «ноябрь 2026» in the bot; the Mini App formats `checked_on` in UTC.
- **Copy:** the admin button reads "Can't confirm…" (it also covers identity doubt); `export-readme-listing` explains the status values.
- **Not done:** `PLATFORM_ADMIN_IDS` is not yet in `.github/workflows/backend.yml` (needs the owner's production account id) or `backend/.env.example`; RU at 320 px was not looked at on a device.
