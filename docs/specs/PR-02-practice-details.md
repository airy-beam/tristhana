# PR-02 + PR-03 + PR-05: practice details on a practiced day

- Status: accepted (owner 2026-10-19; see §9, which overrides earlier text) · Date: 2026-10-18
- Requirements: **PR-02** (context: Mysore · Led · 1:1 · Home, online variants; the class link waits for SC-0x), **PR-03** (length via presets plus custom "series → last asana"; "same as last time" is the default), **PR-05** (optional duration and start time), **AC-01/AC-02** (the catalog is read at runtime; Latin/Cyrillic names), **NF-03**. Prepares ST-01..03 and PR-10. Budget: < 300 ms p50 per tap (warm).
- Related: ADR-0005 (time), 0008 (stateless callbacks), 0010 (natural keys), 0012 (webhook reply), 0016. New: **ADR-0017** (catalog in memory, natural-key references; Proposed).

## 1. Scope
**In:** a `practice` table (one per day now, with room for more), context + online, length (presets, "same as last time", custom series → last asana), duration, start time (API + Mini App; the bot only shows it), the in-memory catalog plus `GET /api/v1/catalog`, bot details screens after 🧘, and a details block in the Mini App Today card. A status change away from Practiced removes the details.
**Out:** the class link (SC-01..03; the schema gets a nullable `class_id` then), progression and "my last asana" records (PR-08: until then, recent lengths stand in for it), check-ins (PR-06), the diary (PR-07), the reminder quick log (PR-10: it will reuse `CopyLastPractice`), a second practice per day, led-class presets defined by a class, extras (drop-backs, short finishing), Mini App backfill (ST-01).
**Cut if time is short:** in the Mini App, the custom picker and the start time (the bot covers custom; the API supports both).

## 2. Flows and copy
- **Bot, after tapping 🧘 Practiced** (`d1:s:…:p`): the PR-01 "saved" screen becomes the **details screen P**. Its text is the saved line ("✓ Today, Sat 18 Oct: 🧘 Practiced. Practice done 🙏"), then either the summary ("Mysore · Primary + Intermediate → Pasasana · 90 min · 06:30 Almaty (UTC+5)") or `practice-details-prompt` with `practice-last-time` ("Last time: Mysore · Primary → Navasana"). Keyboard:
  `[🔁 Same as last time]` (only while no length is set and an earlier practice exists) · `[Mysore] [Led] [1:1] [Home]` (✓ marks the current one) · `[🌐 Online]` (a ✓ toggle, hidden for Home and when no context is set) `[⏱ Duration]` · `[📏 Length]` · `[✓ Done]` `[Remove details]` (the latter only when details exist).
  Every tap saves at once and edits the message in place. **The 90% path is 2 taps:** 🧘 → 🔁. Skipping costs nothing: you can ignore the keyboard or tap Done, and the day stays Practiced.
