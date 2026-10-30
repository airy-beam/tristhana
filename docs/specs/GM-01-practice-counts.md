# GM-01 part 2: practice-count milestones (100 / 365 / 1000 practices)

- Status: **accepted** (architect + ashtanga-expert review, 2026-10-30; owner: all as recommended, 2026-10-30) · Date: 2026-10-30 · Size S, Phase 2
- Requirements: **GM-01** ("100/365/1000 practices"; part 1 = PR-08). Touches **PR-01/PR-04** (the day-status write), **PR-10** (reminder ✅ / 🧘), **ST-01..03** (what "a practice" is), **ST-09** (export, delete), **NT-01** (milestones category: not needed yet, §5).
- Related: ADR-0016, 0017, 0020, 0022, 0026 (it deferred this ledger), 0027. New: **ADR-0028** (a "seen" ledger written inside the day-status statement; accepted).

## 1. Scope
**In:** one 🎉 line when a person's number of practised days reaches a threshold (100, 365, 1000), shown **in reply to their own tap** that made it so: bot `/log` and the `/start` grid, the reminder ✅ and 🧘, the Mini App Today card and the stats calendar (backfill). A ledger so each threshold celebrates **once ever**. Thresholds as data. Export of the ledger.
**Out:** pushes of any kind (so no NT-01 toggle yet); a lifetime total on stats or Home (§11 Q11); GM-02 badges (108, Mandala, Ekam, Shatam/Sahasra names); share cards (ST-07); teacher views (ST-06); "next milestone in N" or any countdown; anything about consecutive days (runs stay ST-03's "in a row", never mixed with counts).

**Tone:** a quiet thank-you for showing up, never a score. No "streak", "goal", "record", no countdown, nothing when the count goes down.

## 2. Domain (pure) `domain/milestones.py`
```python
def counts_as_practice(status: DayStatus) -> bool   # PRACTICED only
@dataclass(frozen=True, slots=True)
class PracticeCounts:                                # loaded from data/seed/milestones.yaml
    thresholds: tuple[int, ...]                      # validated: 1..100_000, strictly ascending, ≤ 12
    def seen_by(self, count: int) -> tuple[int, ...] # thresholds ≤ count (recorded, maybe silently)
    def reached(self, count: int) -> int | None      # the threshold equal to count (celebrated)
# domain/progression.py (reused, PR-08): CelebrationKind += PRACTICE_COUNT; Celebration += count: int | None
```
- **A practice = a day whose status is Practiced** (Q1). Any context (Mysore, Led, 1:1, self-practice, online), no details, pranayama-only and a practice logged on a moon day all count. Rest, 🌙, 🌸, sick, travel, 🌱 No practice, auto-rest (ADR-0022) and pause-covered days (ADR-0023) never count; they aren't Practiced rows. A day counts **once**, whatever its slots (Q31: slot 2 ignored). Same definition as ST-01's "practiced". Any future activity-type change (e.g. pranayama in slot 2) must keep this definition or revisit GM-01.
- **Count = all practised days ever**, by date, not by when they were logged. One write changes it by at most ±1.
- **Rule** (ADR-0028): when a write makes a day Practiced that wasn't (new day, or another status → 🧘), let `after` = practised days including it. Every threshold ≤ `after` goes into the ledger if absent; the one **equal** to `after` and newly inserted is the celebration. Thresholds below `after` that were missing are **seeded silently** (existing users at deploy, a threshold added later). Clearing a day or changing it away from 🧘 never touches the ledger; a later rise past a seen threshold is quiet (Q3).
- **Thresholds are data** (Q2): `data/seed/milestones.yaml` → `practice_counts: [100, 365, 1000]`, loaded at startup in memory with the other seed files (ADR-0017 pattern, strict loader, the validation above). Adding 500 later is a data change with no migration: the silent seed covers people already past it.

## 3. Application and infrastructure
- **Port changes** (`application/ports/days.py`): `DayLogRepository.upsert(account_id, day, timezone, thresholds)` and `insert_if_absent(…, thresholds)` take the thresholds; `Upserted` and `Inserted` += `reached: int | None`. Fakes implement the rule with `PracticeCounts`; the SQL mirrors it (a parity test, §10).
- **Use cases:** `SetDayStatus`, `QuickLogSameAsLast`, `LogFromReminder` get `PracticeCounts` injected. `DaySaved` and `QuickLog` += `celebrations: tuple[Celebration, ...]` (`Celebration(PRACTICE_COUNT, count=n)` or empty). `ClearDayStatus`, practice-detail saves and rest periods are unchanged: they never make a day Practiced. No new use case, no read.
- **One statement, no new round trip** (Q4): `SqlDayLogRepository.upsert` adds two CTEs **only when the new status is Practiced** (other statuses build exactly today's SQL):
  ```sql
  n    AS (SELECT count(*) + 1 AS after FROM day_log
           WHERE account_id = :a AND status = 'practiced' AND local_date <> :d),
  seen AS (INSERT INTO practice_milestone (account_id, threshold, celebrated)
           SELECT :a, t, t = n.after FROM n, unnest(CAST(:thresholds AS int[])) AS t
           WHERE t <= n.after AND NOT <was_practiced>     -- the existing snapshot EXISTS
           ON CONFLICT DO NOTHING RETURNING threshold, celebrated)
  … RETURNING …, (SELECT max(threshold) FROM seen WHERE celebrated) AS reached
  ```
  `insert_if_absent` does the same gated by its existing `empty` predicate (a reminder tap on a logged day writes nothing). Every CTE sees the pre-statement snapshot, hence `local_date <> :d` + 1. Data-modifying CTEs always run, like today's `gone` / cut CTEs.
- **Cost:** one aggregate over one account's `day_log` rows through the PK `(account_id, local_date)`: ≈ 365 rows after a year, ≈ 9 000 for 25 years of backfill. Sub-millisecond to a few ms server time, against a < 300 ms p50 budget dominated by Telegram and the DB network round trip, which stays one. Not a counter column (drift, a second hot row; ADR-0028). The DB test asserts < 5 ms on a 9 000-day account; **only if it fails**, 0017 adds a partial index `day_log (account_id) WHERE status = 'practiced'` (index-only count).
- **Races:** two concurrent 🧘 writes at 99 both compute 100; the ledger PK lets one insert win, so one 🎉 (the other reply shows none; the real count 101 is fine). Read Committed, no lock added.
- **Policy:** own data only (`Principal`); `can_view_milestones(viewer, student)` = owner (named for ST-06, Q12). Not sensitive, not sealed (a threshold and a timestamp; a 🌸 day is stored as rest and never counts either way, so the ledger reveals nothing about it).
- **ST-09:** the export adds `practice_milestones: [{count, reached_at, celebrated}]` to `data.json` (additive, schema stays `tristhana.export/1`); no CSV. Account delete cascades (FK).

## 4. API (initData auth; additive; regenerate the client with `gen:api`)
| Method, path | Change |
|---|---|
| `PUT /api/v1/me/days/{date}` | `DaySaved` += `celebrations: [CelebrationOut]` (default `[]`; at most one `practice_count`) |
| (shared schema) | `CelebrationOut.kind` += `practice_count`; `CelebrationOut` += `count: int \| null` (null for the PR-08 kinds) |

Note: the trigger is the **day** PUT, not `PUT …/practice` (details never change the count). No new endpoint, no error codes. A lost reply loses the card (the ledger already has the row); accepted, as in PR-08. `DELETE /me/days/{date}` unchanged.

## 5. Where it shows (bot and Mini App)
- **Bot** (no new callbacks or prefix): the 🎉 line goes **on top of the screen the tap already edits in place**, via the existing `lead` lines: `/log`, `/start` grid, day picker 🧘 → P (`practice.details(…, lead=…)`); reminder 🧘 → P; reminder ✅ "same as last time" → the practice summary (`summary` gets the same `lead` parameter). Already-logged reminder taps write nothing, so they never celebrate. No sticker, no separate message (PR-08 Q12). Round trips: **unchanged** (+0).
- **Mini App:** `TodayCard` and the stats `DayEditor` (backfill) show the existing `CelebrationCard` from the PUT **response** (`onSuccess`; the day write stays optimistic, the card waits for the server), with `notificationOccurred("success")`, reduced motion respected, tap to dismiss. `progressionText.ts` formats `practice_count`. Budget ≈ +0.2 KB initial (the card is already in the initial bundle), no dependency.
- **No push** (Q5): the line only answers the person's own tap, so the NT-01 milestones toggle isn't needed. It lands with the first milestone push (e.g. a weekly recap), as PR-08 Q14 did.

## 6. Backfill and corrections
- Backfilling a past day that makes the count reach 100 **celebrates** (Q6): it is the hundredth practice in the log, whenever it happened. The copy says "in your log" and never names a date, so it reads true.
- A mis-tap that reaches 100 and is then cleared has spent its 🎉; the real hundredth is quiet (Q9; like PR-08 Q51).
- Existing accounts already past a threshold at deploy: **silent** (Q3). Their next 🧘 write seeds every threshold below the count with `celebrated = false`. No data migration needed. Today's beta accounts are about two weeks old, so this matters only for people who backfilled.

## 7. i18n (`bot.ftl` + `app.ftl`, en/ru parity; «ты»; ux-writer + ashtanga-expert polish; drafts)
- `celebrate-practice-count`, EN: `🎉 { $count } { $count -> [one] practice *[other] practices } in your log. Thank you for coming to the mat.` RU: `🎉 { $count } { $count -> [one] практика [few] практики *[many] практик } в журнале. Спасибо, что приходишь на коврик.` (plural categories via Fluent, so any future threshold reads right: 101 практика, 102 практики).
- 365 is **not** "a year" (with weekly days off and moon days, it's well over a year): no year wording.
- **Words to avoid** (the PR-08 test grep, extended to `celebrate-practice-count`): PR-08's list (unlock, level, achieve, earn, finally, behind, lost, regress, back to, demote, only, again, streak, rank, goal, should, faster; RU уровень, достижен, разблок, наконец, откат, потер, отстал, только, опять, цель, надо, должен) **plus** record, best, total, in a row, left, until, badge, year, daily, every day, keep; RU рекорд, лучш, подряд, осталось, до цели, значок, год, ежедневн, каждый день, продолжай, так держать (365 must never read as a year or as daily practice). No gendered past tense in RU.

## 8. Migration `0017_practice_milestone` (expand-only, down_revision `0016`)
- `practice_milestone(account_id uuid not null references account on delete cascade, threshold int not null, celebrated boolean not null, reached_at timestamptz not null default now(), PRIMARY KEY (account_id, threshold))`, CHECK `threshold BETWEEN 1 AND 100000`.
- No backfill (the silent seed is lazy, §6). No sequence, so no grants beyond the 0015 defaults. The old revision ignores the table (its upserts just don't write it); downgrade drops it. No owner step.

## 9. Cross-cutting checks
- **Time zones:** the count is over local `date`s (already zone-correct at write, `check_loggable` unchanged); `reached_at` is UTC audit/export only; no time or date is shown, so no zone label. Test: a 🧘 on Kiritimati's "today" that is still yesterday in Honolulu counts once.
- **Privacy:** no sealed data read; the 🌸 seal is never opened (the count is `status = 'practiced'` on the plain column). Nothing in logs beyond the account uuid. Owner-only.
- **i18n:** one key per app, en/ru, Fluent plurals; numbers formatted by Fluent `NUMBER` (RU "1 000" with a CLDR group separator, EN "1,000"; tests don't hard-code the separator, and one test checks that Babel (bot) and Intl (Mini App) agree).
- **Responsiveness:** zero extra round trips on every path; the extra SQL exists only on 🧘 writes; the callback is answered first and the edit happens in place, as today. No outbound call, no new dependency, nothing lazy-imported.

## 10. Test plan
- **Domain:** `counts_as_practice` for every `DayStatus`; `PracticeCounts` validation (empty, unsorted, duplicates, 0, > 100 000, > 12); `seen_by` / `reached` at 99, 100, 101, 364, 365, 1000 and with `[500]` added later; loader rejects a malformed `milestones.yaml`.
- **Use case (fakes, fixed clock):** 99 → 🧘 → `celebrations = [100]`; re-tap 🧘 on the same day → none; 🧘 → 😌 → 🧘 at 100 → none; clear to 99 and log again → none; backfill crossing 100 → celebrates; existing 250 with no ledger → silent seed of 100, nothing shown; `[100, 500]` added for a person at 700 → silent; reminder ✅ / 🧘 on an empty day crossing → celebrates; on a logged day → none; non-practiced statuses never call with a celebration.
- **DB (real Postgres):** upsert and `insert_if_absent` remain **one statement** (statement counter) with and without the CTEs; parity with the domain rule over random sequences of set/clear across 0–1 100 days; snapshot correctness (`local_date <> :d` + 1); two concurrent 🧘 at 99 → one ledger row, one `reached`; 🌸 and rest days never counted; timing on a 9 000-day account < 5 ms (else the partial index); cascade on account delete; `test_db_app_role` writes the ledger as `tristhana_app`; 0017 up → down → up; `alembic check`.
- **API:** `PUT /me/days/{date}` returns `celebrations: [{kind: "practice_count", count: 100, …}]` once, then `[]`; non-practiced → `[]`; OpenAPI shows the new kind and field; old clients ignore it; the TS client builds.
- **Bot (fake use cases):** `/log` 🧘 crossing → P edited in place with the 🎉 line on top; `/start` grid likewise; reminder 🧘 → P with the line; reminder ✅ → summary with the line; already-logged reminder → no line; no new message sent; avoid-word grep over `celebrate-practice-count` (en/ru).
- **Mini App (Vitest):** TodayCard and DayEditor show the card only from the server response (not optimistically), haptic fires, reduced motion, tap dismisses; RU plural rendering for 100/101/102/365/1000; a payload without `celebrations` renders; bundle check.
- **Export:** `practice_milestones` present and ordered; schema string unchanged.
- **Architecture:** import-linter (domain pure, aiogram only in `bots/telegram`).

## 11. Open questions (recommended answer first)
1. **What counts as a practice?** A day with status Practiced: any context incl. Led and self-practice, online, no details or pranayama-only, and practice on a moon day. Rest, moon, 🌸, sick, travel, No practice, auto-rest and pause days never count; a day counts once (slot 2 ignored, Q31). Recommended.
2. **Thresholds:** 100, 365, 1000 only (the requirement) in `data/seed/milestones.yaml`, not code. 108 stays a GM-02 badge (it would fire about a week after 100); 500 can be added later as a data change. Recommended.
3. **Seen ledger, once ever:** `(account, threshold)`; dropping below and rising again is quiet; accounts already past a threshold at deploy are **seeded silently** on their next 🧘 (not one late celebration). Recommended.
4. **One statement:** two CTEs in the existing day upsert / reminder insert, only on 🧘 writes; no counter column; the partial index only if the 9 000-day timing test fails. Recommended.
5. **Where:** only in the reply to the person's own tap (bot `lead` line on the screen being edited; Mini App card from the day PUT). **No push**, so no NT-01 milestones toggle now. Recommended.
6. **Backfill crossing a threshold celebrates** ("in your log", no date). Recommended.
7. **Export:** `practice_milestones` in `data.json`, schema stays `/1`, no CSV; delete cascades. Recommended.
8. **Copy:** the drafts in §7 (tail "Practice, and all is coming" vs "Thank you for coming to the mat"); ux-writer + ashtanga-expert to finalise. Recommended (ashtanga-expert): the thank-you tail. The Jois quote is the brand-tagline candidate, so after a number it reads as a slogan, and its imperative feels like pressure.
9. **A mis-tap that reaches 100, then cleared:** the 🎉 is spent, never repeated. Acceptable for now (like Q51). Recommended.
10. **No sticker or separate message** in the bot; the line on top of the edited screen. Recommended; revisit with beta feedback.
11. **A lifetime "N practices in your log" line** (stats or Home): not in this part; consider with bot `/stats` (Q32). Recommended.
12. **Teachers (ST-06):** count milestones not shown to teachers by default; decide at ST-06. Recommended.
