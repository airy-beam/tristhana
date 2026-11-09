# GM-02: badges (a quiet collection to look back at)

- Status: **accepted** (owner, 2026-11-09; ashtanga-expert reviewed 2026-11-09; ux-writer finalises copy) · Size S, Phase 3
- Requirements: **GM-02** (badge ideas in `10 Naming & Branding`). Reuses **GM-01** (practice definition, `practice_milestone` ledger, avoid-word list), **PR-08** (progression events, `Track`, milestone items), **ST-01..03** (Practiced = a practice; run rules compared in §3), **MD-02** (effective moon calendar), **PR-09** (`joined`, auto-rest), **WH-01** (rest periods). Touches **ST-09** (export, §5), **ST-06** (teachers: hidden), **ST-07** (no card yet). Resolves **Q57**.
- Related: ADR-0016, 0017, 0019, 0022, 0023, 0026, 0028, 0032. New: **ADR-0041** (Accepted): read-time projection, no badge table, definitions in `data/seed/badges.yaml` over a closed set of rule kinds.

## 1. Scope
**In:** a Mini App **Badges** screen (lazy) listing the badges a person has, each with an icon, a name, one line of meaning and the date it came from; a first set of 20 badges (§2: 12 practice, 8 asanas) computed from data we already store; badge definitions as seed data; `GET /api/v1/me/badges`.
**Out:** any 🎉, push or bot message at earn time (GM-01 already celebrates 100/365/1000 and the asana steps; a badge is never a second celebration); a bot screen (later with bot `/stats`, Q32); share cards (Q246); teacher or shala views; unearned / locked badges, progress bars, "N to go" (Q243); leaderboards or comparisons (GM-03); Full Moon Cycle, Lunar Year, Mysore Pilgrim (Q245); anything read from attendance (ADR-0039 keeps attendance apart from the log).

**Tone:** a record of showing up, never a score. Badges appear by themselves; nothing says "earned", "unlocked", "lost", "streak", "goal" or "next". No badge reveals a 🌸 day. "Gate" is an internal word only, never in copy.

