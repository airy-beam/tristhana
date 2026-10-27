# PR-06: after-practice check-in (mood, energy, effort, body and mind tags)

- Status: **accepted** (owner, 2026-10-27: all as recommended, with the changes in §10; ashtanga-expert fixes applied) · Date: 2026-10-27 · Size S, Phase 2
- Requirements: **PR-06** (Garmin-style check-in: energy/effort 1–5, mood emoji, body feel, optional tags). Touches **ID-06** (a new setting). Prepares **ST-05** (check-in trends) and **ST-06** (teacher dashboard; check-ins hidden, 05 privacy matrix). The free-text note waits for **PR-07** (diary). Builds on PR-01/02 (`d1:`/`p1:` screens, the "day is practiced" guard), PR-10 (screen V after ✅) and WH-01 (`hide_ladies` setting pattern). Budget: < 300 ms p50 per tap (warm).
- Related: ADR-0005, 0007, 0008, 0012, 0016, 0017, 0020, 0021. New: **ADR-0024** (check-ins stored plain in their own table, owner-only by policy; Accepted).

## 1. Scope
**In:** an optional check-in on each practiced day (slot 1): a **mood** emoji, **energy**, **effort** (1–5 each) and up to 10 body-and-mind **tags**. The bot offers a one-tap mood row on the details screen P and the done screen V (today or yesterday only), plus a check-in screen K and a tags screen T. The Mini App gets a check-in block in the Today card and the DayEditor. The API gets PUT/DELETE endpoints and the check-in on `/me/days`. A new account setting, **"Offer a check-in after practice"** (on by default), appears in bot `/settings`, Mini App Settings and `PATCH /me`.
**Out:**
- check-ins on rest or other non-practiced days
- the free-text note (PR-07)
- trends and charts (ST-05)
- teacher views (ST-06)
- reminders or nudges to check in
- any streak or score built on check-ins
- a pain or injury tag: injury belongs in the 🤒 Sick/Injury status
- **any inference or advice from check-ins** (never "you've been sore 5 days")
- auto-detecting the setting, or any message about it

**Tone:** always optional, never asked twice, no "you haven't checked in". Every scale reads neutrally ("1 easy · 5 hard", not good/bad). The lowest mood is 😔, not 😡.

