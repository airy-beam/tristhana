# ST-04: progression timeline (asanas over time, when each series begins)

- Status: **accepted** (owner, 2026-11-09: Q215–Q226 all as recommended; Q227, Q228 decided by the owner; ashtanga-expert review applied) · Size S, Phase 3
- Requirements: **ST-04** ("Progression timeline: asanas acquired over time, when the next series begins"; "series unlocked" is banned wording, PR-08 §7). Fixes **Q159** (PR-08 Phase 3 residual (a)). Touches **PR-08** (events, celebrations), **ST-07** (the existing `asana` share subject, unchanged), **ST-06** (teacher views: out of scope).
- Related: ADR-0020 (rules server-side, client only draws), ADR-0026 (one position + append-only events), ADR-0037 (teacher marks, undo until moved on), ADR-0040. **No new ADR**: the timeline is a read-time projection of the ADR-0026 history; nothing is stored.

## 1. Scope
**In:**
- A read-only **Timeline** screen in the Mini App (lazy chunk), opened from My asanas: every progression event of the account, newest first, grouped under year headings, each with its date, asana(s), series and who marked it, plus **"{series} begins" / "Full {series}" markers** where they happened for the first time.
- One endpoint `GET /api/v1/me/progression/timeline`; one use case `GetTimeline`; one pure domain function `timeline(...)`.
- **Q159 fix:** `ProgressionRepository.get` also reads the event that set the current position (any age), so "Marked by …" and its Undo no longer drop off after 20 newer item events (bot G and Mini App `marked`).

**Out:** charts, counts ("N new asanas this year"), pace, comparisons, gaps ("time since…"); undo or edits from the timeline (they stay in My asanas → History); a bot timeline screen or command; teacher/shala timelines (ST-06 Q13 already limits teachers to the position and given events: not built here); new share-card kinds (ST-07 stays as is); export changes (ST-09 already exports all events); any inference of dates before the person's first `start`.

**Tone:** a record of gifts received, not a scoreboard. No 🎉 on corrections, removals or asanas given again; no words from the PR-08 §7 avoid list.

## 2. User flows and copy
**Mini App.** My asanas → under the History card, a link `timeline-open` → `Timeline.tsx` (Telegram BackButton returns to My asanas; fallback link `stats-back`). The History card (newest 20, Undo) is unchanged (Q219).

Entry rendering (newest first, year heading = the number, date = `Intl` short date with `timeZone: "UTC"` on the `occurred_on` date string, as History does):
| Event | Line | Extra |
|---|---|---|
| `start` | `timeline-start` "Record begins: { $length }" / «Начало записи: { $length }». `$length` comes from the **same renderer as `progression-current`** (the position as a practice via `lengthText`, or `progression-standing-only`). The row describes where the **record** begins, not when the practice began | always the oldest entry |
| `given`, first time (has `new_asana`) | reuse `progression-event` [given] "🎉 { $asana }"; a multi-stop jump within one series: `timeline-given-range` "🎉 { $from } → { $asana }" / «🎉 { $from } → { $asana }»; a jump **across a series boundary** names both series, like `students-give-ask-across`: `timeline-given-across` "🎉 { $from } ({ $from_series }) → { $asana } ({ $series })" / «🎉 { $from } ({ $from_series } серия) → { $asana } ({ $series } серия)» | series label (`series-name`, omitted for `-across`), `progression-event-by` for a teacher, ST-07 Share button (subject `{kind: "asana", event_id}`) |
| `given`, held before (no `new_asana`) | reuse `progression-back` "{ $asana } is in your practice." / «{ $asana } — в твоей практике.» (no 🎉) | series label, by, Share (Q213, Q228) |
| `series_complete` / `series_begins` (from the same given) | reuse `celebrate-series-complete` / `celebrate-series-begins` as highlighted marker rows **above** the given row, **in practice order**: Full Primary first, then Intermediate begins (the order of the stops crossed, not the order of `celebrations()`) | |
| `changed` | reuse `progression-event` [changed] "Changed to { $asana }", muted style | |
| `item_given` / `item_removed` | reuse `progression-event` (🎉 only the first time an item is given: `item` celebration). **`item_removed` wording changes (Q227)** to "{ $item }: not in practice now" / «{ $item }: сейчас не в практике» | |

