# PR-08: progression ("new asana given 🎉") and progression milestones (GM-01 part 1)

- Status: **accepted** (owner, 2026-10-27: all as recommended; architect + ashtanga-expert) · Date: 2026-10-27 · Size M, Phase 2
- Requirements: **PR-08** (self-marked "new asana given"; current last asana per series + history; the teacher marking it is Phase 3). **GM-01 part 1** (new asana, series complete, next series begins, drop-backs, standing up). Touches **PR-03** (presets: the "my asana" presets PR-02 deferred), **ST-04** (timeline, Phase 3), **ST-06** (teacher view, Phase 3), **ST-09** (export), **NT-01** (milestones category: not needed yet, §1).
- Related: ADR-0008, 0010, 0016, 0017, 0021, 0024. New: **ADR-0026** (one current position per account + an append-only event history; celebrations derived from the history at write time; proposed).

## 1. Scope
**In:** a progression record per account: where the practice ends now (series + last given stop; earlier series are full) and the optional backbending milestones (drop-backs, standing up). Three ways to change it: **set my practice** (first time, or a correction: no celebration), **🎉 new asana given** (forward only, celebrates), **undo** of the latest event. A history (`progression_event`), shown as a short timeline in the Mini App. Celebrations for a new asana, a series completed, the next series begun and a first drop-back / standing up, shown **in reply to the person's own tap** (bot edit in place, Mini App card). New presets "🧘 My practice". A gentle "New asana? 🎉" question after logging a length that ends past the stored last asana. Bot `/asanas`, Mini App "My asanas" screen, API.
**Out:**
- **GM-01 part 2: practice counts (100/365/1000).** Split (recommended, §11 Q1): its trigger is the day-status write (bot `/log`, reminder ✅, Mini App, backfill), the hottest path, which must stay one statement; counts go up and down (clearing a day, backfilling past 100), so it needs a "seen" ledger and its own backfill rule; and it is the first milestone that might be a push, which brings the NT-01 toggle. None of that is needed for asana milestones, which come only from an explicit tap. Part 2 reuses this spec's `Celebration` type and Mini App card.
- Teacher marking, teacher views, permissions (Phase 3; the model has `marked_by`); the full ST-04 timeline and "asanas over time" charts; ST-07 share cards; GM-02 badges (gate postures, 108, Mandala); stickers or a separate animated 🎉 message (§11 Q12); led-class presets; custom sequences (AC-03); a reason field on corrections (never: it would hold health data); **catching heels, binds, jump-backs/jump-throughs** (achievements within an asana, not something a teacher gives); half Primary + Intermediate as a "mine" preset (it stays a custom/recent length).
- **No pushes, no reminders, no "time since your last new asana", no comparisons, no suggestions to move on.** The record never changes by itself: a logged length or a diary note never edits it (the question in §5 always needs a tap).

**Tone:** "practice and all is coming". Forward steps get a short warm line; corrections are neutral and never say lost, back, regress, only or again. A teacher taking an asana away, injury or pregnancy all look like an ordinary change.

