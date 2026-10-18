# PR-01 + PR-04: log the day status (today, backfill, edit)

- Status: accepted (owner: all recommendations, PyNaCl instead of `cryptography`; see §9) · Date: 2026-10-18
- Requirements: **PR-01** (day status: Practiced · Rest day · Moon day · Ladies' holiday · Sick/Injury · Travel · Skipped), **PR-04** (today, yesterday, any past date; editable), **WH-01** (one-tap ladies' holiday; the multi-day range comes later), **WH-02** (others see "Rest day"), **WH-04** (field-level encryption), **UI-01** ("log today?" from /start), **NF-03**. Budget: < 300 ms p50 per tap warm.
- Related: ADR-0005 (time), 0008 (stateless callbacks), 0012 (webhook reply), 0014, 0015. New: **ADR-0016** (field-level encryption, Proposed).

## 1. Scope
**In:** `day_log` table, the `DayStatus` domain, `GetDays` / `SetDayStatus` / `ClearDayStatus` use cases, the AES-GCM field cipher (ladies' holiday), the bot `/log` flow and a "Log today" button under /start, the week picker for backfill, `GET/PUT/DELETE /api/v1/me/days…`, and a Mini App "Today" card (status chips for today only).
**Out (separate features; the schema leaves room):** practice details (context PR-02, length PR-03, duration/start PR-05), `practice` rows, the reminder quick-log (PR-10, reuses this callback), auto-fill of moon days and the weekly day off (PR-09), the ladies' holiday multi-day range (WH-01 part 2), streaks and stats (ST-01..03), the Mini App calendar/backfill (comes with the ST-01 heatmap), the zone picker in settings (ID-06), teacher projections (ST-06), and import of old history.
**Cut if time is short:** the Mini App card (the bot plus the API already satisfy PR-01/PR-04).

## 2. Flows and copy
- **Bot, today:** `/log` or the [📝 Log today] button under /start → message "How was your day? · Today, Sat 18 Oct" with buttons: row 1 [🧘 Practiced] (full width); then [😌 Rest day] [🌕 Moon day] · [🌸 Ladies' holiday] [🤒 Sick / injury] · [✈️ Travel] [🌱 Skipped]; then [📅 Another day]. If the day already has a status, it is marked ✓ and a [Clear] button appears. Tap → callback answered first → the message is edited in place to "✓ Saved for today, Sat 18 Oct: 🧘 Practiced. Well done 🙏" + [✏️ Change] [📅 Another day]. Ladies' holiday adds "Only you see this. Others see "Rest day"."
- **Bot, backfill (PR-04):** [📅 Another day] → week picker: 7 date buttons (today and the 6 days before), each showing its status emoji or "·", plus [‹ Earlier] / [Later ›] (Later stops at today). Tap a date → the same status screen for that date. Editing = choosing another status. Clear = delete the row.
- **Zone not known yet** (bot-only users): "today" uses a provisional zone (§3). The confirmation always names the date, and while the zone is unknown it adds: "Tip: open the app once, so I know your time zone and your days land on the right date." (the /start button opens it; the Mini App reports the device zone silently, ID-01).
- **Mini App:** Home gets a "Today" card: the 7 status chips for today (current one highlighted), tap = save with haptic feedback; [Clear] when set. Nothing else on Home changes.
- **Failures:** DB down → `error-temporary` (toast on callbacks); a future date (stale keyboard after a zone change) → toast `log-date-future`; API errors as `{code}`.
- **Copy (new keys; ux-writer polishes; RU «ты»; RU ladies' label to confirm with ashtanga-expert):** `bot.ftl`: `log-prompt` ("How was your day? · { $day }"), `day-label` (`$rel` today/yesterday/other → "Today, Sat 18 Oct" / "Yesterday, …" / "Thu 16 Oct" via `DATETIME`), `status-practiced` "🧘 Practiced" / «🧘 Практика», `status-rest` "😌 Rest day" / «😌 Отдых», `status-moon` "🌕 Moon day" / «🌕 Лунный день», `status-ladies` "🌸 Ladies' holiday" / «🌸 Женские дни», `status-sick` "🤒 Sick / injury" / «🤒 Болею / травма», `status-travel` "✈️ Travel" / «✈️ В дороге», `status-skipped` "🌱 Skipped" / «🌱 Пропуск», `log-saved` (with a `$status` selector for the cheer: practiced "Well done 🙏", rest-like "Rest is part of the practice 🌿", skipped "Noted. Tomorrow is a fresh start 🌅"), `log-private-note`, `log-zone-hint`, `log-another-day`, `log-change`, `log-clear`, `log-cleared`, `log-earlier`, `log-later`, `log-pick-day`, `log-date-future`, `start-log-today`; `help-text` updated (logging is no longer "coming soon"). `app.ftl`: `today-title`, the same `status-*` keys, `today-saved`, `today-private-note`, `today-clear`. Never "missed", "broke", "failed".

## 3. Design
**Domain (`domain/days.py`, pure).** `DayStatus(StrEnum)`: `practiced, rest, moon, ladies, sick, travel, skipped`. `DayLog(local_date: date, status: DayStatus)`. Rules:
- `public_status(s)`: `ladies → rest`, others unchanged (the only projection teachers, aggregates and the DB's plain column ever see).
- `provisional_zone(locale)`: `ru → Europe/Moscow`, `en → UTC`. Used only to compute "today" while `account.timezone` is null; **never stored on the account** (per `06 Time Zones`: a guess is fine for logging, off by at most one day around midnight; never used for reminders).
- `local_today(now, zone)`; `latest_loggable(now, zone | None)`: the local today when the zone is known, else the date in `Pacific/Kiritimati` (UTC+14, the latest date on Earth) so a wrong guess never blocks a real "today".
- `check_loggable(day, now, zone)`: raises `DateInFuture` after `latest_loggable`, `DateTooEarly` before `MIN_LOG_DATE = 2000-01-01`. No floor at account creation (people backfill from paper journals).
- `check_range(start, end)`: `start ≤ end`, at most `MAX_RANGE_DAYS = 371` (a heatmap year plus a week), else `InvalidRange`.
- Moon day is a plain user choice: no check against computed calendars (MD-02 inheritance and per-location calendars don't exist yet; PR-09 will pre-mark).

**Application (`application/days.py`).** Port `DayLogRepository` (`application/ports/days.py`), exposed as `Storage.days` (and on `UnconfiguredStorage`): `upsert(account_id, day: DayLog, timezone: str | None) -> DayLog`, `delete(account_id, local_date) -> None`, `list_range(account_id, start, end) -> list[DayLog]`. Each is one statement. Use cases (all take a `Principal`, own data only; the bot builds `Principal(account)` from the middleware-injected account):
- `GetDays(principal, start=None, end=None) -> DaysView(today, timezone_known, days)`: defaults to the 7 days ending today.
- `SetDayStatus(principal, local_date, status) -> DayLog`: `check_loggable`, then `upsert` with `account.timezone` (null if provisional).
- `ClearDayStatus(principal, local_date) -> None`: idempotent.
No new policy function: every call is on the caller's own account (`/me/…`). Teacher reads (ST-06) will get a named policy that returns `public_status` only.

**Infrastructure.** `infrastructure/crypto.py`: `FieldCipher` (AES-GCM via `cryptography`, keyring from settings, ADR-0016). `infrastructure/db/days.py`: `SqlDayLogRepository(engine, cipher)` stores `status = public_status(s)` and, for every `rest` row, `sealed_status = seal(b"r" | b"l", aad=account_id ‖ date)`, so rest and ladies rows look identical in the DB (same column, same 30-byte length). Reads unseal rest rows in app code (a year has ≤ ~100; microseconds each); an unreadable seal (lost or retired key) degrades to `rest` with a warning carrying the account uuid only. Upsert = `INSERT … ON CONFLICT (account_id, local_date) DO UPDATE … RETURNING` (one round trip, idempotent, so Telegram retries are harmless and the in-memory `update_id` dedupe stays: ID-01 Q6 still holds). `cryptography` is imported by the cipher and preloaded in the lifespan (startup CPU boost), never per request.

**API (`api/v1/days.py`, initData auth as in ADR-0015).**

| Method, path | Request | Response |
|---|---|---|
| `GET /api/v1/me/days?from=&to=` (ISO dates, optional) | none | 200 `Days {today: date, timezone_known: bool, days: [{date, status}]}` (only logged days; `status` includes `ladies` for the owner); 422 `{code: "invalid_range"}` |
| `PUT /api/v1/me/days/{date}` | `{status: DayStatus}` | 200 `{date, status}`; 422 `{code: "date_in_future" \| "date_too_early"}` |
| `DELETE /api/v1/me/days/{date}` | none | 204 (also when nothing was logged) |

Plus the existing 401 / 503 codes. `ErrorCode` gains `invalid_range`, `date_in_future`, `date_too_early`. **CORS:** add `PUT` to `allow_methods` (today GET/POST/PATCH/DELETE).

**Bot (`bots/telegram/days.py` + `keyboards.py`).** Callback data, versioned prefix `d1:`, absolute dates (a keyboard tapped tomorrow still writes the date it shows), ≤ 16 bytes: `d1:s:20261018:p` set (codes `p r m l k t s`), `d1:x:20261018` clear, `d1:o:20261018` open the status screen, `d1:w:20261018` week page ending on that date. Unknown or malformed data → empty callback answer, nothing else. Per tap: the handler starts `answerCallbackQuery` as an outbound call first, runs the use case concurrently, awaits both, and returns `editMessageText` as the webhook reply (ADR-0012; nothing left running after the response). DB round trips: middleware SELECT + one statement (set/clear/range). `/log` and [Log today] → `GetDays(today, today)` to show the ✓. `Translator.t` accepts `date` args (Fluent `DATETIME`, Babel already bundled). Register `/log` and `/help` with `setMyCommands` in `tools/telegram/set_webhook.py`.

**Mini App.** Generated client (`npm run gen:api`); `useDays()` (`GET /me/days`, today only needed) and `useSetDay()` / `useClearDay()` with optimistic update and rollback on error; `TodayCard` on Home. No dates computed on the client: `today` comes from the server.

**Settings.** `field_encryption_keys: SecretStr | None` (`"<id>:<base64 32 bytes>[,…]"`, first = active). Unset (dev, tests without a key): the cipher raises `StorageUnavailable` on rest/ladies rows → bot `error-temporary`, API 503; prod refuses a `DATABASE_URL` without keys. `.env.example` documents generating a dev key.

## 4. Ops (☁️ owner only, in order; dry-run first)
1. Generate the key locally and keep a copy in your password manager (losing it turns past ladies' holidays into plain "rest"; nothing else is lost): `python3 -c 'import base64,secrets;print("1:"+base64.b64encode(secrets.token_bytes(32)).decode())'`.
2. `infra/gcp/bootstrap.sh` (dry-run, then apply): secret container `field-encryption-keys`, runtime SA → accessor on it only.
3. Add the value via stdin (`gcloud secrets versions add field-encryption-keys --data-file=-`), never pasted to an agent.
4. Merge: the migrate job applies `0002`, the service deploys with `FIELD_ENCRYPTION_KEYS=field-encryption-keys:latest`. Then `python3 tools/telegram/set_webhook.py` (commands menu).

## 5. Migration `0002_day_log`
`day_log(account_id uuid not null references account on delete cascade, local_date date not null, status text not null check in ('practiced','rest','moon','sick','travel','skipped'), sealed_status bytea null, timezone text null, created_at/updated_at timestamptz not null default now(), primary key (account_id, local_date), check ((status = 'rest') = (sealed_status is not null)), check (local_date >= '2000-01-01'))`. `'ladies'` is deliberately **not** a valid plain value. The PK serves every range query; no extra index. Text + CHECK (as 0001). Later, `practice(…, account_id, local_date)` references `day_log (account_id, local_date) on delete cascade` (1..n per day, `05 Domain Model`); PR-02 decides what a status change does to existing practices. Expand-only; downgrade drops the table.

## 6. Cross-cutting checks
- **Time zones:** a day is `date` + the zone used at logging (`timezone` null = provisional guess). "Today" is always computed server-side from `account.timezone`; the provisional zone is never written to the account. No times are displayed in this feature (dates only, RU `18 окт`, EN `Oct 18`), so the `07:00 Almaty (UTC+5)` label doesn't apply yet. Tests at midnight, `Asia/Kolkata` (+5:30), `Asia/Kathmandu` (+5:45), zone null, UTC+14 bound.
- **Privacy:** ladies' holiday never exists in plain text in the DB, logs or teacher-facing paths; DB dumps show "rest". The key lives only in Secret Manager + the owner's password manager. The bot chat is private; the confirmation reminds the user who sees what. Logs carry the account uuid, never statuses.
- **i18n:** all copy in `bot.ftl` / `app.ftl`, en/ru parity tests; dates via Fluent `DATETIME` with the account locale; no plurals needed yet.
- **Responsiveness:** a tap = 2 short DB statements (~2–6 ms) + one concurrent outbound `answerCallbackQuery`; edit via the webhook reply. `cryptography` preloaded at startup. Measure the image: **`cryptography` adds roughly 10 MB to a 242 MB image (budget 250)**, see Q4.

## 7. Test plan
- **Domain:** `public_status` (only ladies changes); `local_today` around midnight in Almaty, Kolkata, Kathmandu; `latest_loggable` with zone and with null (Kiritimati bound); `check_loggable` (today ok, tomorrow `DateInFuture`, 1999-12-31 `DateTooEarly`); `check_range` (reversed, 371 ok, 372 rejected); `provisional_zone` per locale.
- **Use case (in-memory fake repo, fixed clock):** set today; set yesterday; overwrite; clear twice; future rejected; provisional zone stored as null timezone; `GetDays` default window and `today`.
- **Cipher:** round trip; wrong AAD (other account / other date) fails; tampered byte fails; key rotation (old id still opens, new writes use the active id); `b"r"` and `b"l"` seals have equal length.
- **Infrastructure (real Postgres, `db` marker):** upsert insert/update in one statement; `ladies` lands as `rest` + seal (raw SQL check); rest rows without a seal rejected by the CHECK; `'ladies'` rejected by the CHECK; unreadable seal → `rest`; range query; cascade on account delete; upgrade → downgrade → upgrade; `alembic check`.
- **API contract:** 401 without auth; GET default window + `today`; PUT valid / future / too early / bad status (422); DELETE 204 twice; ladies round trip returns `ladies` to the owner; OpenAPI contains the new codes; CORS preflight allows PUT.
- **Bot handler (fake use cases):** `/log` builds the 7+1 keyboard with ✓ on the current status; each callback parses and calls the right use case; callback answered before the edit; malformed data ignored; `DateInFuture` → toast; zone hint shown only when the zone is null; every callback ≤ 64 bytes; en/ru keys exist.
- **Mini App (Vitest):** chips render the server status; tap sends PUT and highlights optimistically; rollback on error; `session-expired` on 401.
- **Architecture:** import-linter: `cryptography` only in `infrastructure`; domain stays pure; image size checked in the container smoke.

## 8. Open questions for the owner
1. **Where it ships:** bot (full flow incl. backfill) + API + a small Mini App "Today" card; Mini App backfill comes with the ST-01 heatmap? Recommended: yes.
2. **Unknown time zone:** compute "today" with a provisional zone from the locale (ru → Moscow, en → UTC), never store it, show the date in every confirmation plus a hint to open the app once? Recommended: yes (no extra question in the bot; the alternative, a zone picker in the bot, belongs to ID-06).
3. **Ladies' holiday storage:** plain `rest` status + an AES-GCM-sealed true status on every rest row, key in Secret Manager (ADR-0016), shipped in this feature? Recommended: yes. Fallback if the key setup must wait: hide the 🌸 button until it exists (never store it in plain text).
4. **Image budget:** `cryptography` likely pushes the image just past 250 MB. Raise the budget to 270 MB? Recommended: yes (the alternatives are a smaller, less standard library or our own construction on stdlib HMAC, which we shouldn't do).
5. **Who sees the 🌸 button:** everyone, in the same grid (no gender question, no setting)? Recommended: yes; a "hide this button" toggle can come with ID-06 settings.
6. **Skipped and streaks (ST-03):** the data separates practiced / rest-like (rest, moon, ladies, sick, travel) / skipped / not logged. Should Skipped break a streak, or only not extend it like a rest day? Recommended: ask the ashtanga-expert at ST-03; nothing in this feature depends on it.
7. **Sick/injury privacy:** treat it like the other statuses (visible to teachers later), not sealed? Recommended: yes for now; revisit with ST-06 privacy settings (the sealing pattern extends to it cheaply).
8. **Backfill floor:** any date from 2000-01-01, no floor at account creation? Recommended: yes.
9. **Labels:** "Skipped" → «Пропуск», "Ladies' holiday" → «Женские дни»? Recommended: let the ux-writer and ashtanga-expert settle them before release.

## 9. Decisions (owner, 2026-10-18) and changes to the text above
- §8 Q1–3, Q5, Q7, Q8: as recommended. Q6: decided with ST-03 (ashtanga-expert: unlogged days never count against you; "No practice" ends a run quietly, never "streak broken").
- **Q4 → PyNaCl, not `cryptography`.** Measured: `cryptography` +16 MB (image ~258 MB, over budget), PyNaCl +4.9 MB (~247 MB). Cipher: libsodium **XChaCha20-Poly1305 (IETF AEAD)** via `nacl.bindings`, which keeps the AAD binding of ADR-0016; 24-byte random nonces (no nonce-reuse risk). Sealed value = `key id (1) ‖ nonce (24) ‖ ciphertext+tag (1+16)` = 42 bytes for both `r` and `l`. Read "AES-GCM" above as this.
- **Copy (ashtanga-expert):** `status-skipped` "🌱 No practice" / «🌱 Без практики» (enum stays `skipped`); `status-moon` "🌙 Moon day" / «🌙 Лунный день»; `status-rest` "😌 Rest day" / «😌 День отдыха»; `status-sick` «🤒 Болезнь / травма»; `log-saved` cheers: practiced "Practice done 🙏" / «Практика сделана 🙏», rest/moon/ladies "Rest is part of the practice 🌿" / «Отдых — тоже часть практики 🌿», sick "Get well soon 🌿" / «Выздоравливай 🌿», travel "Safe travels ✈️" / «Хорошей дороги ✈️», skipped "Every day is different 🌱" / «Каждый день разный 🌱» (ux-writer dropped the leading "Saved." / «Сохранено.»: the line above already starts with ✓); `log-private-note` "Only you see this. Others see “Rest day”." / «Это видишь только ты. Остальные видят «День отдыха».»; `log-clear` RU «Убрать отметку». RU: no gendered past tense for the user; never «пропустил(а)», «прогул», «серия прервана», «лунные дни» for ladies' holiday.
- **Q (week view):** the week picker shows 😌 for a ladies' holiday; 🌸 appears only on that day's status screen.
- **RU ladies' label:** «🌸 Женские дни».

## 10. Implementation notes (deviations and review fixes, 2026-10-18)
- **Copy:** final wording is in the `.ftl` files (ux-writer polish on top of §9).
- **Dates in copy:** `fluent.runtime`'s `DATETIME` ignores weekday/day/month options, so `FluentTranslator` formats `DateArg(day, with_year)` with Babel (`MMMEd` / `yMMMEd`). The caller decides the year from the person's "today" (no server clock in the translator).
- **"Log today" under /start** (`d1:t`) opens the picker as a **new message**, so the greeting keeps its "Open the app" button. All other taps edit in place.
- **Errors in the bot:** a future date (`log-date-future`) or a date before 2000 (`log-date-too-early`) reshows the week picker with the real statuses and a note on top. Paging stops at 2000-01-01; callback data with dates outside [2000-01-01, date.max − 31 d] is ignored.
- **Clear** = one statement (no read-back). Unknown/old keyboards (other prefixes) get a silent `answerCallbackQuery`.
- **Seals:** truncated values are `UnreadableSeal` (→ rest), never a 500; DB CHECK `octet_length(sealed_status) = 42`; key ids must be ASCII digits.
- **Mini App:** after the device zone is reported, `me` is updated and the days query refetched ("today" may move); day mutations run one at a time (`scope`), so the last tap wins; the card shows `today-load-failed` if `/me/days` fails.
- **Image budget:** `uvicorn[standard]` → `uvicorn` + `uvloop` + `httptools` (no `websockets`; `watchfiles` dev-only). With PyNaCl the image is ~245 MB in CI (budget 250).
- **Measured locally** (Postgres 17, warm): `GET /me/days` p50 4 ms, `PUT` p50 14 ms (commit flush on a laptop disk).
