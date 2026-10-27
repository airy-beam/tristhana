# ST-09: export my data and delete my account

- Status: **accepted (owner, 2026-10-27)**; ashtanga-expert review applied · Date: 2026-10-27 · Size M, Phase 2
- Requirements: **ST-09** (export own data as CSV/JSON, delete the account), **NF-03** (GDPR-style export/delete). Covers every per-account table to date: ID-01/06 (account, identity, settings), PR-01..05 (`day_log`, `practice`), WH-01 (`rest_period`), PR-06 (`check_in`), PR-07 (`diary_note`), PR-08 (`progression`, `progression_event`), MD-03/PR-10 (`notification_settings`, `notification_delivery`).
- Related: ADR-0012 (webhook reply; direct Bot API calls when needed), 0015, 0016, 0018, 0021, 0023, 0025, 0026. New: **ADR-0027** (accepted).

## 1. Scope
**In:** one **"📦 My data"** place in the bot (`/settings` → screen D) and the Mini App (Settings card). **Export:** a ZIP with a versioned JSON (everything) plus CSVs (spreadsheet-friendly) and a localized README, sent by the bot to the person's chat as a document, from either side. **Delete:** two steps, then an immediate hard delete of the account and everything that cascades from it.
**Out:** a grace period / undo, a direct download in the Mini App (`downloadFile` + signed URL) and Cloud Storage links, partial deletes, import, scheduled or emailed exports, deleting the bot's old chat messages (Telegram allows it only within 48 h; we keep no message ids), per-account keys / crypto-shredding (§8), admin-initiated deletion, an inactivity retention rule, a new slash command, teacher/shala data (Phase 3 extends both lists, §3 guard), a "🌸 as rest" export variant (deferred to ST-06; for now the README is honest that 🌸 appears with its true value).
**Tone:** neutral and kind. No "we're sad to see you go", no retention nudges, no repeated "are you sure?". The export-first offer is one quiet button.