## 2. Domain (pure) `domain/progression.py`
```python
class EventKind(StrEnum): START, GIVEN, CHANGED, ITEM_GIVEN, ITEM_REMOVED
@dataclass(frozen=True, slots=True)
class Position: series: str | None; key: str | None   # both None = sun salutations + standing only
@dataclass(frozen=True, slots=True)
class Progression: position: Position; items: frozenset[str]; last_event_id: int | None
class Track:                                       # built once from PracticeCatalog + Catalog
    def rank(self, p: Position) -> int | None      # global order over the stops of confirmed series
                                                   # (standing only = -1); None = stale key
    def next(self, p: Position) -> Position | None # next stop; after the last stop of a series:
                                                   # the first stop of the next confirmed series
    def after(self, p) -> tuple[Position, ...]     # later stops (current + next series), for "Other…"
    items: tuple[str, ...]                         # block items with milestone: true (catalog data)
def last_asana(prog, series) -> str | None         # per-series view: lower series → their last stop
def check_given(track, current, target) -> Position   # forward only (rank > current) else NotForward
def check_position(track, target) -> Position      # a stop of a confirmed series, or standing only
def from_length(length: PracticeLength) -> Position   # last series + end (full → its last stop)
def my_presets(track, prog, recent: list[Practice]) -> tuple[PracticeLength, ...]
def past_last(track, prog, length, context, dismissed) -> Position | None
    # §5 question: Mysore / 1:1 only (Q5), not when (position, target) was dismissed
def celebrations(track, earlier: Earlier, event) -> tuple[Celebration, ...]
def suggest_start(catalog, recent: list[Practice]) -> Position | None
```
- **Granularity = stop points** (`StopPoint.key`), because a stop is where a teacher can let a practice end: Kapotasana A, B is one stop after B, each Marichyasana is its own stop, Virabhadrasana A, B one stop. Non-stop items are never given on their own. Optional milestone **items** (drop-backs, standing up) are separate flags, read from the catalog (`milestone: true`), not code.
- **One current position, lower series implied full** (ADR-0026). "Primary + Intermediate → Kapotasana" is `Position("intermediate", "kapotasana-b")`; `last_asana("primary")` = Setu Bandhasana. A full series stores its last stop explicitly (a fact; stays right if a stop is appended later). This is the per-series record of PR-08 as a projection, and "Primary complete → Intermediate started" needs no extra state. Why this holds (ashtanga-expert, 2026-10-27): in the SYC line Pasasana is given only after full Primary, and Primary with incomplete binds (Marichyasana D, Supta Kurmasana not yet bound) still counts as full once given. The same applies to Intermediate → Advanced A.
- **Items are independent flags** (drop-backs and standing up are taught in either order). Items can be marked once a position is set. Viparita Chakrasana (tic-tacs) is already `optional`; flagging it `milestone: true` is a data-only change in `sequences.yaml` (Q8).
- **Celebrations** (`Celebration(kind, series, key)`), first time only: `NEW_ASANA` for a `GIVEN` whose rank is above every earlier `START`/`GIVEN` target (`Earlier.peak`); `SERIES_COMPLETE` when that target is a series' last stop; `SERIES_BEGINS` when it is the first stop of a series (UHP = Primary begins; Pasasana = Intermediate begins); `ITEM` for an `ITEM_GIVEN` never given before. A give that jumps several stops (marked late) carries `from` so the line reads "New asanas: Marichyasana D → Navasana". A give that is not above the peak (re-given after a change) gets the quiet `progression-back` line, no 🎉 (Q3). `START` and `CHANGED` never celebrate. A stale peak key is ignored.
- **My practice presets** (PR-03; ashtanga-expert): current series N with last stop X →
  - N = 1: `Primary → X`.
  - N ≥ 2: `("mine", N−1 full + N → X)`: **only the series just below**, never every lower series (Advanced A → X is "Intermediate + Advanced A → X", never "Primary + Intermediate + Advanced A").
  - The **split** preset `("mine", N → X)` (the current series alone, e.g. Intermediate with Primary on Fridays): for Intermediate only once the position is at or past Pincha Mayurasana **or** an Intermediate-alone length is among the recent practices (Q6); for Advanced A and later always.
  - Standing only → Short. Presets equal to a static one are dropped. **Full Primary stays a static preset** (Friday Primary) for everyone. Half Primary + Intermediate is never a "mine" preset.
- **Suggestion:** `suggest_start` = the most-used non-Led length among the recent practices (`derive_presets` ranking) mapped by `from_length`; None if there is none.
- **Stale keys** (catalog edited): `rank` None → no next/after buttons, no presets from it, no celebrations; screens show the stored key's label if the asana still exists, else the raw key, and offer ✏️ Change. A slug rename stays a migration (ADR-0010) and now rewrites `progression` and `progression_event` too.
- Dates: `occurred_on` follows the logging rules (`check_loggable`: ≥ 2000-01-01, ≤ local today; `DateInFuture`, `DateTooEarly`).