- **Done → screen V:** the same text with `[📝 Details] [✏️ Change] [📅 Another day]`. In the week picker, a practiced day's status screen also gets `[📝 Details]`.
- **Length screen L:** `[☀️ Short: standing + finishing] [½ Primary → Navasana]` · `[Full Primary]` · up to 3 **recent lengths** from your history (e.g. `[Primary + Intermediate → Pasasana]`, `[Intermediate → Karandavasana]`) · `[🎯 Other…]` · `[‹ Back]`. Tapping a preset saves it and returns to P.
- **Other… (custom):** screen O lists the confirmed series (`[Primary] [Intermediate] [Advanced A] [Advanced B]`; C and D are hidden while pending or placeholder). Picking Intermediate or later opens screen S: `[Only Intermediate] [Primary + Intermediate]`. Then grid G shows the stop points of the last series, 2 columns × 8 per page, with `‹ ›` paging and `[Full series]` on top. Labels: Latin, plus the variant letter ("Janu Sirsasana C"); RU shows Cyrillic with a Latin letter («Джану Ширшасана C»). Tapping an asana saves and returns to P. That's 3–4 taps, and you rarely need it.
- **Duration screen D:** `[30] [45] [60] [75]` · `[90] [105] [120] [150]` · `[No duration] [‹ Back]` (minutes).
- **Status change:** switching a practiced day to any other status deletes its details. There's no confirmation, since "Same as last time" restores them in one tap (Q4).
- **Mini App:** when today is Practiced, the Today card shows a details block: preset chips (same as last time, short, ½ primary, full primary, recent), context chips, an online toggle, duration chips, a start-time field with the zone label next to it ("Almaty (UTC+5)"; hidden while the zone is unknown), and "Other…", which opens two native `<select>`s (series range, then the last asana or "Full series"). Each change saves optimistically.
- **Failures:** if the day is no longer practiced (a stale keyboard, or the status was changed in another message), the bot reshows the status screen with `practice-day-not-practiced`. The API returns `{code}`. A DB outage shows `error-temporary`.
- **Copy (new keys; the ux-writer polishes; RU uses «ты» and no gendered past tense; the ashtanga-expert checks the context labels).** `bot.ftl`: `practice-details-prompt` ("Add details? Optional, one tap is enough." / «Добавишь детали? Это необязательно, хватит одного нажатия.»), `practice-last-time` ("Last time: { $summary }" / «В прошлый раз: …»), `practice-same-as-last` ("🔁 Same as last time" / «🔁 Как в прошлый раз»), `context-mysore` Mysore/«Майсор», `context-led` Led/«Лед-класс», `context-private` 1:1/«1:1», `context-home` Home/«Дома», `practice-online` "🌐 Online"/«🌐 Онлайн», `practice-length` "📏 Length"/«📏 Объём практики», `practice-duration` "⏱ Duration"/«⏱ Длительность», `practice-done` "✓ Done"/«✓ Готово», `practice-details` "📝 Details"/«📝 Детали», `practice-clear` "Remove details"/«Убрать детали», `length-pick` ("How far did the practice go?" / «Докуда была практика?»), `preset-short` ("☀️ Short: standing + finishing" / «☀️ Короткая: стоячие + завершающая»), `preset-other` "🎯 Other…"/«🎯 Другое…», `length-pick-series` ("Which series did you end with?" / «Какой серией закончилась практика?»), `length-only` ("Only { $series }" / «Только { $series }»), `length-pick-asana` ("Last asana in { $series }:" / «Последняя асана ({ $series }):»), `length-full-series` "Full series"/«Вся серия», `duration-pick` ("How long was it?" / «Сколько длилась практика?»), `duration-min` ("{ $min } min" / «{ $min } мин»), `duration-none` "No duration"/«Без длительности», `series-short` (selector `$n`: Primary/«Первая», Intermediate/«Вторая», Advanced A/«Третья», Advanced B/«Четвертая», …), `length-summary` (selector `$kind`: short "Short practice"/«Короткая практика»; full "{ $series } (full)"/«{ $series } (полностью)»; to "{ $series } → { $asana }"), `time-label` ("{ $time } { $city } ({ $offset })"), `practice-day-not-practiced`, `log-back` "‹ Back"/«‹ Назад». The series range is built as `series-short` joined with " + ". Asana names come from the catalog, never from `.ftl`. `app.ftl` gets the same keys plus `practice-title`, `practice-start-time`, `practice-save-failed`.

