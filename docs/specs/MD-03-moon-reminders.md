# MD-03 + MD-01 (storage) + NT-01/NT-02 (moon part): moon days and reminders

- Status: accepted (owner 2026-10-19; §9 overrides earlier text) · Date: 2026-10-19
- Requirements: **MD-03** (reminders 7/3/1 days before, configurable), **MD-01** (pre-computed, stored calendars per location; the module is already verified), **NT-01** (moon category toggle), **NT-02** (quiet hours, max-per-day cap, friendly copy), **ID-06** (the "moon-day calendar" profile field only), **NF-06** (retry-safe notifications). Prepares **PR-10** (the practice reminder reuses the machinery), PR-09, ST-01, SC-06. Budget: < 300 ms p50 per tap (warm).
- Related: ADR-0005 (time), 0006/0009 (moon algorithm, AGPL), 0008 (stateless callbacks), 0011 (Cloud Run), 0012 (webhook reply), 0014, 0017 (data in memory). New: **ADR-0018** (notifications on a scheduler tick; Proposed), **ADR-0019** (moon locations: curated cities + stored calendars; Proposed).

## 1. Scope
**In:** a curated city list `data/seed/cities.yaml` (in memory); stored calendars for every listed city (`moon_calendar`, `moon_day`), filled by the tick; the account's moon location (default **Mysuru**); moon reminders 7/3/1 days before at a chosen local hour; quiet hours and a daily cap (stored, applied, API-editable); a bot `/moon` screen (next moon days, city picker, reminder settings) and quick buttons on each reminder; `POST /internal/tick`; `GET /api/v1/me/moon-days`, `GET /api/v1/moon/cities`, `PUT /api/v1/me/moon-location`, `GET/PUT /api/v1/me/notification-settings`; a Mini App **Moon card** on Home and a "today is a moon day" line on the Today card.
**Out:** MD-02 inheritance (teacher/shala, Phase 3), MD-04 FYI on differences, MD-05 SYC import (the schema leaves room: a `source` column later), PR-09 auto-fill, PR-10/NT-01 practice reminder (reuses §3's machinery: a new category + columns), own coordinates / "Share location" (needs `timezonefinder`, tens of MB; image is at ~245/250), the ID-06 settings page (quiet hours/cap UI), a weekday-off rule (07 open question).
**Cut if time is short:** the Mini App city select and reminder chips (the bot and API cover them).

## 2. Flows and copy
- **`/moon`** (also in `/help` and the command menu) → screen **M**: "🌙 Moon days · 📍 Mysuru" then the next 4 (≈ 2 months): "🌕 Full moon · Wed, Nov 5 · in 3 days", "🌑 New moon · Thu, Nov 20", … Below: "🔔 Reminders: 7, 3 and 1 day before, at 19:00 Almaty (UTC+5)" or "🔕 Reminders off", or, with no known zone, `moon-zone-needed`. Buttons `[📍 Change city] [🔔 Reminders]`.
- **City picker C:** `[🕉 Mysuru (SYC)]` on top, then the other cities by localised name, 2 columns × 6 per page, `‹ ›`, `[‹ Back]`. Tap = save, back to M (edited in place). If the account zone is unknown and the city isn't Mysuru, M adds `moon-use-city-zone` "Use Almaty time (UTC+5) for reminders?" `[Yes] [No]` (06 Time Zones, "from context"; Yes = `set_timezone_if_unset`, an explicit choice, never a guess). Picking Mysuru never sets a zone (you may follow Mysuru from anywhere).
- **Reminders screen R:** `[✓ 7 days] [✓ 3 days] [✓ 1 day]` (each a toggle) · `[07:00] [12:00] [19:00] [21:00]` (✓ on the current) · `[🔕 Turn off]` / `[🔔 Turn on]` (on = 7·3·1) · `[‹ Back]`. With no zone: the toggles still save, plus `moon-zone-needed` ("To remind you at the right hour I need your time zone: pick your city or open the app once.") and `[📍 Pick your city] [Open the app]`.
- **A reminder** (a new message, sent by the tick): text by offset, then `[Only the day before] [🔕 Turn off] [🌙 All moon days]`. A tap re-renders the same reminder text (from the callback data) plus a status line ("✓ I'll only remind you the day before." / "🔕 Moon reminders are off. Turn them on in /moon."), with `[🔔 Turn back on]` after Turn off. The first reminder an account ever gets adds `moon-reminder-intro` ("I remind you 7, 3 and 1 day before each moon day. One tap below changes it.").
- **Mini App:** Home gets a **Moon card** under Today: the next 3 moon days (phase, date, "in N days"), "📍 Mysuru · Change" (native `<select>`), and "🔔 7 · 3 · 1 days before · 19:00 Almaty (UTC+5)" with three toggle chips (hidden while the zone is unknown, with `moon-zone-needed-app`). The Today card shows "🌕 Today is a full moon · 📍 Mysuru" when it is one (no auto-fill; the 🌙 chip stays a choice).
- **Failures:** unknown city slug → `moon-city-unknown` (API 422 `unknown_location`); a calendar not computed yet → `moon-calendar-pending` ("The moon calendar is being prepared, try again in a few minutes."); DB down → `error-temporary`.
- **Copy (new keys; ux-writer polishes; RU «ты», no case-inflected city names: the location is always "📍 City"; ashtanga-expert checks the marked ones ⚑).** `bot.ftl`: `moon-title` ("🌙 Moon days · 📍 { $city }"), `moon-phase` (selector `$phase`: purnima "🌕 Full moon"/«🌕 Полнолуние», amavasya "🌑 New moon"/«🌑 Новолуние») ⚑, `moon-day-line` ("{ $phase } · { $date }{ $in }"), `moon-in-days` (plural: "in { $n } days"/«через { $n } день/дня/дней»; 0 "today"/«сегодня», 1 "tomorrow"/«завтра»), `moon-reminders-on` ("🔔 Reminders: { $offsets } before, at { $time }"), `moon-reminders-off`, `moon-offsets` (selector over `731`, `73`, `71`, `31`, `7`, `3`, `1`: "7, 3 and 1 day"/«за 7, 3 и 1 день» …), `moon-change-city`, `moon-reminders`, `moon-turn-on`, `moon-turn-off`, `moon-only-day-before`, `moon-all-days`, `moon-mysuru-syc` ("🕉 Mysuru (SYC)"/«🕉 Майсур (SYC)»), `moon-use-city-zone`, `moon-zone-needed`, `moon-city-unknown`, `moon-calendar-pending`, `moon-reminder` (selector `$days`) ⚑:
  - 7: "{ $phase } in a week: { $date } · 📍 { $city }" / «{ $phase } через неделю: { $date } · 📍 { $city }»
  - 3: "{ $phase } in 3 days: { $date } · 📍 { $city }. A rest day for the practice." / «{ $phase } через 3 дня: { $date } · 📍 { $city }. В этот день практики нет, это отдых.»
  - 1: "{ $phase } tomorrow, { $date } · 📍 { $city }. Enjoy the rest 🌿" / «Завтра { $phase-lower }, { $date } · 📍 { $city }. Хорошего отдыха 🌿»
  `moon-reminder-intro`, `moon-reminder-only-1`, `moon-reminder-off`, `moon-turn-back-on`. Dates via `DateArg` (year only when not this year), the hour via `TimeArg`. City names come from `cities.yaml` (en/ru), never `.ftl`. `app.ftl`: `moon-card-title`, the shared keys, `moon-today` ("{ $phase } today · 📍 { $city }"), `moon-zone-needed-app`, `moon-save-failed`.
  ⚑ Expert questions: does a reminder say why (Purnima/Amavasya, tradition) or just "rest day"; 🌕/🌑 vs PR-01's 🌙; "no practice" vs "rest"; mention Purnima/Amavasya by name (e.g. "Full moon (Purnima)") in /moon only?

## 3. Design
**Domain (pure).** In `domain/moon.py`: `City(slug, names: Mapping[Locale, str], location: MoonLocation)`, `Cities` (in-memory directory: `get(slug)`, `default` = `mysuru`, ordered by locale name), `calendar_years(today) -> range` = **previous year … current + 2** (Q9), `ALGO_VERSION` is built in infrastructure. New `domain/notifications.py`:
- `QuietHours(start: time, end: time)`: may wrap midnight; `start == end` = none; `contains(local_time)`.
- `MoonReminders(offsets: frozenset[int] ⊆ {1, 3, 7}, at: time)`: empty = off. `NotificationSettings(moon: MoonReminders, quiet: QuietHours, daily_cap: int 1..10)`; `DEFAULTS` = 7·3·1 at **19:00**, quiet **22:00–07:00**, cap **3** (Q6). `at` on a 15-minute grid.
- `send_instant(local_date, at, zone) -> datetime (UTC)`: wall clock + IANA zone; a DST gap moves forward (`fold=0` round trip), an ambiguous time takes the first occurrence.
- `due_moon_reminders(now, zone, settings, moon_days, sent_keys, sent_today) -> list[DueReminder(key, moon_day, days_before, local_date)]`. For each moon day D (a **date of the calendar's location**, applied as the same date in the user's zone, as people do when they follow Mysuru abroad) and k in offsets: `send_at = send_instant(D − k, at, zone)`; due iff `send_at ≤ now < send_at + GRACE (3 h)`, `now` local isn't in quiet hours, the key `moon:{D}:{k}` isn't in `sent_keys`, and the cap allows it (`sent_today` + earlier picks < cap; smaller k first). Nothing is sent for a moon day ≤ local today.

**Application.** Ports (`application/ports/moon.py`, `notifications.py`), exposed on `Storage` (and `UnconfiguredStorage`) as `moon` and `notifications`:
- `MoonCalendarRepository`: `days(location, start, end)`, `coverage() -> {(location, year): algo_version}`, `replace_year(location, year, days, algo_version)`.
- `MoonCalculator` (port; `infrastructure/moon_calc.py` wraps `tristhana.moon` in `asyncio.to_thread`, one city-year per call so webhook requests interleave): `compute_year(location, year) -> list[MoonDay]`, `version: str` (port version + pyswisseph + tzdata).
- `NotificationRepository`: `settings(account_id)`, `update(account_id, patch) -> NotificationSettings`, `moon_candidates(utc_today, defaults) -> list[MoonCandidate]`, `claim(account_id, key, category, local_date) -> bool`, `finish(account_id, key, status)`, `mark_unreachable(account_id, at)`, `prune(before)`.
- `Notifier` (port; implemented by `bots/telegram/notifier.py`, so `application` stays aiogram-free): `deliver(recipient: Recipient(provider, provider_user_id, locale), n: Notification) -> DeliveryResult` (`sent | blocked | retry_after(s) | failed`). `Notification` is semantic (`MoonReminder(moon_day, days_before, city, intro)`); the adapter renders text and keyboard with the Translator and its callback codec. PR-10 adds `PracticeReminder`.
Use cases (Principal, own data only): `GetMoonView(principal, start, end) -> MoonView(city, explicit, days, settings, zone_known)`; `SetMoonLocation(principal, slug)`; `UpdateNotificationSettings(principal, patch)` (the bot sends one field per tap); `RunTick(now, deadline)` = `SendDueReminders` (candidates → domain → claim → deliver → finish; stops at the deadline or on `retry_after`; `failed` retried by later ticks, ≤ 3 attempts, within the grace) then `TopUpMoonCalendars` (missing or outdated city-years in `calendar_years`, until the deadline) then `prune(60 days)`.

**Infrastructure.** `infrastructure/seed/cities_yaml.py` loads `cities.yaml` in the lifespan (strict, like the catalog; the 10 golden-fixture cities use the fixtures' exact coordinates). Repos, one statement each on AUTOCOMMIT, except `replace_year` (job path only: one transaction of upsert + delete-not-in + ledger upsert):
- `moon_candidates`: accounts with a zone, a Telegram identity, moon reminders on (`s.moon_offsets IS NULL` = default) and not unreachable (`unreachable_at IS NULL OR unreachable_at < last_seen_at`), joined to `moon_day` of `coalesce(moon_location, 'mysuru')` for dates `utc_today − 1 … utc_today + 9`, with the account's recent dedupe keys and today's sent count as subqueries. ~2 rows per account; fine to ~10k accounts, then filter by send hour in SQL.
- `claim`: `INSERT … ON CONFLICT DO NOTHING RETURNING` (a retry: `UPDATE … SET status='claimed', attempts=attempts+1 WHERE status='failed' AND attempts < 3 RETURNING`). Claim **before** sending: at most once, also across 2 instances or a scheduler retry.
- `GetMoonView`: one statement (days + settings via a scalar subquery). `SetMoonLocation`: `UPDATE account`. Settings: upsert `RETURNING`.

**Tick (`jobs/tick.py`, ADR-0018).** `POST /internal/tick` (hidden from OpenAPI), mounted when `INTERNAL_TICK_TOKEN` is set. Auth: header `X-Tristhana-Tick-Token`, `hmac.compare_digest`, mismatch → 404. All work happens **inside the request** (CPU is throttled after it): deadline 40 s (service timeout 60 s). Sending: ≤ 8 concurrent, paced to ≤ 25 msg/s (Telegram ~30/s). Telegram 403 / "chat not found" → `mark_unreachable` (the daily `last_seen_at` write clears it when the person comes back); 429 → stop, rest next tick. Response `{sent, skipped, failed, computed}`. Logs: counts and account uuids only. The scheduler runs it **every 10 min** and it **replaces the keep-warm job** (it pings the DB too): still 2 of 3 free jobs. Kathmandu 19:00 = 13:15 UTC → sent at 13:20 (≤ 10 min late).

**API.**

| Method, path | Request | Response |
|---|---|---|
| `GET /api/v1/moon/cities` (public) | none | 200 `[{slug, names{en,ru}, timezone}]`, `ETag`, `Cache-Control: public, max-age=3600` |
| `GET /api/v1/me/moon-days?from=&to=` | ISO dates; default today … +60 d; max 371 d | 200 `{location: {slug, explicit}, coverage_end, days: [{date, kind}]}`; 422 `invalid_range` |
| `PUT /api/v1/me/moon-location` | `{slug: str \| null}` (null = default Mysuru) | 200 `{slug, explicit}`; 422 `unknown_location` |
| `GET /api/v1/me/notification-settings` | none | 200 `{moon: {offsets, at: "HH:MM"}, quiet: {start, end}, daily_cap, timezone}` |
| `PUT /api/v1/me/notification-settings` | the same (all fields) | 200 same; 422 `invalid_settings` |

`kind` keeps `kshaya_*` (clients show the phase). Zone-from-city in the Mini App isn't needed (the device reports it).

**Bot** (`bots/telegram/moon.py`, `moon_callbacks.py`, prefix **`m1:`**, same tap protocol as PR-01/02: answer in parallel, edit as the webhook reply).

| Data | Meaning | Max bytes |
|---|---|---|
| `m1:v` / `m1:r` | screen M / R | 4 |
| `m1:c:2` | city picker page | 6 |
| `m1:s:<slug>` / `m1:z:<slug>` | set city / use its zone | 29 (slug ≤ 24, checked at load) |
| `m1:o:7` | toggle offset 7 (`1 3 7`; `0` off, `a` on) | 6 |
| `m1:t:1900` | send time | 9 |
| `m1:q:20261105:a:3:1` | from a reminder: date, phase, k, action (`1` only day before, `0` off, `a` back on) | 19 |

Round trips per tap: middleware SELECT + one statement; the city picker needs none (in memory).

**Mini App.** `useMoonDays()`, `useMoonCities()` (staleTime ∞), `useNotificationSettings()` + optimistic `useSaveNotificationSettings()` / `useSetMoonLocation()` (scope `"settings"`). `MoonCard` on Home; `TodayCard` reads `useMoonDays` for today. No new libraries; ~+3 KB gzip (now 108/150).

## 4. Ops (☁️ owner only, in order; dry-run first)
1. `infra/gcp/bootstrap.sh` (dry-run, then apply): secret container `internal-tick-token` + runtime SA accessor. The job step is skipped while the secret has no version.
2. Add the value via stdin, never pasted to an agent: `python3 -c 'import secrets;print(secrets.token_urlsafe(32))' | gcloud secrets versions add internal-tick-token --data-file=-`.
3. Merge: migrate applies `0004`, deploy adds `INTERNAL_TICK_TOKEN=internal-tick-token:latest`.
4. `bootstrap.sh` again: creates job `tristhana-tick` (`*/10 * * * *`, `POST <service>/internal/tick`, `--attempt-deadline 60s`; the header value is read from Secret Manager inside the script and shown as `***` in dry-run). Check the first tick's log (`computed` ≈ 140 city-years), then **delete `tristhana-keepwarm`**. Run `python3 tools/telegram/set_webhook.py` (adds `/moon` to the menu).

## 5. Migration `0004_moon_notifications`
- `account.moon_location text null check (moon_location ~ '^[a-z0-9-]{1,24}$')` (null = default Mysuru; no FK, cities are in memory).
- `moon_calendar(location text, year smallint, algo_version text not null, computed_at timestamptz not null default now(), primary key (location, year))`.
- `moon_day(location text, date date, kind text not null check in ('purnima','amavasya','kshaya_purnima','kshaya_amavasya'), primary key (location, date))`. MD-05 adds `source`.
- `notification_settings(account_id uuid primary key references account on delete cascade, moon_offsets smallint[] null check (moon_offsets <@ '{1,3,7}'), moon_at time null, quiet_start time null, quiet_end time null, daily_cap smallint null check between 1 and 10, unreachable_at timestamptz null, updated_at)`. A missing row or null column = the domain default (one source of truth, passed as parameters).
- `notification_delivery(account_id uuid references account on delete cascade, dedupe_key text, category text not null check in ('moon'), local_date date not null, status text not null check in ('claimed','sent','failed','blocked'), attempts smallint not null default 1, created_at/updated_at, primary key (account_id, dedupe_key))`. Pruned after 60 days.
Expand-only; downgrade drops the tables and the column.

## 6. Cross-cutting checks
- **Time zones:** moon dates are the calendar location's local dates; reminders fire at wall clock + the **account zone** (ADR-0005), recomputed every tick, so DST and zone changes need no rewrite. The provisional zone is **never** used: no zone, no reminders (the city's zone only after an explicit Yes). Every shown hour has the label (`TimeArg`). Tests: Kolkata +5:30, Kathmandu +5:45, Berlin across DST (19:00 = 17:00 or 18:00 UTC; a 02:30 gap), Los Angeles following Mysuru, quiet hours wrapping midnight, a user east of the date line.
- **Privacy:** only a city-level slug is stored, never coordinates. Reminders carry no personal data; the ledger stores dedupe keys only. Logs: account uuid and counts, never chat ids or text. Account delete cascades.
- **i18n:** all copy in `bot.ftl`/`app.ftl` with en/ru parity; RU plurals via Fluent `NUMBER`; city names from YAML in both locales; no case-inflected city names.
- **Responsiveness:** taps = middleware + ≤ 1 statement; picker screens pure CPU. Moon computation never runs on a tap path; in the tick, one city-year per thread hop. No new dependency (no `google-auth`, no `timezonefinder`): image stays ~245/250 MB.
- **Cost:** no new scheduler job (net 2 of 3), the same request count as the keep-warm ping, ~3.5 k `moon_day` rows. **Compute not measured in this session** (no shell); MD-01 estimated ~0.1 s per city-year → ~14 s once for 35 cities × 4 years, then ~4 s each January. Measure as the first TDD step; if far slower, cap city-years per tick.

## 7. Test plan
- **Domain:** `QuietHours` (wrap, none, edges); `send_instant` (+5:30, +5:45, Berlin gap and fold); `due_moon_reminders`: exact send minute, 9 min late, after grace, in quiet hours, already sent, cap (k=1 wins), offsets empty, a moon day today, the same Amavasya on 18 Mar (Moscow) vs 19 Mar 2026 (Mysuru) giving different send dates; `calendar_years` across New Year; `Cities` ordering per locale, slug ≤ 24.
- **Use case (fakes, fixed clock):** tick claims then delivers; a lost claim isn't sent; `blocked` marks unreachable; `retry_after` stops the batch; `failed` retried up to 3; deadline respected; top-up computes only missing/outdated years and swaps a version; intro only on the first reminder; `SetMoonLocation` rejects unknown slugs; zone-from-city only when unset.
- **Infrastructure (real Postgres):** candidate query (default row absent, offsets empty, unreachable vs last_seen, location default), claim race (two claims, one wins), `replace_year` replaces atomically, CHECKs, upgrade → downgrade → upgrade, `alembic check`. **Moon parity:** stored calendars of the 10 fixture cities equal the golden fixtures; every city in `cities.yaml` computes current … +2 without `NoSunriseError` (no polar city ships).
- **API contract:** cities public + ETag; moon-days default window, range 422, `coverage_end`; moon-location 422; settings round trip and 422s; `/internal/tick` 404 without or with a wrong token, 200 with it, absent from OpenAPI.
- **Bot handler (fake use cases, fake notifier):** M with and without zone; picker paging; `m1:z` shown only when the zone is unknown and the city isn't Mysuru; toggles; reminder quick actions re-render the reminder; malformed data ignored; **every callback ≤ 64 bytes over all cities**; notifier maps aiogram errors to `DeliveryResult`; en/ru keys exist.
- **Mini App (Vitest):** Moon card lists days; the select saves optimistically and rolls back; chips hidden without a zone; the Today line on a moon day.
- **Architecture:** import-linter (aiogram only in `bots`, `swisseph` only in `moon`, `yaml` only in infrastructure); bundle check; container smoke loads `cities.yaml`.

## 8. Open questions for the owner
1. **Scope** as §1 (stored calendars for a city list, reminders, `/moon`, Mini App Moon card; inheritance, FYI, SYC import, auto-fill and share-location later)? Recommended: yes.
2. **On by default** (7·3·1 for everyone with a known zone, an intro line on the first reminder, one-tap "Only the day before" / "Turn off" on every reminder) rather than an opt-in question? Recommended: yes. It's ~6 short messages a month and the core value of MD-03; an unanswered opt-in loses most people.
3. **Default calendar Mysuru** (every message names "📍 Mysuru"), the user picks their city in `/moon`; no automatic city from the zone? Recommended: yes (explicit, matches "no teacher → own city if known, else Mysuru").
4. **City list:** Mysuru + the 9 other fixture cities + ~25 common ones (e.g. Tbilisi, Yerevan, Bishkek, Tashkent, Kazan, Sochi, Kaliningrad, Riga, Tallinn, Vilnius, Warsaw, Berlin, London, Lisbon, Barcelona, Istanbul, Limassol, Belgrade, Dubai, Goa, Bangkok, Bali, New York, Los Angeles); no own coordinates or "Share location" now? Recommended: yes; send me cities to add.
5. **Zone from a city:** when the zone is unknown, offer "Use Almaty time for reminders?" after a city pick (never for Mysuru)? Recommended: yes.
6. **Timing defaults:** 19:00 local (the evening before for the 1-day reminder), chips 07/12/19/21; quiet hours 22:00–07:00; cap 3/day; a reminder more than 3 h late is dropped; quiet hours and cap editable via API now, UI with ID-06? Recommended: yes.
7. **Scheduler:** one tick every 10 min that **replaces the keep-warm job** (2 of 3 free jobs stay used)? Recommended: yes. Alternative: a third job, keeping keep-warm separate.
8. **Tick auth:** a secret header from Secret Manager (no new dependency) instead of verifying a Scheduler OIDC token (`google-auth` + an outbound cert fetch, ~2–3 MB at 245/250)? Recommended: header (ADR-0018); the value is visible only to project viewers (you).
9. **Stored window:** previous year … current + 2 (adds the previous year so ST-01's 12-month heatmap has moon markers), instead of current + 2? Recommended: yes.
10. **Delivery:** at most once (claim before send), ≤ 3 attempts on transient errors, blocked bot → paused until you write to the bot again? Recommended: yes.
11. **Copy ⚑** for the ashtanga-expert: reasons in reminders, 🌕/🌑 vs 🌙, "rest" vs "no practice", Purnima/Amavasya names. Recommended: expert + ux-writer settle before release.
12. **Moon day on the weekly day off** (07 open question) and **open question 10** (SYC kshaya Amavasya): no effect on this feature; reminders fire as computed. Recommended: leave open until PR-09 / MD-05.

## 9. Decisions (owner + ashtanga-expert, 2026-10-19): override the text above
- Q1, Q2, Q4–Q11 as recommended. **Default offsets 7 + 1** (3 days optional; expert: 7·3·1 ≈ 6 messages a month is the noisy end; the 1-day reminder matters most). `DEFAULTS` = offsets {7, 1} at 19:00.
- **Q12 / city picker:** "📍 Mysuru" / «📍 Майсур» on top, no 🕉, no "(SYC)" until MD-05 imports the official calendar (computed dates can differ, e.g. 2025-02-27 vs 28). Use "Mysuru" for the city, "Mysore" only for "Mysore style".
- **Copy (expert):**
  - `moon-phase`: purnima "🌕 Full moon" / «🌕 Полнолуние»; amavasya "🌑 New moon" / «🌑 Новолуние». New `moon-phase-long` (only /moon and the Mini App card): "🌕 Full moon (Purnima)" / «🌕 Полнолуние (Пурнима)», "🌑 New moon (Amavasya)" / «🌑 Новолуние (Амавасья)». 🌙 stays the category (title, status label, "All moon days").
  - `moon-title`: "🌙 Moon days · 📍 { $city }" / «🌙 Лунные дни · 📍 { $city }».
  - `moon-reminder` 7: "{ $phase } in a week: { $date } · 📍 { $city }" / «{ $phase } через неделю: { $date } · 📍 { $city }»; 3: "{ $phase } in 3 days: { $date } · 📍 { $city }. A traditional rest day." / «{ $phase } через 3 дня: { $date } · 📍 { $city }. Традиционный день отдыха.»; 1: "{ $phase } tomorrow, { $date } · 📍 { $city }. Enjoy your rest 🌿" / «Завтра { $phase-lower }, { $date } · 📍 { $city }. Хорошего отдыха 🌿».
  - `moon-reminder-intro` (the reason, once): "In Ashtanga we traditionally rest on full and new moon days. I'll remind you a week and a day before; one tap below changes it." / «В аштанге в полнолуние и новолуние традиционно не практикуют. Я напомню за неделю и за день, изменить можно одной кнопкой ниже.»
  - `moon-calc-note` (on /moon): "Dates are calculated for 📍 { $city } (lunar day at sunrise). Your shala's calendar may differ by a day; follow your teacher." / «Даты рассчитаны для 📍 { $city } (лунный день на восходе). Календарь твоей шалы может отличаться на день, ориентируйся на своего учителя.»
  - `moon-today` (Today card): "{ $phase } today · 📍 { $city }" / «Сегодня { $phase-lower } · 📍 { $city }».
  - Never "kshaya" in user copy; no special copy for a moon day on the weekly day off; nothing ever nudges someone who chooses to practise on a moon day (Q21).
- **Measured:** `compute_moon_days` 0.26 s for the first city-year (ephemeris load), 0.04 s after: ~35 cities × 4 years ≈ 6 s once, well within one tick.

## 10. Implementation notes and review fixes (2026-10-19)
- **Swiss Ephemeris path is per thread** in this pyswisseph build: computing in `asyncio.to_thread` workers failed after the first year ("files not found"). `_ephemeris._lib()` now sets the path once per thread (regression test; full 760 city-year parity still passes). The algorithm is unchanged.
- **Measured locally:** the first tick computed all 136 city-years (34 cities × 4 years) in 9.1 s; later ticks 7 ms.
- **Code review fixes:** `replace_year` runs in a real transaction (the engine autocommits) with a per-city-year advisory lock; the tick checks its deadline before each claim, Telegram sends time out after 10 s, and stale claims (> 5 min) are taken over; only sent/in-flight deliveries count toward the daily cap; the intro names the recipient's own offsets and stays until a reminder actually arrives; a send time inside quiet hours is refused; the reminder's "today" is the recipient's local date.
- **Copy (ux-writer):** offset chips read "7 days" / «за 7 дней» (3 per row); the city-zone button "🕒 Time zone: 📍 { $city }"; picker question "Which city's moon days do you follow?" / «По какому городу считать лунные дни?».
- **Known limits / follow-ups:** the intro flag is derived from deliveries kept 60 days (someone off for > 2 months sees the intro again); `ALGO_VERSION` names the `tzdata` package version, and the image sets `PYTHONTZPATH=` so zoneinfo uses exactly that package (the base image's own zoneinfo files are ignored); `PUT /me/notification-settings` stores all fields while the bot's patch keeps NULL = default; no index on `notification_delivery(created_at)` (fine at this scale).