## 3. Application and infrastructure
- Port **`ProgressionRepository`** (`application/ports/progression.py`, on `Storage.progression`):
  - `get(account_id) -> ProgressionView | None`: the state row plus `Earlier` (distinct `START`/`GIVEN` targets and given items, two `array_agg` subqueries) and the newest 20 events, **one statement**.
  - `apply(account_id, change, expected_event_id) -> AppliedChange | None`: one CTE statement: insert the event(s), upsert the state row **only `WHERE last_event_id IS NOT DISTINCT FROM :expected`** (compare-and-set), `RETURNING`. None = someone changed it first.
  - `undo(account_id, event_id) -> Progression | None`: one statement: delete the event **only if it is `last_event_id`**, restore the state from its `from_*` / item and the previous event id (undoing a `START` deletes the state row: unset again); None otherwise.
  - `dismiss_hint(account_id, target, at_event_id)`: one `UPDATE progression SET hint_dismissed = :target, hint_dismissed_event_id = :at WHERE …` ("Not new"). A dismissal counts only while `hint_dismissed_event_id = last_event_id`, so any change of the position brings the question back for later stops.
  - `recent_with_progression` (extends `PracticeRepository.recent`): a scalar subquery adds the state row, still one statement. `PracticeRepository.save` LEFT JOINs `progression` (like `check_in`), so `SavedPractice` += `progression`.
- Use cases (`application/progression.py`, `Principal`, own data): **`GetProgression`** (view + `suggested` when unset, then + `recent`), **`SetPractice(principal, target, on)`** (`START` if none, else `CHANGED`; equal = no-op), **`MarkNewAsana(principal, target, on)`** (raises `NotForward`, `ProgressionNotSet`), **`MarkItem(principal, item, given: bool, on)`**, **`UndoProgression(principal, event_id)`** (raises `NotLatest`), **`DismissNewAsanaHint(principal, target)`** (1 statement, idempotent). Each write = get (1) + domain + apply (1); a lost compare-and-set raises `ProgressionChanged`. `ChangeResult(progression, event, celebrations)`. `SavePractice` returns `past` (§5) from `past_last` with no extra read; `GetPracticePresets` adds `my_presets`.
- **Policy:** `can_view_progression(viewer, student)` = owner (named now for ST-06). `marked_by` = the actor (the owner now); Phase 3 adds `can_mark_progression(actor, student)` for linked teachers, never more.
- **Not sensitive, not sealed** (ADR-0016 not needed): the 05 matrix already shows practice length/series to teachers, and no reason is ever stored. ST-06 plan (decided then, Q13): teachers see the current position and `GIVEN` events, not `CHANGED`/undo (a step back can hint injury or pregnancy). ST-09 exports state + events; account delete cascades.