## 2. Domain (pure) `domain/export.py`
```python
SCHEMA = "tristhana.export/1"                     # bumped on any breaking change
@dataclass(frozen=True, slots=True)
class Snapshot:                                   # plain domain values, already opened
    account: Account; telegram_ids: tuple[str, ...]; settings: NotificationSettings
    days: tuple[ExportDay, ...]                   # ExportDay(date, status: DayStatus | None, zone, unreadable)
    periods: tuple[ExportPeriod, ...]             # (start, end, kind | None, unreadable)
    practices, check_ins, notes, reminders        # notes: (date, text | None, unreadable)
    progression: Progression | None; events: tuple[ExportEvent, ...]   # marked_by: MarkedBy
    exported_at: datetime                         # UTC
class MarkedBy(StrEnum): SELF = "self"; TEACHER = "teacher"; UNKNOWN = "unknown"   # never a name or id
EXPORT_STATUS = {..., DayStatus.SKIPPED: "no_practice"}   # export vocabulary; the rest map 1:1
def to_json(s: Snapshot) -> dict                  # §2a
def to_tables(s: Snapshot, labels: ExportLabels) -> dict[str, list[list[str]]]   # days, rest_periods, progression
def export_file_name(today: date) -> str          # "tristhana-export-2026-10-27.zip"
def check_rate(last: datetime | None, now) -> timedelta | None   # None = allowed; else the wait
EXPORT_EVERY = timedelta(minutes=10)
```
- `ExportLabels` is a port-free value object the use case fills from Fluent + catalog (domain stays pure): `status(code)`, `kind(event)`, `asana(key)`, `length(practice)`, `unreadable_rest`.
- **True values for the owner:** a sealed `rest` row opens to `ladies` or `rest`; a period kind opens to `ladies`/`sick`/`travel`. **Unreadable seals** (lost/retired key, ADR-0016): day `{"status": "rest", "unreadable": true}`, period `{"kind": null, "unreadable": true}`, note `{"text": null, "unreadable": true}`; CSV `unreadable = yes` and the label "Rest (details couldn't be read)". An unreadable value always says **rest, never guesses 🌸**. Nothing is dropped.
- **Stored facts only.** Day off, moon days and pause coverage are derived at read time (ADR-0022/0023) and are not rows; the export carries their inputs (day off with `since`/`before`, periods, moon city). `moon` in `days.csv` means "you logged this day as a moon day". Moon calendars are shared, not exported.
- **2a. JSON** (`data.json`, UTF-8, ISO dates, UTC instants with `Z`, wall times with their IANA zone): `schema`, `exported_at`, `catalog_version`, `account` {id, display_name, name_from_telegram, locale, locale_from_telegram, timezone, moon_city (resolved; `default: true` when unset), day_off {days (ISO weekday numbers, 1 = Monday … 7 = Sunday), since, before}, hide_ladies, offer_check_in, created_at, last_seen_at}, `identities` [{provider: "telegram", id, linked_at}], `notification_settings` (effective values), `days` [{date, status, status_label, unreadable}], `rest_periods`, `practices` (context, online, series, end, end_name, first_part, duration_min, start_time + timezone), `check_ins`, `diary`, `progression` {series, last, last_name, items} | null, `progression_events` (kind, kind_label, from, from_name, to, to_name, item, occurred_on, marked_by, created_at), `reminders` [{category, date, status}] (≤ 60 days). Keys stay machine names; `*_name`/`*_label` are in the account's language. **Not exported:** dedupe keys, attempt counts and internal guards (`last_event_id`, `hint_*`, `day_off_dismissed_at`, `moon_intro_sent_at`, `unreachable_at`, `export_claimed_at`).
- **2b. CSV** (UTF-8 **with BOM**, RFC 4180 quoting, notes keep line breaks):
  - `days.csv`, one row per date with any record: `date, status, status_label, unreadable, context, online, length, series, end, end_name, first_part, duration_min, start_time, timezone, mood, energy, effort, tags, note`. `status` ∈ practiced, rest, moon, ladies, sick, travel, **no_practice**; `status_label` reuses `status-*` (keys `status-practiced` … `status-skipped`, e.g. "🌱 No practice"/«🌱 Без практики», "🤒 Sick / injury"/«🤒 Болезнь / травма», "✈️ Travel"/«✈️ В дороге»). `end_name`: simple Latin in EN, the catalog's Cyrillic transliteration in RU. `first_part` ∈ `first_half`/`second_half`.
  - `rest_periods.csv`: `start, end` (inclusive), `kind, kind_label, unreadable`; labels from `status-ladies/sick/travel`, unreadable → `export-rest-unreadable`.
  - `progression.csv`: `occurred_on, kind, kind_label, from, from_name, to, to_name, item, marked_by, created_at`. Labels: start "Starting point"/«Начальная точка», given "New asana"/«Новая асана», changed "Correction"/«Исправление», item_given "Marked: { $item }"/«Отмечено: { $item }», item_removed "Unmarked: { $item }"/«Отметка снята: { $item }».
  - `README.txt` (`export-readme-*` lines, account's language), §6 copy.

## 3. Application and infrastructure
- Port **`ExportRepository`** (`application/ports/export.py`, on `Storage.export`): `snapshot(account_id) -> Snapshot` in **one read-only REPEATABLE READ transaction** (~9 PK-range SELECTs); seals opened in the adapter with the existing per-table AADs. `claim(account_id, now) -> datetime | None`: one statement (CTE with `UPDATE account SET export_claimed_at = :now WHERE id = :id AND (export_claimed_at IS NULL OR export_claimed_at < :now - interval '10 min')` plus a scalar read); None = claimed, else the earlier claim instant. `release(account_id)` sets it to NULL.
- `AccountRepository.delete(account_id) -> bool`: **one statement** `DELETE FROM account WHERE id = :id`; every per-account FK cascades; others' `progression_event.marked_by` → NULL.
- Port `Notifier.send_export(recipient, ExportFile(name, content, caption_key)) -> DeliveryResult`; the Telegram adapter (`bots/telegram/notifier.py`) calls `sendDocument` directly (ADR-0012), 20 s timeout. Packing (stdlib `zipfile`/`csv`/`json`, lazy-imported) in `infrastructure/export_zip.py` behind an `ExportPacker` port.
- Use cases `application/export.py`: **`SendMyExport(principal) -> ExportSent`** = claim → snapshot → labels → `to_json`/`to_tables` → pack → `send_export`; BLOCKED/FAILED → `release`, raise `BotUnreachable`/`ExportFailed`; `ExportTooSoon(wait)`; `ExportTooLarge` > 45 MB. **`DeleteMyAccount(principal) -> None`** (idempotent; logs `account deleted <uuid>` only). Same use cases for bot and API.
- **Policies** (`application/policies.py`): `can_export`, `can_delete_account` = self only.
- **Races with a delete:** a 23503 on an `*_account_id_fkey` maps to **`AccountGone`**: the tick's `claim` returns False, `mark_unreachable` no-ops, the API answers 410 `account_deleted`, the bot stays silent. A reminder claimed seconds before is still sent (at-most-once, ADR-0018; accepted).
- **Coverage guard (test):** every table with an FK to `account.id` is in `EXPORTED_TABLES` or `EXCLUDED_TABLES` (with a reason), and its FK is `CASCADE`/`SET NULL`.

## 4. API (initData auth; regenerate the client with `gen:api`)
| Method, path | Request → Response |
|---|---|
| `POST /api/v1/me/exports` | `{}` → 200 `ExportSentOut {file_name, bytes, sent_at}`; 429 `export_too_soon` (+ `retry_after_s`, `Retry-After`); 409 `bot_unreachable`; 413 `export_too_large`; 503 |
| `DELETE /api/v1/me` | `{confirm: "delete-everything"}` → 204; 422 `confirmation_required` |
- Auth runs `EnsureAccount`, so any call after a 204 creates a new empty account; the Mini App stops calling after the 204 (§6). No file over HTTP. `ErrorCode` += `export_too_soon`, `bot_unreachable`, `export_too_large`, `confirmation_required`, `account_deleted`.

## 5. Bot (prefix **`x1:`**, stateless; answer first, edit in place)
| Data | Meaning |
|---|---|
| `x1:o` | open D (new `/settings` row "📦 My data") |
| `x1:e` / `x1:e:x` | send the export (from D / from X, which is then re-shown) |
| `x1:d` | delete step 1: screen X (`delete-explain`, [⬇️ Download my data first] [Delete everything] [‹ Back]) |
| `x1:y:<a8>:<m>` | delete step 2; `a8` = first 8 hex of the account uuid, `m` = base36 unix minute of rendering |
- **D:** `data-intro`, [⬇️ Download my data], [Delete my account…], [‹ Back]. 0 statements.
- **Export tap:** `answerCallbackQuery(export-preparing)` first, then `SendMyExport`; the document arrives with `export-caption`; D is edited to `export-sent`. Too soon → toast `export-too-soon` only.
- **Delete:** `x1:y` only if `a8` matches the sender's account and `m` ≤ 10 min old; else X again with `delete-expired`. Then `DeleteMyAccount`, message edited to `delete-done`, **no keyboard**.
- **After:** any later message/tap silently creates a fresh empty account (ID-01); the Telegram id is not kept.
- Failures: DB outage or failed upload → `error-temporary` (claim released); malformed `x1:` ignored.

## 6. Mini App (`screens/settings/MyData.tsx`, lazy Settings chunk) and copy
- Card "📦 My data": [Download my data] → `POST /me/exports` (busy `export-sending`) → `export-sent-app` + success haptic; 429 → `export-too-soon`; 409 → `export-unreachable` + `openTelegramLink`.
- "Delete my account…" expands `delete-explain` + [Download my data first] + [Delete everything] → native **`showConfirm(delete-confirm-popup)`** → `DELETE /me`. On 204: a client flag rejects every further API call, `queryClient.clear()`, `localStorage.clear()`, standalone Done screen (`delete-done-app`, [Close] → `WebApp.close()`). ~+1 KB gzip.

**Copy (`bot.ftl`/`app.ftl`; «ты»; RU gender-neutral)**
- `settings-data-button`/`data-title` "📦 My data"/«📦 Мои данные» · `data-intro` "Download everything you've logged here, or delete your account."/«Здесь можно скачать все свои записи или удалить аккаунт.»
- `export-button` "⬇️ Download my data"/«⬇️ Скачать мои данные» · `export-preparing` "Preparing your file…"/«Готовлю файл…»
- `export-caption` "Your Tristhana data for { $date }: data.json for apps, CSV files for spreadsheets."/«Твои данные из Tristhana на { $date }: data.json для программ, CSV для таблиц.»
- `export-sent` "📦 Sent below. The file includes your private entries (diary notes, all day statuses): once it's saved, you can delete it from this chat."/«📦 Файл ниже. В нём есть личные записи (заметки, все отметки дней): когда сохранишь его, файл можно удалить из чата.» (no 🌸 in chat text)
- `export-too-soon` "A file was sent a moment ago. Again in { $minutes } min."/«Файл только что отправлен. Ещё раз — через { $minutes } мин.» · `export-unreachable` "Couldn't send the file to your chat. Open the bot, tap Start, then try again."/«Не получилось отправить файл в чат. Открой бота, нажми «Старт» и попробуй снова.»
- `delete-button` "Delete my account…"/«Удалить аккаунт…» · `delete-export-first` "⬇️ Download my data first"/«⬇️ Сначала скачать данные» · `delete-confirm` "Delete everything"/«Удалить всё»
- `delete-explain` "This deletes your account and everything in it, right away: days and rest pauses, practices, check-ins, diary notes, your asana progress and settings. It can't be undone.\n• Messages in this chat stay; you can clear the chat in Telegram.\n• Copies in our backups disappear within 30 days.\n• If you write to the bot again, it starts fresh."/«Аккаунт и всё, что в нём, удалятся сразу: дни и паузы, практики, самочувствие, заметки, прогресс в асанах и настройки. Отменить это нельзя.\n• Сообщения в этом чате останутся, их можно удалить в Telegram.\n• Из резервных копий данные исчезнут в течение 30 дней.\n• Если снова написать боту, всё начнётся с чистого листа.»
- `delete-expired` "This button is out of date. Here it is again."/«Кнопка устарела. Вот она снова.» · `delete-done` "Your account and data are deleted. Good practice to you. /start begins fresh any time."/«Аккаунт и данные удалены. Хорошей практики! /start — и всё начнётся заново.»
- App: `export-sending`, `export-sent-app` "Sent to your chat with the bot."/«Отправлено в чат с ботом.», `delete-confirm-popup` "Delete your account and all data? This can't be undone."/«Удалить аккаунт и все данные? Отменить нельзя.», `delete-done-app`, `delete-close`.
- Export labels: `export-rest-unreadable` "Rest (details couldn't be read)"/«Отдых (подробности не прочитать)»; `export-kind-start|given|changed|item-given|item-removed` (above); `export-marked-teacher` "teacher"/«учитель».
- **README** (`export-readme-*`, one key per paragraph): files list; "Only days you logged are listed. Your day off, moon days (by your city 📍 { $city }) and pause days are filled in by the app, so they aren't in the day list; pauses are in rest_periods.csv. Rest days are part of the practice."/«Здесь только дни с записями. Выходной, лунные дни (по городу 📍 { $city }) и дни паузы приложение заполняет само, поэтому их нет в списке дней; паузы — в rest_periods.csv. Дни отдыха — часть практики.»; "`moon` in days.csv means you logged that day as a moon day."; "Moon days follow your city's calendar (📍 { $city }); ask your teacher if your shala uses different dates."; "🌸 appears here with its true value, unlike in the app."; status codes with their labels; empty `series` = Short (sun salutations, standing, backbends optional, finishing); `first_part` first_half/second_half (RU «1-я/2-я половина первой»); context codes (`self` = Self-practice/«Самостоятельно», plus mysore/led/private from `context-*`); series 1–6 = Primary (1st), Intermediate (2nd), Advanced A–D (3rd–6th) / «Первая серия» … «Шестая серия»; `day_off.days` 1 = Monday … 7 = Sunday (named); `hide_ladies` = "hide the 🌸 button"; `marked_by` self/teacher/unknown; `unreadable = yes`.

## 7. Migration `0016_export_claim` (expand-only, down `0015`)
`ALTER TABLE account ADD COLUMN export_claimed_at timestamptz NULL`. Downgrade drops it. Deletion needs none.

## 8. Cross-cutting checks
- **Time zones:** dates stay local ISO `date`s, instants UTC `Z`, `start_time` with its own stored zone (never re-labelled), file name from the account's local today. Rate limit and confirm expiry use UTC instants. No time shown in copy, so no zone label.
- **Privacy:** decrypted for the owner only, sent only to the identity's own private chat; `export-sent` says the file holds private entries. No names in `marked_by`. **Logs:** update ids, counts, uuids only; Cloud Logging 30 days; one `account deleted <uuid>` line per deletion is the re-delete list after a restore. **Backups:** weekly `pg_dump` lifecycle **90 → 30 days** (☁️ owner changes `bootstrap.sh`/GCS; copy says 30); Supabase daily platform backups (no PITR on free). Runbook `infra/backup/README.md` gets the re-delete step. **Keys:** global keyring, no crypto-shredding.
- **i18n:** all copy and labels in `.ftl` (en/ru parity); JSON keys/CSV headers/codes English; labels, asana names (Latin EN, catalog Cyrillic RU) and README localized; `$minutes` abbreviated, no plurals.
- **Responsiveness:** D/X 0 statements; toast is the callback answer; export = claim + 1 tx + pack + one upload; delete = 1 statement. Heavy 25-year user ≈ 2 MB zipped, ~1 s; worst case (2000-char note daily) ~25 MB zipped, ~5 s, < 200 MB peak: within 50 MB upload, 60 s, 512 MiB.

## 9. Test plan (each bullet = one failing test first)
- **Domain `test_export.py`:** `to_json` has `schema == "tristhana.export/1"`; a `SKIPPED` day exports `status: "no_practice"` and no output anywhere contains `"skipped"`; `ladies` day/period keep their true value; unreadable day → `status "rest"`, `unreadable: true`, label = unreadable label, never `ladies`; unreadable period → `kind null`; unreadable note → `text null`; `marked_by` maps self/teacher/unknown and the event JSON has no other id or name; null progression → `null`; internal guard keys absent (assert the exact key set of `account`); `day_off.days` are 1–7. `to_tables`: headers exactly as §2b; one row per date (note-only day, practice without check-in, two records same date → one row); `status_label`/`kind_label`/`end_name`/`from_name`/`to_name` come from the `ExportLabels` passed in (RU fake → Cyrillic); `rest_periods` end inclusive; multiline + Cyrillic note round-trips through `csv.reader`; `check_rate` at 9:59 → wait 1 s, at 10:00 → None; `export_file_name` from local date (Kiritimati vs Honolulu, same instant → two dates).
- **Packer:** ZIP holds exactly `data.json, days.csv, rest_periods.csv, progression.csv, README.txt`; CSVs start with BOM; README in the account's language contains the moon city.
- **Use case (fakes, fixed clock):** second call within 10 min raises `ExportTooSoon(wait)`; BLOCKED → `release` called + `BotUnreachable`; FAILED → `release` + `ExportFailed`; success keeps the claim; oversize → `ExportTooLarge`, nothing sent; RU account → labels in RU; `DeleteMyAccount` twice → no error; policies refuse another account.
- **DB (real Postgres):** `snapshot` opens seals (ladies day, sick period, note) and keeps unreadable ones; another account's rows never appear; two concurrent `claim`s → exactly one None; `release` → next claim succeeds; `delete` removes the account's rows in **every** table, leaves a second account intact, NULLs others' `marked_by`; tick `claim` after delete → False, nothing sent; **coverage guard** over `metadata`; 0016 up/down/up; `alembic check`; app role may DELETE `account`.
- **API:** 401 without initData; export 200 (fake notifier gets a ZIP whose `data.json` validates and whose CSVs parse), 429 with `Retry-After`, 409, 413; DELETE without/with confirm → 422/204; a write racing the delete → 410 `account_deleted`; OpenAPI lists the codes; TS client builds.
- **Bot (fake use cases):** `/settings` shows the My data row; D/X render with 0 statements; export answers the callback before the use case runs, then edits D to `export-sent`; too soon → toast only, no edit; `x1:y` with a foreign `a8` or minute > 10 old → X with `delete-expired`, delete not called; valid → `delete-done`, `reply_markup` None; every `x1:` ≤ 64 bytes and round-trips; malformed ignored.
- **Mini App (Vitest):** busy/sent/429/409 (bot link) states; `showConfirm` cancel → no request; confirm → DELETE, then zero further requests, cache and localStorage cleared, Close → `WebApp.close()`; bundle check.
- **i18n/architecture:** every new key in en and ru, formats with sample args; RU `export-*`/`delete-*` have no gendered past-tense endings (`-ла`/`-л ` grep on verbs listed); avoid-word grep over new copy and README: sad, miss you, sure?, unlocked, level up, skipped, жаль, уверен, открыта серия, пропуск; `export-sent` has no 🌸; import-linter (aiogram only in `bots/telegram`, `domain/export.py` pure).

## 10. Decisions (owner, 2026-10-27; all as recommended)
1. ZIP: `data.json` + `days.csv`, `rest_periods.csv`, `progression.csv` + localized README.
2. The bot sends the document to the chat, also when the Mini App asks.
3. Two-step confirm: bound 10-min bot button; Telegram native confirm in the Mini App; no typed word.
4. Immediate hard delete; no grace period.
5. One export per 10 min per account, released if sending fails.
6. Later taps/messages silently create a fresh empty account; the Telegram id is not kept.
7. Delivery ledger exported as `reminders` (category, date, status, ≤ 60 days); no internal guard fields.
8. Weekly dump lifecycle 90 → 30 days (owner does the cloud change); copy says 30 days.
9. Entry points: `/settings` → 📦 My data and a Mini App Settings card; no new slash command.
10. "🌸 as rest" export variant deferred to ST-06; honest README copy now.
11. Export schema renames `skipped` → `no_practice`.

## 11. Implementation notes (2026-10-27, after code review)
- **One answer per tap:** `SendMyExport.execute(principal, claimed)` runs `claimed` once the slot is taken; the bot answers "Preparing…" there, or "too soon" as the only answer.
- **Stale claim:** a claim that waited on another claim's row lock loses with its snapshot's old instant; the use case then applies the whole 10-minute window.
- **Slot release:** any failure after the claim frees the slot (unreachable, failed upload, storage, a bug), except "too large" (retrying can't help).
- **Delete button window:** `0 ≤ now − m < 10` unix minutes (never more than 10 minutes).
- **Mini App 409:** no bot username is configured, so instead of `openTelegramLink` the app asks Telegram's `requestWriteAccess` and sends once more if allowed; otherwise `export-unreachable`.
- **Mini App delete:** while the DELETE is in flight every other request is blocked and queries are cancelled; a 410 `account_deleted` from any request also switches to the Done screen (shown in the launch language).
- **Logs:** `account deleted <uuid>` at WARNING (survives any LOG_LEVEL); the runbook restores only dumps younger than 29 days.
- **Labels:** `application/labels.py` (`PracticeLabels`) now owns length/asana/item names for the bot and the export.