## 2. Domain (pure) `domain/check_in.py`
```python
SCALE = range(1, 6)                       # 1..5
OFFER_DAYS = 2                            # the mood row: today and yesterday only
class CheckInTag(StrEnum):                # display order = definition order (ashtanga-expert, final)
    STIFF, OPEN, STRONG, LIGHT, HEAVY, SORE,            # body
    FOCUSED, CALM, SCATTERED, STEADY_BREATH             # mind ("steady_breath")
TAG_GROUPS: dict[CheckInTag, Literal["body", "mind"]]
@dataclass(frozen=True, slots=True)
class CheckIn: mood: int | None = None; energy: int | None = None; effort: int | None = None
               tags: frozenset[CheckInTag] = frozenset(); slot: int = 1
    def is_empty(self) -> bool            # all None and no tags = "no check-in"
class InvalidCheckIn(ValueError)
def check_check_in(c: CheckIn) -> CheckIn # each scale None or in SCALE; slot == 1
def offer_mood_row(day, today, existing: CheckIn | None, enabled: bool) -> bool
    # enabled and day ∈ {today, today − 1} and (existing is None or existing.is_empty())
```
- **One check-in per practice slot, on a Practiced day only** (the same rule as PR-02 details). **Every field is optional**, and an empty check-in counts as none, so reads map it to None.
- **Body feel = the tags**: there's no separate body scale. Energy means how the body and energy felt (1 low → 5 high), Garmin's "How did you feel". Effort means how hard it felt (1 easy → 5 hard), Garmin's perceived effort. Mood is a 5-step emoji scale stored as 1–5. The emoji are presentation only and live in `.ftl`.
- **The mood row** is offered only when `offer_mood_row` holds. "Today" is the caller's local date (provisional zone allowed, as for logging). Older practiced days, and accounts with the setting off, get only `[✨ Check-in]`. That button is always there, so a check-in can be added or edited on any practiced day.
- **The status changes away from Practiced → the check-in is deleted** (same statement, as PR-02). Accepted consequence: tapping 😌 Rest by mistake and then 🧘 again loses the check-in, just as it loses the details. **Clearing the day** cascades. **"Remove details" (`ClearPractice`) keeps the check-in**, since it's a separate row. Re-tapping 🧘 on a 🧘 day keeps it.
- `Account.offer_check_in: bool = True` (the setting; it only controls the mood row and the Mini App's open block, never whether check-ins can be made).
- Tags are vocabulary in code plus `.ftl` labels (ADR-0024). There are no bandha or drishti tags (ashtanga-expert). Unknown stored keys (a tag removed later) are dropped on read.

## 3. Application and infrastructure
- Port **`CheckInRepository`** (`application/ports/check_in.py`, on `Storage.check_ins`). It has one statement per method, and every write is guarded by `_practiced(...) FOR SHARE` (reused from `db/practice.py`):
  - `save(account_id, date, patch: CheckInPatch) -> CheckIn | None`: `INSERT … SELECT … WHERE EXISTS(practiced) ON CONFLICT (account_id, local_date, slot) DO UPDATE SET <patched columns>, updated_at = now() RETURNING *`. None = the day isn't Practiced. `CheckInPatch(values, fields)` works like `PracticePatch`: a bot tap sets one field, the API's PUT sets all of them.
  - `set_tag(account_id, date, tag, on) -> CheckIn | None`: the same upsert with `tags = CASE WHEN :on THEN array_append(array_remove(tags, :t), :t) ELSE array_remove(tags, :t) END` (absolute and idempotent).
  - `delete(account_id, date)`: idempotent.
- Use cases (`application/check_in.py`, `Principal`, own data only):
  - **`SaveCheckIn(principal, date, patch) -> CheckIn`**: validates; raises `DayNotPracticed` (reused from `application/practice.py`) and `InvalidCheckIn`.
  - **`SetCheckInTag(principal, date, tag, on) -> CheckIn`**.
  - **`ClearCheckIn(principal, date)`**.
  - Reads go through the existing **`GetDays`**: `DayLog` gains `check_ins: tuple[CheckIn, ...]` (0..1, practiced days only).
  - The setting goes through the existing `UpdateProfile` (`ProfilePatch.offer_check_in`; ADR-0021 partial write, 1 `UPDATE … RETURNING`).
- `SqlDayLogRepository._range` gets a **LEFT JOIN `check_in`** on the same `status = 'practiced'` condition as `practice`, so it's still one statement. `upsert` gets a second CTE beside `gone` that deletes check-ins under the same conditions, so it's still one statement. The setting is read from `Account`, which the middleware already loads, at no extra cost.
- **No new policy now** (own data). ADR-0024 records the ST-06 rule: teacher projections **omit check-ins entirely**, and a teacher view must never show "check-in missing" or whether one exists. A named policy `can_view_check_ins(viewer, student)` → False until ST-06 adds a per-teacher opt-in. Shala aggregates never read `check_in`.

## 4. API (initData auth; additive; the client is regenerated with `gen:api`)
| Method, path | Request → Response |
|---|---|
| `GET /api/v1/me/days` | each `Day` += `check_ins: [CheckInOut]` (0..1; empty unless practiced). `CheckInOut {slot, mood, energy, effort, tags: [CheckInTag]}` |
| `PUT /api/v1/me/days/{date}/check-ins/{slot}` (slot = 1, else 422) | `{mood: 1..5 \| null, energy, effort, tags: [CheckInTag]}` (replaces all) → 200 `CheckInOut`; 409 `day_not_practiced`; 422 `invalid_check_in` (also an unknown tag, as an enum error) |
| `DELETE /api/v1/me/days/{date}/check-ins/{slot}` | → 204, idempotent |
| `GET /api/v1/me` · `PATCH /api/v1/me` | `Me` += `offer_check_in: bool` · `MePatch` += `offer_check_in: bool \| null` (omitted = unchanged, null = the default, true) |
| `GET /api/v1/catalog` (public) | += `check_in_tags: [{key: CheckInTag, group: "body"\|"mind"}]` in display order. The ETag also covers the tag keys (`version` + a short hash of `CheckInTag`) |

A PUT with everything empty is stored as an empty row and read back as none. The Mini App sends DELETE instead. `ErrorCode` += `invalid_check_in`. The Mini App gets the tag list from the server and never hard-codes it.

## 5. Bot (prefix **`k1:`**, stateless, absolute values, ≤ 17 bytes; answer the callback first, edit in place)
| Data | Meaning | Bytes |
|---|---|---|
| `k1:o:20261018` / `k1:v:…` | open K / done → V | 13 |
| `k1:g:20261018` / `k1:x:…` | tags screen T / remove the check-in → V | 13 |
| `k1:m:20261018:4` · `k1:e:…:4` · `k1:f:…:4` | mood / energy / effort = n (`0` = clear) → K | 15 |
| `k1:t:20261018:s:1` | tag by one-letter code on (`1`) / off (`0`) → T | 17 |
| `s1:k:1` / `s1:k:0` | setting: offer the check-in on / off → `/settings` | 6 |

Tag codes are an adapter table in `check_in_callbacks.py` (like `_CONTEXTS`): `s` stiff, `o` open, `g` strong, `l` light, `h` heavy, `r` sore, `f` focused, `c` calm, `d` scattered, `b` steady breath. A test asserts they're unique and cover `CheckInTag`.
- **Where the check-in is offered:** on **P** (after 🧘, including after 🔁 or a preset) and on **V** (after ✓ Done, and after the reminder's ✅ quick log), the screen gains `checkin-prompt` and **one mood row** `[😔][😕][😐][🙂][😊]` only while `offer_mood_row` holds (setting on, today or yesterday, no check-in yet). **One tap saves the mood** and opens K. Ignoring the row costs nothing. When the rule doesn't hold, P and V show `[✨ Check-in]` (`k1:o`) instead, plus the `checkin-summary` line when a check-in exists ("🙂 · ⚡ energy 4/5 · 🔥 effort 3/5 · Light, Calm").
- **K:** the saved line, the summary (if any) and `checkin-explain`. Rows: mood (5 emoji), energy `[⚡1]…[⚡5]`, effort `[🔥1]…[🔥5]` (✓ marks the current value; tapping it again sends `0` and clears it), `[🏷 Body and mind…]`, `[✓ Done] [Remove check-in]` (the latter only when one exists).
- **T:** `checkin-tags-pick`, then the 10 tags 2 per row (body first; ✓ marks the toggled ones) and `[‹ Back]` → K.
- **`/settings`:** `settings-checkin-line` + `[✨ Don't offer]` / `[✨ Offer]` (`s1:k:0` / `s1:k:1`, absolute).
- **Failures:** a day that's no longer practiced (stale keyboard) raises `DayNotPracticed`, and the bot shows the status screen with `practice-day-not-practiced` (the same outer handler as `p1:`). Malformed data is ignored. A DB outage shows `error-temporary`.
- **Round trips:** a scale or tag tap = middleware + **1** (the upsert's RETURNING renders K or T; the saved line needs no read). Opening K or T = + 1 read. P and V = **unchanged** (the check-in comes with their existing day read; the setting and "today" come from the account and the clock). After ✅ (PR-10) the day was empty, so V decides with no read. A `/settings` toggle = + 1.
- **After review (2026-10-27):**
  - A practice-detail tap on P (`p1:c`, `p1:l`, `p1:s`, …) stays **one statement**: the practice upsert is a CTE LEFT JOINed to `check_in`, so `SavePractice`/`CopyLastPractice` return `SavedPractice(practice, check_in)` and P shows the same check-in line as when opened.
  - **One question at a time:** on V, while the one-time practice-reminder offer (PR-10) is shown, the check-in is only `[✨ Check-in]`.
  - **Remove check-in** returns to V with `[✨ Check-in]` only (not asked again right away).

## 6. Mini App
- **`CheckIn.tsx`** goes below `PracticeDetails` in `TodayCard` and `stats/DayEditor` (practiced days only). It is **open** when the bot's rule holds (setting on, today or yesterday by the payload's server `today`, or a check-in already exists). Otherwise it's a collapsed `checkin-edit` link that opens it.
  - Three labelled chip groups: the mood emoji (each with an `aria-label` such as "Mood 4 of 5"), energy 1–5 and effort 1–5 with end hints. Each chip is `aria-pressed`, and tapping a pressed chip clears it.
  - Then the tag chips (two groups, toggles) and a "Remove check-in" link when one exists.
- **Saving:** `useSaveCheckIn` PUTs the whole object optimistically in mutation scope `"day"` (ordered after status taps), with rollback and `checkin-save-failed` on error. It writes the server's value back to the days cache, and a 409 refetches the days. The tag list comes from `useCatalog()`.
- **Settings → Privacy** (or the practice group): the switch `settings-checkin` with `settings-checkin-hint` (`PATCH /me`, optimistic, rolled back on error).
- No new dependency. Expected size: about +1.6 KB gzip, mostly in lazy chunks.

**Copy (new keys in `bot.ftl` and `app.ftl`; ashtanga-expert fixes applied; the ux-writer polishes; RU uses «ты», nouns for tags, so there are no gendered adjectives or past tenses).**
- `checkin-prompt` "How do you feel after practice? Optional." / «Как ты после практики? По желанию.»
- `checkin-explain` "⚡ Energy: 1 low → 5 high · 🔥 Effort: 1 easy → 5 hard. Tap what fits, all optional." / «⚡ Энергия: 1 мало → 5 много · 🔥 Усилие: 1 легко → 5 тяжело. Отметь, что подходит, всё по желанию.»
- `checkin-mood-chip` (selector `$n`: 😔 😕 😐 🙂 😊), `checkin-energy-chip` "⚡{ $n }", `checkin-effort-chip` "🔥{ $n }" (the same in both locales)
- `checkin-summary-energy` "⚡ energy { $n }/5" / «⚡ энергия { $n }/5», `checkin-summary-effort` "🔥 effort { $n }/5" / «🔥 усилие { $n }/5». The parts are joined with " · ", like the practice summary.
- `checkin-edit` "✨ Check-in" / «✨ Самочувствие»
- `checkin-tags-open` "🏷 Body and mind…" / «🏷 Тело и ум…»
- `checkin-tags-pick` "How did body and mind feel? Pick any." / «Как тело и ум? Отметь, что подходит.»
- `checkin-clear` "Remove check-in" / «Убрать самочувствие»
- `checkin-tag` (selector `$tag`): stiff "Stiff"/«Скованность», open "Open"/«Раскрытость», strong "Strong"/«Сила», light "Light"/«Лёгкость», heavy "Heavy"/«Тяжесть», sore "Sore muscles"/«Ноющие мышцы», focused "Focused"/«Собранность», calm "Calm"/«Спокойствие», scattered "Scattered"/«Рассеянность», steady_breath "Steady breath"/«Ровное дыхание»
- Bot settings: `settings-checkin-line` "✨ Check-in after practice: offered|not offered" / «✨ Самочувствие после практики: предлагаю|не предлагаю», `settings-checkin-off` "✨ Don't offer" / «✨ Не предлагать», `settings-checkin-on` "✨ Offer" / «✨ Предлагать»
- App settings: `settings-checkin` "Offer a check-in after practice" / «Предлагать отметить самочувствие после практики», `settings-checkin-hint` "Mood, energy and effort right after logging today's practice. You can always add one from the day." / «Настроение, энергия и усилие сразу после отметки практики. Добавить можно и позже, в любой день практики.»
- App only: `checkin-title` "How do you feel?" / «Самочувствие», `checkin-mood` / `checkin-energy` / `checkin-effort` / `checkin-body` / `checkin-mind` group labels, `checkin-mood-label` (selector `$n`, aria: "Mood { $n } of 5" / «Настроение { $n } из 5»), `checkin-save-failed`
- Reused: `practice-done`, `log-back`, `practice-day-not-practiced`, `error-temporary`.
- **Words to avoid** (ux-writer and test grep): missed, forgot, bad, pain, push, should, only, again, streak, recovery, training load, «плохо», «пропустил(а)», «боль», «надо», «всего лишь», «опять».

## 7. Migration `0012_check_in` (expand-only, down_revision `0011`)
- **Table:** `check_in(account_id uuid not null, local_date date not null, slot smallint not null default 1, mood smallint null, energy smallint null, effort smallint null, tags text[] not null default '{}', created_at/updated_at timestamptz not null default now(), primary key (account_id, local_date, slot), foreign key (account_id, local_date) references day_log on delete cascade)`.
- **CHECKs:** `slot = 1`, `mood BETWEEN 1 AND 5` (likewise `energy` and `effort`), `cardinality(tags) <= 16` (room to grow; no value CHECK, per ADR-0024).
- **Setting:** `account` add `offer_check_in boolean not null default true` (like `hide_ladies`).
- The PK serves the join and ST-05's range reads. The old revision ignores both changes. Downgrade drops them. There's no data change and no owner step ☁️.

## 8. Cross-cutting checks
- **Time zones:** a check-in belongs to the day's `local_date` (as stored on `day_log`). It has no time of its own, so no zone label is shown. `updated_at` (timestamptz UTC) is audit only. The today/yesterday rule uses the caller's local today (provisional zone allowed), computed in the use case from the clock; the Mini App uses the payload's server `today`, never the device date. ST-05's weekday and moon correlation use `local_date` and the followed city's `moon_day`. Tests: Kiritimati vs Honolulu on the same instant (yesterday edge), a provisional zone, a backfilled day (no row, ✨ only).
- **Privacy:** plain scores and tag keys, owner-only (ADR-0024). The owner accepted that mood and soreness may count as health-adjacent data under GDPR, and the sealed fallback is documented in the ADR. Check-ins are not in teacher projections (not even "missing"), not in aggregates, and not in logs (the account uuid only). They exist only on practiced days, so they never reveal 🌸, and the tag list has no menstrual, pain or injury tags. Account delete cascades. ST-09 export includes them.
- **i18n:** all labels are in `.ftl` with en/ru parity tests. Plural-free (`n/5`). Tags use a Fluent selector over the enum keys, and a test asserts every `CheckInTag` has a label in both locales.
- **Responsiveness:** each tap is ≤ 1 short statement after the middleware. P and V gain no statement (a PK LEFT JOIN; the setting comes from the loaded account). Callbacks are answered first, and the edit goes in the webhook reply. There's no dependency, no image growth and no startup cost.
- **ST-05 must join `day_log` with `status = 'practiced'`** (as `_range` does), never read `check_in` alone: a rare status/check-in race can leave a row on a day that is no longer Practiced (possibly a 🌸 day); re-practicing deletes it.
- **ST-05 readiness:** `SELECT local_date, mood, energy, effort FROM check_in WHERE account_id = … AND local_date BETWEEN …` (PK range), weekday from `local_date`, a join to `moon_day`, tag frequencies via `unnest(tags)`. Compute server-side in `domain/stats.py` (ADR-0020). Empty rows are skipped. Trends describe, never advise (§1).

## 9. Test plan
- **Domain:**
  - `check_check_in` bounds (0, 1, 5, 6, None), slot 2 rejected; `is_empty`.
  - The tag order: body first (6 tags), then mind (4); `TAG_GROUPS` covers every tag.
  - `offer_mood_row`: today ✓, yesterday ✓, 2 days ago ✗, setting off ✗, existing check-in ✗, existing empty check-in ✓.
- **Use case (fakes, fixed clock):** a patch sets only its field; a not-practiced day raises `DayNotPracticed`; a tag on/off is absolute (on twice = once); clear twice; `GetDays` maps an empty row to none; `UpdateProfile` patches `offer_check_in` alone (null → default true).
- **Infrastructure (real Postgres, `db` marker):**
  - Writes: the EXISTS guard (no row on a rest day or with no day); a partial patch; `set_tag` is idempotent and atomic under two concurrent taps.
  - Lifecycle: status → rest deletes the check-in **in the same statement**; rest → 🧘 doesn't bring it back (accepted); re-🧘 keeps it; `ClearPractice` keeps it; clearing the day cascades.
  - Reads: `_range` joins only practiced days and stays one statement; unknown stored tags are dropped on read.
  - Schema: the `account.offer_check_in` default; every CHECK; 0012 upgrade → downgrade → upgrade; `alembic check`.
- **API contract:** 401; PUT 200 / 409 / 422 (scale 6, unknown tag, slot 2); DELETE 204 twice; `/me/days` carries `check_ins`; `GET /me` and `PATCH /me` `offer_check_in` (true / false / null / omitted); the catalog has `check_in_tags` in order and its ETag changes when the tags change; the OpenAPI lists `invalid_check_in` and the `CheckInTag` enum; the TS client builds.
- **Bot handler (fake use cases, fixed clock):**
  - Offering: the mood row on P and V for today and yesterday only while there's no check-in and the setting is on; a day 2+ days back, or the setting off, shows only ✨; with a check-in, the summary plus ✨.
  - Taps: a mood tap saves and renders K; the ✓ chip carries `0`; T toggles with ✓; Back → K; Remove → V; after ✅ (PR-10), V decides with no extra read.
  - Failures: a not-practiced day → the status screen with the note; malformed `k1:` data is ignored.
  - Settings: the `/settings` line and the `s1:k:0`/`s1:k:1` toggle.
  - Callbacks and copy: **every `k1:` and `s1:k` callback round-trips and is ≤ 64 bytes**; the tag codes are unique and complete (`d` = scattered); en/ru keys exist and format; no avoided words appear in the `checkin-*` strings.
- **Mini App (Vitest):**
  - Display: the block shows only on Practiced; it's open for the server's today/yesterday with the setting on, collapsed to ✨ otherwise.
  - Saving: a chip tap PUTs the whole body optimistically and rolls back on error; tapping a pressed chip clears it; Remove sends DELETE.
  - Data: tags come from the catalog; a payload without `check_ins` (an old server) renders; aria labels.
  - The settings switch saves optimistically and rolls back on error; the bundle check passes.
- **Architecture:** import-linter (domain pure, aiogram only in `bots/telegram`).

## 10. Decisions (owner + ashtanga-expert, 2026-10-27)
1. ✅ **Plain, owner-only** (ADR-0024). The owner accepted it knowing mood and soreness may be health-adjacent under GDPR; the sealed fallback stays in ADR-0024's Alternatives.
2. ✅ As recommended: three optional 1–5 scales (mood emoji, energy, effort), with body feel expressed through the tags.
3. ✅ As recommended: attached to the practice slot, deleted when the day changes to another status (Rest by mistake then 🧘 loses it, accepted), kept by "Remove details".
4. ✅ **Changed:** the mood row is offered on P and V **only for today or yesterday** (user's zone) and until a check-in exists. Older practiced days get only `[✨ Check-in]`. A new setting, **"Offer a check-in after practice"** (on by default), lives in bot `/settings`, Mini App Settings and `PATCH /me` (`account.offer_check_in`, migration 0012). There's no auto-detection and no message about it.
5. ✅ As recommended: tags in code plus `.ftl`, served through `/catalog`. Final list (expert): stiff, open, strong, light, heavy, sore | focused, calm, **scattered** (replaces sleepy), steady breath. No bandha or drishti tags, and no pain or injury tag.
6. ✅ **The note waits for PR-07** (one place for private text); PR-07 adds `[📝 Note]` on K.
7. ✅ As recommended: check-ins show only on your own day screens until ST-05.
8. ✅ **Teachers: hidden now.** A future ST-06 opt-in is **per teacher, off by default**, and its scope (mood vs body tags only) is decided at ST-06. A teacher view must never show "check-in missing".
- **Expert copy fixes** are applied in §6: effort is «Усилие» with 🔥, `checkin-prompt` no longer says "one tap is enough", RU «Ноющие мышцы», «Как тело и ум? Отметь, что подходит.», «Убрать самочувствие», and the longer avoid-word list. §1 now rules out inferences or advice from check-ins.