- **Shared key:** `progression-event` [item_removed] is also used by My asanas → History (Mini App only; the bot doesn't show events), so History reads the new wording too. Its tests are updated (§8).
- **A crossing give shows 🎉 three times** (Full Primary, Intermediate begins, the asana row). The final copy (for example, dropping the emoji on the marker rows in the timeline) is left to the ux-writer pass.
- Undone events are deleted (ADR-0026/0037), so they simply aren't there. Stale keys show the raw key (`stopLabel` fallback) and never a marker.
- **Empty states:** unset → `timeline-empty-unset` "Set where your practice ends in My asanas, and your timeline starts from there." / «Укажи в «Мои асаны», где сейчас заканчивается практика, и отсюда начнётся хронология.» + a link back. Only a `start` → the start row + `timeline-empty-start` "New asanas will appear here with their dates." / «Новые асаны появятся здесь с датами.»
- `truncated` → `timeline-truncated` "Showing the newest { $count } entries." / «Показаны последние записи: { $count }.» (number via `NUMBER`, no plural form needed).
- New keys (app.ftl, en + ru; ux-writer + ashtanga-expert pass): `timeline-open` "🗓 Timeline" / «🗓 Хронология», `timeline-title` "🗓 My asanas over time" / «🗓 Мои асаны: хронология», `timeline-start`, `timeline-given-range`, `timeline-given-across`, `timeline-empty-unset`, `timeline-empty-start`, `timeline-truncated`. Changed: `progression-event` [item_removed] (Q227). Reused: `progression-back`, `progression-event`, `progression-event-by`, `progression-by-teacher`, `celebrate-series-*`, `series-name`. No counts → no RU plural selectors.

**Bot:** no new screen, command or button (Q216). G changes only through the Q159 fix: "Marked by …" and `[↩︎ Undo the mark]` appear whenever the current position is a teacher's mark, however many item events followed.

## 3. Domain (pure, `domain/progression.py`)
```python
TIMELINE_LIMIT = 1000
@dataclass(frozen=True, slots=True)
class TimelineEntry: event: ProgressionEvent; celebrations: tuple[Celebration, ...]
def timeline(track: Track, oldest_first: Sequence[ProgressionEvent]) -> tuple[TimelineEntry, ...]
    # replays the history: before each event, `Earlier` = every START/GIVEN/CHANGED target and
    # every item given so far; entry.celebrations = celebrations(track, earlier, change_of(event)).
    # Returns newest first.
def undoable(events, position_event) -> frozenset[int]          # Q159, below
def teacher_mark(position_event) -> ProgressionEvent | None     # Q159, below
```
- **Reuses `celebrations` unchanged**, so "first time", ranges (`first`), "begins" (first stop of a series) and "full" (last stop) mean exactly what the 🎉 meant at write time; START/CHANGED never celebrate; a give at or below the peak is quiet (PR-08 Q3). This also matches ST-07's per-event asana card closely enough (Q213: a card for a re-given asana is allowed).
- No dates are invented: stops below the `start` position have no entry.
- **Q159:** `undoable(events, position_event)` = {newest} ∪ {`position_event.id` if it is a teacher's `given`}; `teacher_mark(position_event)` = it if a teacher's `given`. (By definition no position event is newer than `position_event`, so this equals the ADR-0037 rule without the 20-event window.)

## 4. Application and ports
- `ProgressionView` += `position_event: ProgressionEvent | None` (the newest START/GIVEN/CHANGED, any age). `_after` sets it to the new event for position changes, keeps it for item changes.
- Port `ProgressionRepository.timeline(account_id) -> tuple[tuple[ProgressionEvent, ...], bool]`: the newest `TIMELINE_LIMIT` events oldest first with `by`/`by_name` (the existing `marker_link` join: a name only while linked), plus `truncated`. **One statement.**
- `GetTimeline(progression, track).execute(principal) -> Timeline(entries, truncated, set: bool)`: own data only (`can_view_progression` = owner); one statement, then `timeline(...)` in memory. Bot and API callers of `GetProgression`/`UndoProgression` unchanged in signature.

## 5. Infrastructure (`infrastructure/db/progression.py`)
- `get`: one more scalar subquery in `_view_columns`: `json_build_object(...)` of `SELECT … FROM progression_event WHERE account_id = :me AND kind IN ('start','given','changed') ORDER BY id DESC LIMIT 1`, with the same marker join. Uses the index `(account_id, id DESC)`. Still one statement; `for_teacher` inherits it.
- `timeline`: `json_agg` over `(SELECT … ORDER BY id DESC LIMIT 1001)` re-ordered ascending; 1001 rows → `truncated`, drop the oldest.
- **No migration.** Kinds, `marked_by`, the index and grants exist.

## 6. API (initData; additive; `gen:api`)
| Method, path | Response | Policy |
|---|---|---|
| `GET /api/v1/me/progression/timeline` | `TimelineOut {set: bool, truncated: bool, entries: [TimelineEntryOut {id, kind, occurred_on: date, from: PositionOut \| null, to: PositionOut \| null, item: str \| null, by: "self" \| "teacher", by_name: str \| null, celebrations: [CelebrationOut]}]}` newest first | own (`can_view_progression`) |
| `GET /api/v1/me/progression` | unchanged shape; `events[].undoable` and `marked` now correct beyond 20 events | own |

401/503 as the router. No new `ErrorCode`. Client: `useTimeline()` with key `[...PROGRESSION_KEY, "timeline"]`, so every progression mutation's existing invalidation refreshes it.

## 7. Cross-cutting checks
- **Time zones:** `occurred_on` is already a local practice-day `date` (the student's zone for teacher marks); shown as a date only, formatted in UTC so it never shifts; no times → no zone label. `created_at` unused. Tests: Vitest under `TZ=UTC`, `TZ=Pacific/Kiritimati` and `TZ=America/Honolulu` render the same day.
- **Privacy:** owner-only; plain data (ADR-0026, not sealed); teacher names only while linked, else `progression-by-teacher`; no day status, 🌸 or notes involved; nothing logged beyond the account uuid. Teacher views out of scope.
- **i18n:** 8 new keys and one changed variant, en/ru parity test; asana names from the catalog (Latin / Cyrillic), series via `series-name`; RU «ты», gender-neutral; the avoid-word grep (PR-08 §7, incl. "unlock" / «разблок») is extended to `timeline-*` and gains **"acquire" / «получил»** (the requirement's own word stays internal).
- **Responsiveness:** one request, one indexed statement (realistic accounts: < 300 events, ≈ 20–40 KB JSON worst case), O(n) replay. Target < 300 ms p50 warm; measure with a seeded account of 300 events (expect ~15 ms). `get` gains one LIMIT 1 index scan.
- **Bundle:** `Timeline.tsx` is `React.lazy` (≈ 2 KB gzip, no dependency; ShareButton is already lazy). Initial JS grows only by the ftl keys and the lazy stub, ≈ +0.3 KB (145.0 → ~145.3 / 150). Run `check:bundle`; RU at 320 px.

## 8. Test plan
- **Domain:** `timeline` on fixed histories: start → given ×3 (🎉 each); a jump carrying `first`; (a) position Setu Bandhasana, give Pasasana → `new_asana` + `series_begins(intermediate)` **only** (Primary was already full); (b) position Urdhva Mukha Paschimottanasana (the stop before Setu Bandhasana) or earlier, jump to Pasasana with `first` = Setu Bandhasana → also `series_complete(primary)`; change back then re-give → quiet, no markers; item given twice (after a removal) → 🎉 once; stale key → no celebrations; empty input → (); newest-first output. `undoable`/`teacher_mark` with a teacher `given` followed by 25 item events → undoable; followed by a change → not.
- **Application (fakes):** `GetTimeline` owner only, one repository call, `set` false when unset; `_after` keeps/sets `position_event`.
- **DB (real Postgres):** `timeline` = one statement, ascending order, `by_name` gone after unlink and NULL after a teacher's deletion, `truncated` at 1001; `get` returns `position_event` beyond 20 events in one statement; `for_teacher` still one statement; app role read; `alembic check` clean (no migration).
- **API:** 401; unset / start-only / full payloads; celebrations per entry; no `undoable` field; OpenAPI + TS client build.
- **Bot (fake use cases, through the webhook):** G after a teacher mark + 25 item events shows `progression-marked-by` and `[↩︎ Undo the mark]`; the Undo works; no new callbacks.
- **Mini App (Vitest, also `TZ=UTC` and the two zones above):** link from My asanas; year headings; marker rows above the given row in practice order (Full Primary, then Intermediate begins); a cross-series range names both series in EN and RU; quiet re-give reads `progression-back` without 🎉 and still offers Share; the start row matches `progression-current`'s length text; `item_removed` reads "not in practice now" in both the timeline and History (update the existing History tests); teacher "· Anna" / "· a teacher"; Share only on given entries; both empty states; truncated line; older payload without fields renders; invalidation after a give refreshes it; `check:bundle`.
- **Architecture:** import-linter unchanged (domain pure; aiogram only in `bots/telegram`).

## 9. Decisions (owner, 2026-11-09: Q215–Q226 all as recommended; Q227, Q228 owner decisions from the ashtanga-expert review)
215. **Surface:** ✅ a lazy Timeline screen opened from My asanas only; no entry on 📊 My practice (it is about days, not asanas).
216. **Bot:** ✅ nothing new beyond the Q159 fix; no `/timeline`, no button (G's "Open the app" covers it).
217. **Corrections and item removals:** ✅ visible in the timeline, muted and neutral (the person's own honest record).
218. **Read-only:** ✅ no Undo on the timeline; Undo stays in My asanas → History.
219. **History card:** ✅ kept (newest 20 with Undo); the Timeline link goes under it.
220. **No pagination:** ✅ the whole history in one response, capped at 1,000 events with a quiet "newest N" line.
221. **No charts or counts:** ✅ no "N new asanas this year", no cumulative chart, no "since your last"; revisit with beta feedback.
222. **Order:** ✅ newest first with year headings (as History).
223. **An asana given again** after a correction: ✅ no 🎉, no markers; it reads `progression-back` (PR-08 Q3).
224. **Teacher timelines:** ✅ out of scope; ST-06 keeps the position + given-events rule for later.
225. **Share:** ✅ on every given entry, reusing ST-07's `asana` subject (no new card kind).
226. **Q159:** ✅ fixed with a "position event" subquery in `get` (any age); accepted residual: the bot's "moved on" line after a failed Undo from an old student message still needs the event among the newest 20 (the Undo itself works).
227. **`item_removed` wording** (owner decision A, resolved): "{ $item }: not in practice now" / «{ $item }: сейчас не в практике», replacing "removed" / «убрано». The key is shared, so My asanas → History changes too; tests updated in both places.
228. **Share on a quiet re-given entry** (owner decision B, resolved): keeps the Q213 behaviour (a card means "given on that date"); no change.

**Open, for the ux-writer (not blocking):** the triple 🎉 on a give that crosses a series boundary (§2); RU `timeline-*` polish.