## 4. API (initData auth; additive; regenerate the client with `gen:api`)
| Method, path | Request → Response |
|---|---|
| `GET /api/v1/me/progression` | → `ProgressionOut {set: bool, position: {series: slug \| null, last: key \| null}, by_series: [{slug, last: key \| null}], items: [key], next: {series, last} \| null, suggested: Length \| null, events: [EventOut], last_event_id: int \| null}`; `EventOut {id, kind, occurred_on, from, to, item, marked_by_self: bool}` newest first, ≤ 20 |
| `POST /api/v1/me/progression/events` | `{kind: "set" \| "given" \| "item_given" \| "item_removed", series?, last?, item?, occurred_on?: date (default local today), expected_event_id: int \| null}` → 201 `ChangeOut {progression: ProgressionOut, event: EventOut \| null, celebrations: [CelebrationOut]}` (`event` null = no-op); 409 `progression_changed`; 422 `invalid_progression` (not a stop / not forward / unknown item / not set yet), `date_in_future`, `date_too_early` |
| `DELETE /api/v1/me/progression/events/{id}` | → 200 `ProgressionOut`; 409 `not_latest` |
| `POST /api/v1/me/progression/hint-dismissals` | `{series, last}` → 204 ("Not new"; idempotent) |
| `PUT /api/v1/me/days/{date}/practice` | `PracticeOut` += `new_asana_hint: {series, last} \| null` (only when this request changed the length, the context is Mysore or 1:1, and that target isn't dismissed) |
| `GET …/practice-presets` · `GET /api/v1/catalog` | `Preset.kind` += `"mine"` · `CatalogOut` += `milestone_items: [StopOut]` (covered by the seed ETag) |

`CelebrationOut {kind: new_asana \| series_complete \| series_begins \| item, series, key}`; the Mini App renders it with Fluent. `ErrorCode` += the three codes. A retried POST hits 409 and refetches (a lost reply can miss the card; accepted).

## 5. Bot (prefix **`g1:`**, stateless, ≤ 64 bytes; answer first, edit in place)
| Data | Meaning |
|---|---|
| `g1:o` | open G |
| `g1:g:2:kapotasana-b` (+ `:20261027` from P) | new asana given (forward) → G with the celebration (or P of that day, `occurred_on` = that day) |
| `g1:s:2:laghu-vajrasana` · `g1:s:0:` | set/change the position · standing only → G with `progression-saved` |
| `g1:i:drop-backs:1` / `…:0` | item given / removed |
| `g1:a:g` / `g1:a:s` · `g1:p:g:2:1` | series picker · stop grid (mode give/set, series, page; reuses the p1 grid renderer) |
| `g1:u:1234` | undo event 1234 → G with `progression-undone` |
| `g1:n:2:kapotasana-b:20261027` | "Not new": store the dismissal → P of that day without the question |
- **Entry:** command **`/asanas`** (menu "My asanas" / «Мои асаны»; `/help` line; owner reruns `set_webhook.py` ☁️), `[🧘 My asanas]` on L, and the §5 question on P.
- **G unset:** `progression-unset`, `[From your log: Primary → Navasana]` (when suggested), `[Choose…]`, `[Sun salutations and standing]`. A tap = `START`, **no celebration**.
- **G set:** `progression-current` (one length line, as the practice summary), `progression-items`; `[🎉 New asana: Supta Vajrasana]` (`next`; hidden when none or stale), `[🎉 Another new asana…]` (later stops only), `[🎉 Drop-backs]` / `[🎉 Standing up]` for items not given, `[✏️ Change]` (series picker → all stops + "Not in my practice now" for higher series, plus item toggles), `[Open the app]`. After a give: the celebration line on top + `[↩︎ Undo]`. A stale keyboard (target no longer forward) → G with `progression-already`.
- **Detection on P** (Q4, Q5): only on the reply to a length tap (`p1:l` and recent/mine presets) when `past` is set, the context is **Mysore or 1:1** (not self-practice: people try the next asana at home before it is given; not Led: the teacher counts everyone through), and this (position, target) wasn't dismissed: `progression-ask-new` + `[🎉 Yes, new]` (`g1:g:…:<date>`) `[Not new]` (`g1:n:…:<date>`, 1 UPDATE, then P without the question). Not asked again for that target until the position changes. With no progression set, nothing is asked. Opening P later never asks.
- **L:** "🧘 My practice" presets first (`preset-mine`), then up to `3 − len(mine)` recent ones (deduped), then `[🎯 Other…]`.
- **Round trips:** G open = middleware + 1 (+ 1 for the suggestion when unset); give/set/item = + 2; undo and "Not new" = + 1 (then P's usual read); L and P = **unchanged** (subquery / join). Failures: DB outage → `error-temporary`; malformed `g1:` ignored.

## 6. Mini App
- **Home card** "🧘 My asanas" (the current line or a quiet `progression-set-link`) → lazy screen `progression/Progression.tsx`: the current practice per series, the `next` button, "Another new asana…" (`<select>` of later stops), item chips, ✏️ Change (two native selects, as PracticeDetails "Other…"), an optional date (default the server's `today`), and a **short timeline** (newest 20, dates only; Undo on the newest entry). Unset: the suggestion button + Choose.
- **Celebration card:** inline at the top of the screen, `role="status"`, haptic `notificationOccurred("success")`, a soft scale-in that respects `prefers-reduced-motion`, dismissed by tap. No confetti library.
- **PracticeDetails:** when the PUT returns `new_asana_hint`, a one-line banner with Yes / Not new; Yes POSTs `given` with `occurred_on` = the day, Not new POSTs the dismissal.
- Writes are **not optimistic** (the celebration must reflect the server); scope `"progression"`; 409 refetches. Unknown preset kinds render as length text. Budget ≈ +3 KB gzip lazy, +0.3 KB initial, no dependency.

## 7. i18n (new keys in `bot.ftl` and/or `app.ftl`; «ты»; ux-writer + ashtanga-expert polish; asana and series names come from the catalog)
- `progression-title` "🧘 My asanas" / «🧘 Мои асаны» · `progression-unset` "Where does your practice end now? Set it once, then mark it here when you get a new asana." / «Где сейчас заканчивается твоя практика? Отметь один раз, а потом отмечай здесь, когда появится новая асана.» (no teacher assumed)
- `progression-suggest` "From your log: { $length }" / «По журналу: { $length }» · `progression-choose` "Choose…" / «Выбрать…» · `progression-standing-only` "Sun salutations and standing" / «Приветствия солнцу и стоячие асаны»
- `progression-current` "Your practice: { $length }" / «Твоя практика: { $length }» · `progression-items` "Backbends: { $items }" / «Прогибы: { $items }»
- `progression-new` "🎉 New asana: { $asana }" / «🎉 Новая асана: { $asana }» · `progression-new-other` "🎉 Another new asana…" / «🎉 Другая новая асана…» · `progression-item-new` "🎉 { $item }"
- `progression-change` "✏️ Change" / «✏️ Изменить» · `progression-change-explain` "Pick where your practice ends now. Your history stays." / «Выбери, где сейчас заканчивается практика. История сохранится.» · `progression-not-in-practice` "Not in my practice now" / «Сейчас не в практике»
- `progression-saved` "Saved: your practice ends at { $asana }." / «Сохранено: практика заканчивается на { $asana }.» · `progression-back` "{ $asana } is in your practice." / «{ $asana } — в твоей практике.» · `progression-already` "That's already in your practice." / «Это уже есть в твоей практике.»
- `progression-undo` "↩︎ Undo" / «↩︎ Отменить» · `progression-undone` "Undone." / «Отменено.»
- `progression-ask-new` "{ $asana } goes beyond your last asana. New asana? 🎉" / «{ $asana } — дальше твоей последней асаны. Новая асана? 🎉» · `progression-ask-yes` "🎉 Yes, new" / «🎉 Да, новая» · `progression-ask-no` "Not new" / «Не новая»
- `celebrate-new-asana` "🎉 New asana: { $asana }. Enjoy it!" / «🎉 Новая асана: { $asana }. Пусть приносит радость!» · `celebrate-new-asanas` (a multi-stop jump) "🎉 New asanas: { $from } → { $asana }" / «🎉 Новые асаны: { $from } → { $asana }» · `celebrate-series-complete` "🎉 Full { $series }{ $traditional -> [none] {""} *[other] : { $traditional } }." / «🎉 { $series } целиком{ $traditional -> [none] {""} *[other] : { $traditional } }.» (the traditional name only for Primary "Yoga Chikitsa" and Intermediate "Nadi Shodhana"; Advanced A–D share "Sthira Bhaga", so it is dropped there; the same rule for `celebrate-series-begins`) · `celebrate-series-begins` "🎉 { $series } begins: { $traditional }." / «🎉 Начинается { $series }: { $traditional }.» · `celebrate-item` "🎉 { $item }: a lovely step." / «🎉 { $item }: прекрасный шаг.»
- `progression-event` (selector `$kind`: start / given / changed / item_given / item_removed) · `preset-mine` "🧘 My practice: { $length }" / «🧘 Моя практика: { $length }» · `command-asanas`, `help-asanas` · app: `progression-set-link`, `progression-date`, `progression-history`, `progression-save-failed`, `progression-changed`.
- Item labels come from the catalog (`drop-backs`, `standing-up` asana names). Reused: `log-back`, `error-temporary`, `log-date-future`, `series-*`.
- **Words to avoid in `progression-*`/`celebrate-*`** (test grep; "series unlocked" stays banned: GM-01's wording is internal only): unlock, level, achieve, earn, finally, behind, lost, regress, back to, demote, only, again, streak, rank, goal, should, faster; RU уровень, достижен, разблок, наконец, откат, потер, отстал, только, опять, цель, надо, должен. No gendered past tense in RU.

## 8. Migration `0014_progression` (expand-only, down_revision `0013`)
- `progression(account_id uuid PK references account on delete cascade, series text null, last_key text null, items text[] not null default '{}', last_event_id bigint null, hint_dismissed_series text null, hint_dismissed_key text null, hint_dismissed_event_id bigint null, updated_at timestamptz not null default now())`. CHECKs: `(series IS NULL) = (last_key IS NULL)`, `cardinality(items) <= 8`, the three `hint_dismissed_*` all NULL or all set (one dismissal at a time: a new "Not new" replaces it).
- `progression_event(id bigint generated always as identity PK, account_id uuid not null references account on delete cascade, kind text not null, from_series text, from_key text, to_series text, to_key text, item text, occurred_on date not null, marked_by uuid null references account on delete set null, created_at timestamptz not null default now())`, index `(account_id, id DESC)`. CHECKs: kind in the five values; item kinds have `item` and no from/to, other kinds no `item`; `(from_series IS NULL) = (from_key IS NULL)`, same for `to_*`; `occurred_on >= '2000-01-01'`.
- Keys are text without FKs (ADR-0017). No backfill (no position is inferred; the suggestion covers it). The old revision ignores both tables; downgrade drops them; no owner step besides `set_webhook.py` for `/asanas`.

## 9. Cross-cutting checks
- **Time zones:** `occurred_on` is a local date (the caller's local today by default, provisional zone allowed; from P, the practice day); `created_at` UTC is audit and ordering only. No times are shown, so no zone label. Tests: Kiritimati vs Honolulu on one instant; a give from P for yesterday.
- **Privacy:** not sensitive, plain, owner-only by `can_view_progression`; no reason field; never derived from diary or check-in text; nothing in pushes or logs (account uuid only). Never reveals 🌸 (no link to day status).
- **i18n:** all copy in `.ftl` with en/ru parity; asana and series names from the catalog (`StopPoint.label`, RU series lowercase mid-sentence as in PR-02); no plurals needed.
- **Responsiveness:** §5 round trips; each statement is a PK lookup or a small per-account aggregate (≤ hundreds of events). Celebrations computed in memory from the read already made. Callback answered first; edits in place; no new message, no outbound call, no dependency.

## 10. Test plan
- **Domain:** `rank`/`next` across series (Setu Bandhasana → Pasasana; standing only → UHP; Advanced B end → None as C is pending); `check_given` rejects equal/earlier and non-stops (`utthita-trikonasana-b`, `kapotasana-a`); `from_length` (full, → X, second half + Intermediate → Primary full implied); `my_presets`: Primary → X gives one; Intermediate → Bakasana gives only "Primary + Intermediate → Bakasana"; Intermediate → Pincha Mayurasana (or a recent Intermediate-alone length) adds "Intermediate → X"; **Advanced A → Galavasana gives "Intermediate + Advanced A → Galavasana" and "Advanced A → Galavasana", never a preset with Primary**; full Advanced A → "Intermediate + full Advanced A"; Full Primary stays static and a "mine" equal to it is dropped; half Primary + Intermediate never appears as mine; `past_last` (beyond / equal / earlier / Led / self / no context / Mysore and 1:1 asked / dismissed for this position / asked again after the position changes / unset / stale); multi-stop give carries `from`; `celebrations` (first give, series complete, series begins combined with new asana, re-give below peak → none, `START`/`CHANGED` → none, item first time only, stale peak ignored); `suggest_start` skips Led and stale lengths.
- **Use case (fakes, fixed clock):** set → START then CHANGED; equal set = no event; give when unset → `ProgressionNotSet`; lost compare-and-set → `ProgressionChanged`, no celebration; undo latest only, then a real give celebrates again; future/too-early `occurred_on`; `SavePractice` hint only when the length changed; presets include mine.
- **DB (real Postgres):** `get` = one statement with Earlier + events; `apply` compare-and-set under two concurrent gives (one wins, one event); `undo` restores position, items and the previous event id in one statement and refuses a non-latest id; `dismiss_hint` is one UPDATE and stops counting after any change; practice save join and `recent` subquery stay one statement; CHECKs; cascades and `marked_by` set null; 0014 up → down → up; `alembic check`.
- **API:** 401; GET unset/set; POST set/given/items 201 with celebrations; 409 `progression_changed` and `not_latest`; 422 cases; practice PUT `new_asana_hint`; presets `mine`; catalog `milestone_items`; OpenAPI lists the codes; the TS client builds.
- **Bot (fake use cases):** G unset with/without suggestion, START shows no 🎉; G set buttons (next hidden at the end and on stale keys); a give edits in place with the celebration + Undo; a stale give → `progression-already`; the P question only after a length tap past the last asana, never for Led, never on `p1:o`; never for self-practice; Not new stores the dismissal and returns P without it, and the next length tap past the same target doesn't ask; Yes from P → P with the celebration, `occurred_on` = that day; L shows mine presets first and caps recents; every `g1:` round-trips, ≤ 64 bytes; malformed ignored; avoid-word grep over the new keys.
- **Mini App (Vitest):** card states; next/other/items/change/undo calls with `expected_event_id`; celebration card with haptic and reduced motion; 409 refetch; banner in PracticeDetails; an old payload without the new fields renders; bundle check.
- **Architecture:** import-linter (domain pure, aiogram only in `bots/telegram`).

## 11. Open questions (recommended answer first)
Status: ashtanga-expert review applied 2026-10-27 (presets, the question's contexts and dismissal, the "full" reasoning, copy); owner: all as recommended (2026-10-27).
1. **GM-01 split?** Yes: asana and series milestones here; practice counts 100/365/1000 as **GM-01 part 2** (day-write path, non-monotonic counts → a seen ledger, backfill rule, NT-01 toggle). Recommended.
2. **One current position, earlier series full** (not per-series rows)? Yes (ADR-0026; expert: Pasasana comes only after full Primary, incomplete binds still count as full). Recommended.
3. **Re-given after a change** (injury, teacher took it back): no 🎉, the quiet `progression-back` line. Recommended.
4. **Ask "New asana? 🎉" after a length past the last asana**: one tap, never automatic, only on that reply screen, never when unset; "Not new" is stored per (position, target) until the position changes. Recommended.
5. **Which contexts get the question?** Mysore and 1:1 only, not self-practice (people try the next asana at home before it is given) and not Led. Recommended.
6. **Split preset trigger for Intermediate** ("Intermediate → X" alone): at or past Pincha Mayurasana, or a recent Intermediate-alone length? Both (either one shows it). Recommended.
7. **Presets:** "🧘 My practice" = the series just below (full) + current → last; the split preset as in Q6 (always from Advanced A); Full Primary stays static; recents fill up to 3; 🔁 unchanged. Recommended.
8. **Viparita Chakrasana (tic-tacs) `milestone: true`**, a data-only change? Yes. Catching heels, binds and jump-backs stay out. Recommended.
9. **Drop-backs and standing up as independent flags**, celebrated the first time. Recommended.
10. **Undo = delete the latest event** (any kind, no time limit); real changes go through ✏️ Change and stay in the history. Recommended.
11. **Bot entry `/asanas` "My asanas"** plus a button on L. Recommended.
12. **No sticker or separate animated 🎉 message** in the bot now; the edited line only. Recommended; revisit with beta feedback.
13. **ST-06 visibility:** teachers see the current position and given events, never changes back or undos. Recommended; confirm at ST-06.
14. **No "show celebrations" setting and no NT-01 toggle now** (celebrations only answer your own tap). Recommended.
15. **Backdating:** the bot uses today (or the P day); the Mini App offers an optional date. Recommended.

## 12. Implementation notes (2026-10-27, after the code and domain reviews)
- **"Held before" includes ✏️ Change targets** (`Earlier.targets` = every START/GIVEN/CHANGED target): after a mis-tapped start fixed by Change, or a change back after injury, stepping back to an asana held before is quiet, not a first time. A mis-tapped *forward* Change shows ↩︎ Undo like a give; undone, it leaves no trace.
- **A jump across a series boundary** carries `first` as a position (`{series, last}`), so "New asanas: Bhujapidasana → Krounchasana" names the Primary stop.
- **"Not new"** is stamped with the server's current `last_event_id` (one UPDATE); the callback carries no event id.
- **`progression_event.id` is `GENERATED BY DEFAULT AS IDENTITY`**: apply takes `nextval(pg_get_serial_sequence(…))` first, so the state row and its event share the id in one statement.
- **API extras:** `ProgressionOut.length`, `suggested_length`, `later`; `CatalogOut.series[].traditional` (Primary and Intermediate only). The client never re-derives domain rules.
- **Mini App Home** has a "🧘 My asanas" row button (no card, no extra request on Home load).
- **Standing only → "Another new asana…"** lists Primary only; RU pickers say «Вторая серия», «Последняя асана, вторая серия:».