## 3. Design
**Domain (`domain/practice.py`, pure; small helpers in `domain/catalog.py`).**
- `PracticeContext(StrEnum)`: `mysore, led, private, home`.
- `PracticeLength(series: tuple[str, ...], end: str | None)`: the series slugs in practice order. Opening, standing, backbending and finishing are implied. `()` = **short** (sun salutations + standing + finishing). `end=None` = the last series in full. Examples: full Primary `(("primary",), None)`; half Primary `(("primary",), "navasana")`; Primary + Intermediate → Pasasana `(("primary","intermediate"), "pasasana")`; split Intermediate → Karandavasana `(("intermediate",), "karandavasana")`. Every series except the last is full. That matches how the method is taught (05's "segments", with only the last one partial), and one row covers it.
- `check_length(catalog, length) -> PracticeLength` (normalised) raises `InvalidLength` unless: every slug is a **confirmed** series; the series are **contiguous and ascending** by number; `end` is a **stop point** of the last series (optional items are never stops, as the validator already guarantees); an empty `series` has no `end`. An `end` equal to the series' last stop normalises to `None`, so "full" stays full even if the catalog grows.
- `Practice(context | None, online, length | None, duration_min | None, start_time: time | None, timezone | None)`. Rules: `online` is false for Home; duration is 1–600; a start time needs a known zone (`TimezoneUnknown`).
- `STATIC_PRESETS`: short, ½ Primary (→ `navasana`), full Primary. These are natural keys in code, and a test checks them against the catalog (Q6).
- `derive_presets(recent: list[Practice], catalog) -> Presets(last, presets)`: `last` = the newest practice, for "same as last time". `presets` = the static ones plus up to 3 distinct recent lengths that aren't already static, newest first. Lengths that no longer validate are skipped. Before PR-08, this is how "up to my asana" works.

**Application (`application/practice.py`).** Port `PracticeRepository` (`application/ports/practice.py`), exposed as `Storage.practices`. The `Catalog` arrives as a value from the composition root (ADR-0017). Use cases take a `Principal` and act on the caller's own data only:
- `SavePractice(principal, date, patch: PracticePatch) -> Practice`: the patch carries only the fields to set. The bot sends one field per tap; the API's PUT sends all fields. Validates, stamps `timezone = account.timezone`, and raises `DayNotPracticed`, `InvalidLength`, `InvalidPractice` or `TimezoneUnknown`.
- `CopyLastPractice(principal, date) -> Practice`: copies context, online, length and duration (not the start time) from the newest practice **before** `date` (this also works for backfill). Raises `DayNotPracticed` or `NoPreviousPractice`.
- `ClearPractice(principal, date)`: idempotent.
- `GetPracticePresets(principal, date) -> Presets`: `recent(before=date, limit=60)` plus `derive_presets`.
- `GetDays`: `DayLog` gains `practices: tuple[Practice, ...]`. `SetDayStatus` is unchanged in its interface.

**Infrastructure.** Catalog: `load_catalog` runs once in the lifespan from `settings.seed_dir`, plus a `version` hash. Use `yaml.CSafeLoader` as the strict loader's base when available, and measure. `SqlPracticeRepository` (each method is one statement):
- `save`: `INSERT INTO practice (…) SELECT … WHERE EXISTS (SELECT 1 FROM day_log WHERE account_id=… AND local_date=… AND status='practiced') ON CONFLICT (account_id, local_date, slot) DO UPDATE SET <patched columns>, updated_at=now() RETURNING *`. No row back = `DayNotPracticed`.
- `copy_latest`: `INSERT … SELECT <cols> FROM practice WHERE account_id=… AND local_date < :d ORDER BY local_date DESC, slot DESC LIMIT 1`, with the same EXISTS guard and upsert.
- `delete`.
- `recent(before, limit)`: a backward scan of the PK.

`SqlDayLogRepository.upsert` with a status other than practiced becomes `WITH gone AS (DELETE FROM practice WHERE account_id=… AND local_date=…) INSERT INTO day_log …`, still one statement. `list_range` LEFT JOINs `practice` on `day_log.status = 'practiced'`, still one statement. The join condition also hides any row left by a status/details race; the next status write removes it.

**API** (`api/v1/practice.py`; initData auth per ADR-0015, except the catalog).

| Method, path | Request | Response |
|---|---|---|
| `GET /api/v1/catalog` (public) | none | 200 `PracticeCatalog {version, series: [{slug, number, names{en,ru}, stops: [{key, latin, ru}]}]}`, confirmed series only. `ETag: "<version>"`, `Cache-Control: public, max-age=3600`, 304 on `If-None-Match` |
| `GET /api/v1/me/days…` (PR-01) | as before | each `Day` gains `practices: [Practice]` (0..1 for now) |
| `GET /api/v1/me/days/{date}/practice-presets` | none | 200 `{last: Practice \| null, presets: [{kind: short\|half_primary\|full_primary\|recent, length}]}` |
| `PUT /api/v1/me/days/{date}/practices/{slot}` (slot = 1 only, else 422) | `{context, online, length: {series, end} \| null, duration_min, start_time: "HH:MM" \| null}` | 200 `Practice {slot, context, online, length, duration_min, start_time, timezone}`; 409 `day_not_practiced`; 422 `invalid_length` \| `invalid_practice` \| `timezone_unknown` |
| `DELETE /api/v1/me/days/{date}/practices/{slot}` | none | 204, idempotent |

`ErrorCode` gains the four codes above. The client is regenerated (`gen:api`). There's no copy endpoint: the Mini App PUTs `presets.last`.

**Bot** (`bots/telegram/practice.py`, `practice_callbacks.py`, prefix **`p1:`**, absolute dates, decoded like `d1:`). Item keys go into callbacks as **natural keys**, so no positions or catalog versions are needed. Series are referenced by number (1–6, validated unique).

| Data | Meaning | Max bytes |
|---|---|---|
| `p1:o:20261018` / `p1:v:…` | open P / collapse to V | 13 |
| `p1:c:20261018:m` | context (`m l i h`) | 15 |
| `p1:n:20261018:1` | online on/off | 15 |
| `p1:s:20261018` / `p1:x:…` | same as last time / remove details | 13 |
| `p1:m:` `p1:a:` `p1:d:` + date | screens L / O / D | 13 |
| `p1:r:20261018:2` | screen S for series 2 | 15 |
| `p1:g:20261018:12:1` | grid, series 1..2, page 1 | 18 |
| `p1:l:20261018:12:<key>` | set length (`00` = short; no key = full) | **54** (`triang-mukhaikapada-paschimottanasana`, 37) |
| `p1:t:20261018:105` | duration (`0` = none) | 17 |

A catalog test asserts that every stop key yields ≤ 64 bytes, so a longer future slug fails CI rather than Telegram. The tap protocol is as in PR-01: answer in parallel, then the edit as the webhook reply. **DB round trips per tap:** the middleware SELECT plus one statement (save/copy/delete RETURNING renders P). Screens L/O/S/G/D need **no** statement apart from L, which runs `recent`. P after 🧘 runs two (status upsert, `recent`). `Translator` gains `TimeArg(local_date, time, zone)`, which renders `06:30 Almaty (UTC+5)` (EN) or `06:30 Алматы (UTC+5)` (RU) via Babel exemplar cities and the offset on that date.

**Mini App.** No new libraries. `useCatalog()` (staleTime ∞), `usePracticePresets(date)` (enabled when practiced), `useSavePractice()` / `useClearPractice()`, optimistic, in the same mutation scope `"day"` as status changes, so taps apply in order. A `PracticeDetails` component inside `TodayCard`. Bundle: + ~4 KB gzip expected (budget 150, now ~105).

## 4. Ops
No owner steps ☁️. On merge, the existing migrate job applies `0003`, and the deploy ships the catalog that's already in the image. After go-live, check the startup log for the catalog parse time.

## 5. Migration `0003_practice`
`practice(account_id uuid not null, local_date date not null, slot smallint not null default 1 check (slot = 1), context text null check in ('mysore','led','private','home'), online boolean not null default false, series text[] null, end_item text null, duration_min smallint null check (duration_min between 1 and 600), start_time time null, timezone text null, created_at/updated_at timestamptz not null default now(), primary key (account_id, local_date, slot), foreign key (account_id, local_date) references day_log on delete cascade, check (not (context = 'home' and online)), check (end_item is null or cardinality(series) > 0), check (cardinality(series) <= 6), check (start_time is null or timezone is not null))`.

`series` null = length not given; `'{}'` = short. There are no FKs to the catalog (ADR-0017). Clearing a day or deleting the account cascades. The PK serves `recent` and the join. Widening to n practices later means dropping `check (slot = 1)`. Expand-only; downgrade drops the table.

## 6. Cross-cutting checks
- **Time zones:** the date is the day's local date. `start_time` is **wall clock + `timezone`** (the account zone when saved; ADR-0005), not a `timestamptz`. A practice in Mysuru should still read "04:30 Mysuru (UTC+5:30)" after you fly home, and stats like "usual start time" want wall clock. With no known zone, a start time is refused, so a guessed zone is never stored. Every displayed time carries the label (`time-label`, offset computed for that date, so DST is handled). Tests: Kolkata +5:30, Kathmandu +5:45, a DST date in Europe/Berlin, zone null.
- **Privacy:** details are visible to teachers by default per 05 (length/series ✅), so there's no sealing. A ladies' holiday or rest day never carries practice rows (they're deleted on the status change), so no detail leaks a sealed status. Logs carry the account uuid only.
- **i18n:** all labels are in `bot.ftl`/`app.ftl`, with en/ru parity tests. Asana names come from the catalog (Latin for EN; Cyrillic plus a Latin variant letter for RU). Minutes use an abbreviation, so no plurals; Fluent still gets `NUMBER`.
- **Responsiveness:** the catalog is in memory, so picker screens are pure CPU. Each tap is ≤ 2 short statements. No new dependency and no image growth (the YAML is already in the image; PyYAML is already a dependency). Startup is + one YAML parse.
- **Stats readiness (ST-01..03):** practices per month by context are `GROUP BY context`. By series, use `series[cardinality(series)]` (the furthest series) or `unnest(series)`. Short practices are `series = '{}'`. Practiced days without details count as "unspecified". The weekday comes from `local_date`.

## 7. Test plan
- **Domain:** `check_length`, covering full/half/short/split/multi-series, a non-contiguous range (1+3), descending order, a pending series (C), a non-stop item (`dandasana`), an optional item (`paschimottanasana-d`), an end in a non-last series, an end on the last stop normalised to full, an unknown key; Home + online rejected; duration bounds; start time without a zone; `derive_presets` (empty history, last, 3 distinct recents, statics deduplicated, invalid old keys skipped); `STATIC_PRESETS` valid against the real seed.
- **Use case (fake repo, fixed clock):** a patch sets only its field; a not-practiced day raises; copy uses the newest practice *before* the date and drops the start time; copy with no history raises; clear twice; the stored zone equals the account zone.
- **Infrastructure (real Postgres, `db` marker):** the EXISTS guard (no row on rest or no day); a partial patch upserts; `copy_latest` in one statement; a status change to rest deletes practices in the same statement; clearing the day cascades; `list_range` joins only practiced days; every CHECK; upgrade → downgrade → upgrade; `alembic check`; catalog load + version stable across runs.
- **API contract:** 401; catalog without auth, ETag/304, confirmed series only; PUT valid, 409, each 422 code, slot 2 → 422; DELETE 204 twice; `/me/days` includes practices; OpenAPI lists the new codes.
- **Bot handler (fake use cases):** after 🧘, P shows 🔁 only with history and no length; each `p1:` callback parses and calls the right use case; context ✓; the online toggle hidden for Home; grid paging bounds; L shows recents; not-practiced → status screen with a note; malformed data ignored; **every generated callback ≤ 64 bytes over the whole catalog**; RU grid labels are Cyrillic with Latin variant letters; en/ru keys exist.
- **Mini App (Vitest):** the details block only on Practiced; a preset tap PUTs and highlights optimistically, rolling back on error; the start time hidden when the zone is unknown; the zone label shown; the custom selects list only stop points.
- **Architecture:** import-linter (domain pure; `yaml` only in infrastructure); the bundle check; the container smoke loads the catalog (already does).

## 8. Open questions for the owner
1. **Default "same as last time"**: a one-tap 🔁 button on the details screen, never applied automatically when you tap 🧘 (auto-apply would write details you didn't confirm; PR-10's reminder will do Practiced + same in one tap)? Recommended: yes.
2. **Scope:** ship PR-02 (no class link), PR-03 in full, and PR-05 with duration in the bot + Mini App and start time in the Mini App only (the bot shows it)? Recommended: yes. Bot time entry would need extra screens for a rarely used field.
3. **Catalog in memory** (ADR-0017, no catalog tables until admin editing) and natural keys as text in `practice`? Recommended: yes.
4. **Status change** away from Practiced deletes the details in the same statement, with no confirmation? Recommended: yes ("same as last time" restores them in one tap). The alternative, keeping hidden rows, makes every stats query filter them.
5. **One practice per day now** (`slot = 1`, with room in the schema and API path for more)? Recommended: yes. Related, open question 19 (pranayama-only day): no pranayama context now. Log such a day as Practiced without length if you consider it practice; a `pranayama` context comes with the second practice slot. Recommended: confirm with the ashtanga-expert.
6. **Static presets in code** (short, ½ Primary → Navasana, full Primary; validated against the catalog in CI) rather than a new YAML file? Recommended: yes. Move them to data when teachers/shalas define class presets (SC-0x).
7. **Custom ranges in the bot:** offer only "Only X" and "previous + X" (Primary + Intermediate, Intermediate + Advanced A); the API accepts any contiguous range? Recommended: yes.
8. **Context labels:** Mysore / Led / 1:1 / Home; RU «Майсор» / «Лед-класс» / «1:1» / «Дома», «Онлайн»? Recommended: let the ashtanga-expert and ux-writer settle them.
9. **Duration chips:** 30/45/60/75/90/105/120/150 min? Recommended: yes.
10. **Zone label in the Mini App:** the city from the IANA id (Latin, e.g. "Almaty (UTC+5)") plus the offset via `Intl`; localised city names come with the ID-06 zone picker. The bot uses Babel's localised city. Recommended: yes.
11. **"Same as last time" source:** the newest practice before the logged date (so backfilling 2024 copies 2024, not today's)? Recommended: yes.

## 9. Decisions (owner + ashtanga-expert, 2026-10-19) — override the text above
- Q1–Q10 as recommended. Expert corrections applied:
  - **Implied blocks:** `()` = short = opening + standing + finishing, **no backbending**; any non-empty `series` implies opening, standing, series, backbending, finishing. No separate "standing only" length.
  - **Context `home` → `self`** ("Self-practice" / «Самостоятельно»: home, hotel, shala outside class hours). DB CHECK `('mysore','led','private','self')`, online hidden for `self`. RU: «Майсор», «Лед-класс», «Индивидуально» (EN "1:1"), «🌐 Онлайн». Context buttons in two rows: `[Mysore] [Led]` / `[1:1] [Self-practice]`.
  - **Duration chips:** `[30][45][60][75]` / `[90][120][150][180]`.
  - **Copy:** `preset-short` "☀️ Short: sun salutations, standing, finishing" / «☀️ Короткая: приветствия солнцу, стоячие, завершающие» (own row); new keys `preset-half-primary` "½ Primary → Navasana" / «½ первой → Навасана», `preset-full-primary` "Full Primary" / «Вся первая серия»; `length-pick` "Where did your practice end?" / «Где закончилась практика?»; one full series reads "Full { $series }" / «{ $series } целиком»; RU series names lowercase inside sentences.
  - **Recents:** the 3 recent lengths are ranked by **use count** over the last 60 practices (ties: newest), so a weekly Friday Primary doesn't push out the usual length. 🔁 still copies the newest practice before the logged date.
  - Pranayama-only day: Practiced with no length; an activity type comes with the second slot (open question 19 closed).
- **Q11 (owner): half Primary + the next series ships now.** Some teachers/students practise **first half of Primary (→ Navasana) + Intermediate → X** or **second half of Primary (Bhujapidasana → Setu Bandhasana) + Intermediate → X**.
  - Model: `PracticeLength(series, end, first_part)` with `first_part ∈ {None, "first_half", "second_half"}` applying to the **first** series only, allowed only for a series with defined halves (`SERIES_HALVES = {"primary": "navasana"}`: the first half ends at Navasana, the second starts at the next item, Bhujapidasana). Rules: with one series, `first_half` normalises to `end = navasana` (`first_part = None`); `second_half` alone is allowed (second half of Primary only) and may carry an `end` within it after the split; with ≥2 series the first series is that half and the last series may be partial (`end`). Everything else as §3 (contiguous ascending confirmed series, stop points only).
  - Storage: new nullable column `first_part text check in ('first_half','second_half')` (and `first_part is null or cardinality(series) >= 1`). API `length: {series, end, first_part}`.
  - Bot: screen S for a series n ≥ 2 offers `[Only Intermediate] [Primary + Intermediate] [½ Primary (1st) + Intermediate] [½ Primary (2nd) + Intermediate]` (half options only when the previous series has halves, i.e. n = 2). Range codes in callbacks gain a suffix: `12` (full + …), `12a` (first half + …), `12b` (second half + …); e.g. `p1:l:20261018:12a:pasasana` (≤ 56 bytes).
  - Summary copy: "Primary, 1st half + Intermediate → Pasasana" / «1-я половина первой + вторая → Пашасана»; ux-writer polishes.
- **Expert re-check (2026-10-19):** "second half of Primary" exists only together with Intermediate (alone it isn't a recognised practice), so `check_length` rejects it with one series. Half labels read "Primary, 2nd half" / «2-я половина первой»; RU full series «Первая серия целиком» (preset and summary alike). The catalog's «Пашасана» (ś → ш) is correct.

## 10. Implementation notes and review fixes (2026-10-19)
- **Zone travels with the start time only:** `timezone` is written only when `start_time` is in the patch; re-sending the same start time (the Mini App PUTs all fields) keeps the stored zone (`CASE … IS NOT DISTINCT FROM`); "same as last time" never touches the day's start time or zone.
- **Empty rows never count:** `recent` and `copy_latest` skip rows with no context/length/duration/start time, and copy only from practiced days.
- **Status race:** the "day is practiced" guard reads the day row `FOR SHARE`; when a day is set to Practiced again, details left over from a race (or an old revision) are deleted in the same statement. `list_range`/`recent` show practices only on practiced days.
- **Bot:** one outer handler turns `DayNotPracticed` into the status screen (also after a fallback); Clear re-reads the day; "same as last time" is looked up only while the practice has no details (≤ 2 statements per tap); grid paging glyphs come from `.ftl` (`page-prev`/`page-next`).
- **API:** a start time with a UTC offset is `invalid_practice`; `If-None-Match` accepts weak and listed ETags.
- **Mini App:** the server's normalised practice is written back to the cache; after the last queued day-scope mutation (or a 409) the days are refetched, so a failed earlier tap can't leave the screen out of sync; the start time saves on blur/Enter and is labelled with the practice's own zone at that time.
- **Domain:** "second half of Primary" only with the next series; "first half" alone normalises to Primary → Navasana (also when given with `end = navasana`).
- **Known limits:** RU city names come from Babel and are Latin for some cities (Kolkata, Kathmandu) until ID-06's zone picker; the Mini App shows no "last time" summary next to 🔁 (the bot does).
- **Measured locally** (Postgres 17, warm): PUT practice p50 14 ms, presets 4 ms, catalog 1.5 ms. Image unchanged (~245 MB in CI); bundle 108 KB gzip.