## 2. First set (`data/seed/badges.yaml`, display order = file order)
| Key · icon · name (EN / RU) | Rule kind and parameters | Date shown |
|---|---|---|
| `ekam` 🌅 Ekam / Экам | `practices` 1 | the first practised date |
| `nava` 🔢 Nava / Нава | `practices` 9 | the 9th practised date |
| `shatam` 💯 Shatam / Шатам | `practices` 100 (GM-01 ledger keeps it) | 100th date |
| `count-108` 📿 108 | `practices` 108 (Q57: quiet, no 🎉) | 108th date |
| `count-365` 🗓 365 | `practices` 365 (ledger keeps it; no "year" wording) | 365th date |
| `sahasra` ✨ Sahasra / Сахасра | `practices` 1000 (ledger keeps it) | 1000th date |
| `mandala` 🪷 Mandala / Мандала | `run` 40: 40 practices in a row, rest days of every kind transparent (Q235) | the 40th practice of the first such run |
| `before-dawn` 🌄 Before dawn / До рассвета | `early_start`: 10 practices started before 06:00 local (Q237) | the 10th |
| `led-by-the-count` 🎙 Led by the count / Под счёт | `context` led, 10 | the 10th |
| `self-practice` 🏠 Self-practice / Своя практика | `context` self, 30 (Q238) | the 30th |
| `rest-is-practice` 🫶 Rest is practice / Отдых — тоже практика | `moon_rest` 10 (Q236) | the 10th such moon date |
| `return` 👣 Return / Возвращение | `return` 14: a practice after ≥ 14 days with none (Q239) | the first such practice |
| `yoga-chikitsa` 1️⃣ Yoga Chikitsa · the full Primary series | `series_complete` primary | event date |
| `nadi-shodhana` 2️⃣ Nadi Shodhana · Intermediate begins | `series_begins` intermediate | event date |
| `supta-kurmasana` 🐢 · `kapotasana` 🕊 · `karandavasana` 🦆 (catalog names, no variant letter: the client drops it, so the B stop shows as "Kapotasana") | `stop` primary/supta-kurmasana, intermediate/kapotasana-b (the catalog's stop: A and B are given together, after B), intermediate/karandavasana (Q240) | event date |
| `drop-backs` 🏹 · `standing-up` ⤴️ · `tic-tacs` 🎡 (labels from `milestone-label`, RU «тик-токи», Q53) | `item` drop-backs, standing-up, viparita-chakrasana | first `item_given` date (quick removals ignored, §3) |

Icons avoid the status emoji (🧘 Practiced, 🌱 No practice, 🌙 moon, 😌 rest). Item icons by ux-writer (above). Not in the set: Q245.

## 3. Domain (pure) `domain/badges.py`
```python
class RuleKind(StrEnum): PRACTICES, RUN, CONTEXT, EARLY_START, MOON_REST, RETURN,
                         SERIES_COMPLETE, SERIES_BEGINS, STOP, ITEM
class Group(StrEnum): PRACTICE, ASANAS
@dataclass(frozen=True, slots=True)
class BadgeDef: key; group; icon; rule: RuleKind; count: int | None; days: int | None
                before: time | None; context: PracticeContext | None; target: Position | None; item: str | None
@dataclass(frozen=True, slots=True)
class BadgeFacts: logged: Mapping[date, DayStatus]      # plain `status` only (🌸 is stored as REST)
                  covered: frozenset[date]               # dates inside a rest period (kind never read)
                  moon: frozenset[date]                  # effective calendar, first logged date .. today
                  led: tuple[date, ...]; self_: tuple[date, ...]; starts: tuple[tuple[date, time], ...]
                  kept_counts: frozenset[int]; events: tuple[ProgressionEvent, ...]  # position + item events, oldest first
@dataclass(frozen=True, slots=True)
class Earned: badge: BadgeDef; on: date | None; at_record_start: bool  # .key property
def earned(defs, facts, track, *, off: DayOff, joined: date, today: date) -> tuple[Earned, ...]
def validate(defs, track) -> None   # loader: unique keys, params present, series confirmed,
                                    # target a stop, item a milestone item, ≤ 40 badges
```
- **A practice** = a Practiced day, once per day (GM-01 Q1). `practiced` = sorted dates with `PRACTICED`.
- **A rest date** (one set, used by `run` and `moon_rest`) = logged status in `REST_LIKE` (rest incl. 🌸, moon, sick, travel) ∪ unlogged dates in `covered` ∪ `auto_days(…, joined, logged, off, moon, covered)` (PR-09 auto 🌙 / 😌, reused as is). All kinds are one set, so 🌸 is indistinguishable by construction.
- `practices n`: `len(practiced) ≥ n` → the n-th date; else if `n ∈ kept_counts` → shown with `on = None`.
- `run n` (Mandala): walk dates from the first practice to `today`: P adds 1; a rest date is transparent; **N ("No practice") or an unlogged non-rest date before today ends the run**; an unlogged today never ends it. Earned on the date the first run reaches n. **vs ST-01 runs:** same P/R/N treatment, but ST-01 bridges up to 7 unmarked days (`MAX_UNLOGGED_BRIDGE = 7`) and sees auto-rest as unmarked; Mandala bridges **0** unmarked days and sees auto-rest and rest-period dates as rest. Chosen (simplest correct): a separate ~15-line loop in `badges.py` over the rest-date set, not a parameterised `find_runs` (its input has no auto/covered days, and Stats must not change). Unlogged dates before `joined` get no auto-rest, so they end a run, exactly as the calendar shows them (·); marking them fixes it.
- `context(c, n)` / `early_start(before, n)`: the n-th date. Slot 1 only (Q31), and only on a Practiced date (a stale practice row on a day now logged otherwise never counts). The facts carry the start times (`starts`), so the threshold stays in YAML, not in SQL. Early = `start_time < before` on the practice's own wall clock (its stored zone), so travel never shifts it.
- `moon_rest(n)`: the n-th date of `moon ∩ rest dates` (logged 🌙/😌/🌸/sick/travel, period-covered, or unlogged auto-🌙 since `joined`). Practiced, N and unlogged-before-`joined` moon dates don't count. Sick/travel count because they are rest kinds (owner: "rest of every kind").
- `return(days)`: the first i ≥ 1 with `gap_days = practiced[i] − practiced[i−1] − 1 >= days` (days = 14: at least 14 consecutive days with no practice before this one). Never the first practice.
- `series_complete` / `series_begins` / `stop`: the first `START`/`GIVEN`/`CHANGED` event whose target rank ≥ the rank of the series' last stop / first stop / the stop (`Track.rank`; stale keys ignored). `at_record_start` = that event is the `START`. **Quick corrections are ignored (owner, 2026-11-09):** an event does not count if the next position event is a `CHANGED` below the badge's stop on the same local day, or with no Practiced day strictly between the two dates (a mis-tap). A step back after a practised day keeps the badge; a correction that stays at or past the stop keeps the first date; a later give counts on its own date. Undo removes it (ADR-0041). Teacher marks count like own gives, and a student's correction of one follows the same rule.
- `item`: the first `ITEM_GIVEN` for it; a later removal keeps it, unless it was quick (same rule as above, with `ITEM_REMOVED`).

## 4. Application, ports, infrastructure
- **Use case** `GetBadges(badges, track, cities, clock).execute(principal) -> BadgesView(earned)`. Owner only: `can_view_milestones` (Q59; no new policy). Zone = account zone or provisional; `today` local; moon location = `moon_follow_of(account, cities).city.slug` (MD-02, incl. the Mysuru default); `joined(account, zone)` and `account.day_off` passed to `earned`.
- **Port** `application/ports/badges.py`: `BadgeFactsRepository.facts(account_id, moon_location, today) -> BadgeFacts`, on `Storage.badges`. **One statement**, scalar subqueries: `(local_date, status)` from `day_log` (PK range; `sealed_status` never selected), Led/self/early dates (`practice` slot 1 by PK), rest-period date ranges (plain dates only; sealed kind never selected), the effective calendar's `moon_day` dates from the first logged date to today, GM-01 ledger thresholds, position and item events incl. removals (index `(account_id, id)`).
- **Seed** `infrastructure/seed/badges_yaml.py`: strict pydantic loader (as `milestones_yaml.py`), loaded at startup, `validate` against the `Track`. A backend test checks every YAML key has `badge-<key>` (+ `.about`) in the Mini App's en and ru `badges.ftl` (Q244).
- **Cost:** realistic accounts (≤ 1 000 days) ~2–5 ms; DB test asserts < 30 ms on a 9 000-day account, then O(n) in memory. Bot and day write: **no change**.

## 5. API, privacy, export
| Method, path | Auth / policy | Response |
|---|---|---|
| `GET /api/v1/me/badges` | initData; owner (`can_view_milestones`) | `BadgesOut {badges: [BadgeOut {key, group: "practice"\|"asanas", icon, earned_on: date \| null, at_record_start: bool, count: int \| null, days: int \| null, before: "HH:MM" \| null, series: slug \| null, stop: key \| null, item: key \| null}]}`, earned only, in file order |

401/503 as the router; no new `ErrorCode`. `count`/`before` feed the Fluent copy; stop and item names come from the cached `/catalog` and `milestone-label`. Unknown keys (an older Mini App) are skipped. Regenerate the client (`gen:api`).
- **Teachers / shalas:** never (Q59). **Logs:** account uuid only. **Export / delete (ST-09):** nothing stored, nothing new (Q242).

## 6. Surfaces
- **Mini App:** a "🏅 Badges" row on 📊 My practice (Stats is already lazy) → `screens/badges/Badges.tsx` (`React.lazy`, Telegram BackButton). Two groups, "Practice" and "Asanas"; each row: icon, name, date (`Intl` short date, `timeZone: "UTC"` on the date string) or `badges-at-start`; tap expands the `.about` line inline. "New" pill on keys not in `localStorage["badges.seen"]`. Empty state `badges-empty`. No haptics, no animation. My practice stays mounted (hidden) under it, so Back returns to the same month and scroll. A failed `/badges` or `/catalog` shows `badges-load-failed`. Chunk ≈ 3.6 KB gzip (both `.ftl` files inside).
- **Bot:** nothing (Q241). **Share:** nothing yet (Q246).

## 7. i18n (Mini App `badges.ftl`, en/ru parity; «ты»; ux-writer finalises)
- Screen: `badges-open` "🏅 Badges" / «🏅 Значки» (in `app.ftl`: the only initial-bundle key), `badges-title`, `badges-group-practice` "Practice" / «Практика», `badges-group-asanas` "Asanas" / «Асаны», `badges-new` "New" / «Новое», `badges-at-start` "From the start of your log" / «С начала журнала» ("record" is on the GM-01 avoid list), `badges-empty` "Badges appear here by themselves as you log your practice." / «Значки появляются здесь сами, по мере того как ты ведёшь журнал.», `badges-note` "Badges are just for you; teachers don't see them." / «Значки видны лишь тебе, учителям — нет.» ("only"/«только» are on the PR-08 list), `badges-load-failed`
- Per badge `badge-<key>` + `.about` (RU counts via Fluent plurals):
  - ekam "The first practice in your log." / «Первая практика в журнале.» · practices `{ $count } practices in your log.` / «{ $count } практик(а/и) в журнале.»
  - nava: "Nine practices, as many as the vinyasas of Surya Namaskara A." / «Девять практик — по числу виньяс Сурья Намаскар А.»
  - mandala "{ $count } practices without a break; rest days are part of it." / «{ $count } практик без перерыва; дни отдыха — её часть.»
  - before-dawn "{ $count } practices started before { $before } local time." / «{ $count } практик, начатых до { $before } по местному времени.»
  - led-by-the-count "{ $count } Led practices." / «{ $count } практик под счёт» · self-practice "{ $count } practices on your own." / «{ $count } практик самостоятельно.»
  - rest-is-practice "{ $count } moon days of rest." / «{ $count } лунных дней отдыха.»
  - return "Back on the mat. Welcome back." / «Снова на коврике. С возвращением!» (no duration)
  - yoga-chikitsa / nadi-shodhana: the name is always the pair (table §2; RU «Йога Чикитса · вся Первая серия», «Нади Шодхана · начало Второй серии»). This replaces the draft's "traditional names Primary/Intermediate only" note: that PR-08 rule means only these two series have a traditional name, never that it replaces the plain one; badges always show both. `.about`: "Yoga therapy: the whole Primary series became part of your practice." / «Йога-терапия: вся Первая серия вошла в твою практику.»; "Cleansing the channels: the first asanas of Intermediate became part of your practice." / «Очищение каналов: первые асаны Второй серии вошли в твою практику.»
  - Shared lines use the `badges-` prefix (`badges-stop-about`, `badges-item-about`, `badges-practices-about`) so no badge key can match them; not Fluent terms, which take literal arguments only.
  - stops: `badges-stop-about` "{ $asana } became part of your practice." / «{ $asana } вошла в твою практику.» (agrees with the asana, all stops end in -асана; never with the person) · items: `badges-item-about` "{ $item } became part of your practice." / «{ $item } — теперь часть твоей практики.» (plural-safe). No got/reached/mastered/gate.
- Fluent `NUMBER` grouping ("1,000" / «1 000», Q61). **Avoid-word grep** over `badge*`: GM-01 §7 list (minus "badge"/«значок») + earn, unlock, achievement, collect all, next, lost, gate, mastered; RU заработ, разблок, достижен, следующ, потер, освоил. No gendered past tense about the person in RU.

## 8. Cross-cutting checks
- **Time zones:** rules work on local `date`s, zone-correct at write; `today` and `joined` in the account zone (provisional allowed); early start compares each practice's own wall clock (no instant, so no city label; "local time" in the copy); dates shown date-only, formatted in UTC. Test: Kiritimati vs Honolulu; a 05:30 practice logged in Almaty, then a move to Moscow, stays early.
- **Privacy:** owner-only; plain columns only, `sealed_status` and rest-period kinds never selected; every rest kind is one set, so a 🌸 day behaves exactly like 😌 (Mandala, Rest is practice); Return reads practised dates only; no badge implies SYC endorsement (Q81).
- **i18n:** all copy in `badges.ftl` + one `app.ftl` key; parity + variable tests; catalog names for asanas.
- **Responsiveness:** one GET, one indexed statement, no write-path change; lazy chunk; initial bundle +≈ 0.05 KB. Target < 300 ms p50 warm.

## 9. Test plan
- **Domain:** each rule kind at n−1 / n / n+1; `practices` kept via `kept_counts` (on = None), not for 108; **`run`**: 40 P with logged 🌙/😌/sick/travel/REST(🌸) and auto-🌙/😌 and period-covered dates between → earned on the 40th P; one N at P39 → not; one unlogged non-rest weekday → not; ST-01's 7-day bridge does *not* apply; unlogged today doesn't end it; unlogged day off before `joined` ends it; **`return`** at 13 vs 14 empty days between practices, never on the first; `early_start` 05:59 vs 06:00; **`moon_rest`**: logged 🌙, 😌, REST(🌸), sick, travel, period-covered and unlogged auto-🌙 all count; P, N and pre-`joined` unlogged don't; asana badges via START (`at_record_start`), a multi-stop jump crossing Supta Kurmasana, Kapotasana only at B, Change-down keeps, stale keys ignored, teacher give counts; `item` kept after removal; `validate` rejects bad series/stop/item, duplicates, missing params.
- **Use case (fakes, fixed clock):** owner only; moon location via `moon_follow_of` (own, follow-teacher, Mysuru default); `joined` and `day_off` passed; output order = file order.
- **DB (real Postgres):** one statement (counter); `sealed_status` absent from the compiled SQL; a 😌 row and a sealed 🌸 row on a moon date yield identical facts (no key in the test); Led/self/early slot 1 only; `tristhana_app` role read; < 30 ms on 9 000 days; `alembic check` clean (no migration).
- **Seed:** loader rejects malformed YAML; shipped file validates; every key has en + ru entries.
- **API:** 401; empty account → `[]`; payload shape; OpenAPI + TS client build.
- **Bot:** none (no change; suites stay green).
- **Mini App (Vitest, `TZ=UTC` too):** entry on Stats; groups; dates and `at_record_start`; New pill then seen; unknown key skipped; empty state; RU plurals 1/2/5/21/40/108/1000; series names paired; avoid-word grep; `check:bundle`.
- **Architecture:** import-linter (domain pure; badges never import attendance).

## 10. Open questions (all answered by the owner, 2026-11-09)
233. **Derived, no badge table** (ADR-0041). **Answer: as recommended.**
234. **First set** = the 20 in §2. **Answer: as recommended** (with the renames below).
235. **Mandala.** Draft: 40 practised days within 56 days. **Answer: 40 practices in a row; rest days of every kind (day off, 🌙, 😌, 🌸, sick, travel, auto-rest) don't break it; only "No practice" or an unlogged non-rest day does.** Rule kind `run` (§3): ST-01's P/R/N logic with a 0-day unmarked bridge and auto-rest as rest.
236. **Rest is practice.** **Answer: moon dates (own effective calendar) whose status is any rest kind from the plain column (🌙, 😌, 🌸 stored as rest, plus auto-🌙); never read sealed fields; 🌸 indistinguishable; 10 days.** Sick/travel and rest-period dates on a moon date count too (they are rest kinds; consistent with Q235).
237. **Answer: renamed "Before dawn" / «До рассвета»** (key `before-dawn`), 06:00 local threshold in YAML, 10 practices.
238. **Answer: as recommended** ("Self-practice" / «Своя практика», context `self`).
239. **Return. Answer: as recommended**; copy "Back on the mat. Welcome back." (no duration); rule exactly ≥ 14 consecutive days with no practice before it.
240. **Gate postures. Answer: as recommended** (Supta Kurmasana, Kapotasana at the B stop, Karandavasana); "gate" never in copy.
241.–246. **Answer: as recommended** (no bot surface/earn-time note; nothing new to export; only badges a person has; lazy `badges.ftl`; Full Moon Cycle, Lunar Year, Mysore Pilgrim deferred; share cards later).
247. **Answer: «Значки».**
Q57. **Answer: 108 stays quiet** (a badge, no 🎉).
