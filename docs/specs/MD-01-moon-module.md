# MD-01 (Phase 0 part): moon module, a 1:1 port of generator.py with golden tests

- Status: confirmed by the owner (answers in §8) · Date: 2026-10-18
- Requirements: **MD-01** (compute moon days per location with the existing algorithm; pre-compute and store), **NF-08** (golden fixtures)
- Related: ADR-0003 (layering), ADR-0005 (time model), ADR-0006 (reuse the algorithm), notes `07 Moon Days`, `06 Time Zones`

## 1. Goal and scope
Port `moon_days/generator/generator.py` into `tristhana.moon` as a deterministic function. It must give the same `(date, kind)` list as the original for every verified city. Golden fixtures prove this.

**In this task (Phase 0):**
- Value types in `domain/moon.py`
- `tristhana.moon` package with bundled ephemeris files
- A one-off fixture dump script in `tools/moon/`
- Golden and unit tests
- Import-linter contracts

**Later (Phase 1, MD-01/MD-03):** DB tables, the pre-compute job on `/internal/tick`, the application port and use cases, the API, bot/Mini App display, and reminders.
**Out of scope:** official SYC import (MD-05), FYI on differences (MD-04), calendar inheritance (MD-02), Ekadashi or any other tithi.

## 2. User flows and copy
None in this task, because it has no user-facing surface. Enum values stay ASCII (`kshaya`). Display is "Full moon (Purnima)" / "New moon (Amavasya)", with IAST pūrṇimā / amāvāsyā / kṣaya as metadata and RU «Пурнима», «Амавасья». Users never need the word "kshaya": `moon-kshaya-note` is one gentle line ("the tithi starts and ends between two sunrises; observed on this day"), not a label. Keys reserved for Phase 1 (`en`/`ru` `.ftl`): `moon-purnima`, `moon-amavasya`, `moon-kshaya-note`, `moon-location-unsupported`.

## 3. Domain, module API, algorithm
**Domain types (`tristhana/domain/moon.py`, pure):**
- `MoonDayKind(StrEnum)` has `PURNIMA`, `AMAVASYA`, `KSHAYA_PURNIMA`, `KSHAYA_AMAVASYA`, with the properties `phase` (purnima/amavasya) and `is_kshaya`.
- `MoonLocation(lat: float, lon: float, tz: str)` is a frozen dataclass. It validates the ranges and checks that `tz` is a valid IANA name via `zoneinfo`.
- `MoonDay(date: date, kind: MoonDayKind)` is a frozen dataclass. **It has no index** (see Q3).

**Module (`tristhana/moon/`):**
```python
def compute_moon_days(location: MoonLocation, start: date, end: date) -> list[MoonDay]
    # inclusive range; raises MoonRangeError outside ephemeris coverage, NoSunriseError (polar)
```
- `rules.py` holds the pure helpers, which are testable without swisseph:
  - `tithi(moon_lon, sun_lon)`
  - `classify(t0, t1) -> MoonDayKind | None`
  - `dedup(candidates)`, where an event that is less than 2 days after the last **accepted** event is dropped
- `_ephemeris.py` is the only file that imports `swisseph`. It imports it **lazily** inside functions and sets the ephemeris path once to the bundled `ephe/` directory (`Path(__file__)`; the package is installed unzipped). It also owns the lock that serializes swisseph access.

**Parity rules (copied exactly, not "improved"):**
- Tropical longitudes from `calc_ut` with default flags.
- Sunrise comes from `rise_trans(jd(local midnight → UTC), SUN, CALC_RISE, (lon, lat, 0), atpress=0, attemp=0)`.
- The sunrise is truncated to whole seconds before the tithi JD is computed.
- Tithi 15/30 at sunrise d gives the event on d. Otherwise, if a 15 or 30 is skipped between sunrise d and sunrise d+1, d is kshaya.
- When tithi 15/30 holds at two consecutive sunrises (a **vriddhi** tithi), dedup keeps the first day. That is the generator's behaviour, and we keep it. Dedup works across both phases, not per phase, as in the generator.
- `pytz` is replaced by `zoneinfo`. This is behaviour-neutral for the verified cities: the zone only picks which local midnight starts the sunrise search. In zones whose DST change happens at 00:00, pytz `is_dst=False` and zoneinfo `fold=0` can pick different offsets. That moves the search start, not which sunrise is found, and the generator-parity fixtures would catch any difference.

**Ephemeris files:**
- Bundle only `sepl_18.se1` and `semo_18.se1` (coverage 1800–2399, about 2 MB; confirm the sizes) under `tristhana/moon/ephe/`. The `_30` files are for years 3000+ and are not needed.
- No silent Moshier fallback: `_ephemeris` checks the returned flag for `FLG_SWIEPH` and raises if the files are missing.
- The supported request range is `1800-01-05..2399-12-30` (the scan starts 3 days earlier and reads one sunrise past the end; file coverage is 1800-01-01..2400-01-10).

**Per-year computation and the year boundary:**
- Internally we scan `[start − 3 d, end]`, run dedup over that span, and then filter to `[start, end]`.
- A tithi lasts at most about 26.8 h, so detections never chain for more than 2 consecutive days. A 3-day look-back therefore gives the same dedup state as one continuous run. The parity test also covers this (§7).
- Sunrise d+1 is reused as sunrise d of the next iteration. The values are identical, and this halves the `rise_trans` calls.

**Skipped local dates:** zones that jumped the date line (e.g. Pacific/Apia on 2011-12-30) have local dates that never existed. These are skipped as non-days, not treated as missing sunrises.

**Fixed-offset zones** (`Etc/GMT±N`) are rejected by `MoonLocation`; `UTC`/`Etc/UTC` are allowed.

**Polar latitudes (an added guard, not parity):** the generator silently uses `tret[0]`. We instead raise `NoSunriseError(date)` if `rise_trans` reports circumpolar or the found sunrise is not on local date d. No verified city is affected. The Phase 1 policy is in Q4.

**Performance:** per city-year, about 366 `rise_trans` and 732 `calc_ut` calls, roughly 0.1 s (to measure). This is offline pre-computation, never on a tap path.

**Thread-safety:** swisseph has process-global state, so callers run it serially. The Phase 1 job uses `asyncio.to_thread` plus a lock.

## 4. API endpoints
None in this task. Phase 1 sketch: `GET /api/v1/moon-days?from=&to=` resolves the caller's calendar through an application port `MoonCalendarRepository` (read side). An infrastructure adapter wraps `tristhana.moon` for the job.

## 5. DB migration outline (Phase 1, not this task)
- `moon_calendar(id, location_key, year, source computed|official, algo_version, computed_at)`
- `moon_day(calendar_id, date, kind)` with PK `(calendar_id, date)`

`algo_version` records the port version, the pyswisseph version and the tzdata version, so a recompute can be traced.

## 6. Cross-cutting checks
- **Time zones:** moon dates are **local dates of the location**, not of the user (06 Time Zones). Use the zone, never an offset. Pin `tzdata` for reproducibility. Example: Asia/Almaty became UTC+5 in 2024, which is harmless for us because sunrise is never near midnight.
- **Privacy:** the module never sees a user. It takes coordinates only. In Phase 1, key calendars by a city-level location (coordinates rounded to 0.01°, which shifts sunrise by seconds), never by a user's exact position.
- **i18n:** no strings in this task. Kinds become Fluent keys in Phase 1, and dates are formatted per locale.
- **Responsiveness:** zero per-tap cost. `swisseph` is lazy-imported, so neither the bot nor the API pays for it at cold start. The image grows by the wheel (a few MB) plus about 2 MB of ephemeris files.
- **Layering (new import-linter contracts):**
  - Add `tristhana.moon` to the **adapter layer** (top layer, next to `infrastructure`). It may import `tristhana.domain`. `domain` and `application` may not import it.
  - `swisseph` is forbidden everywhere except `tristhana.moon`.
  - `tristhana.moon` is forbidden from importing fastapi, starlette, aiogram, sqlalchemy, `tristhana.settings`, `tristhana.logs` and `tristhana.main`.

## 7. Test plan
**Fixtures (`backend/tests/fixtures/moon/`):**
- `generator/<city>.json`: the full `[{date, kind}]` list per city for 2025-01-01..2100-12-31. It is produced once by `tools/moon/dump_generator_fixtures.py <path-to-prior-art>`. That script imports the **original** generator read-only, overrides `START_DATE`/`END_DATE` (starting 2024-12-01) and dumps the result. Nothing is copied into the repo, and no secrets are read. A header records the pyswisseph and tzdata versions.
- `syc_2025.yaml`: the 24 SYC-posted Mysuru dates with their kinds.
- ~~Owner's 2025/2026 city calendars~~: dropped. The owner made them with generator.py, so the generator-parity fixtures already cover them (§8, Q2b).
- Fixture headers list the **vriddhi "watch" dates**, where SYC and the generator are most likely to disagree.

**Unit tests (`rules`):**
- tithi boundaries at 0°, 12°, 168°/180°, 348°/360°
- `classify` for: direct 15/30, a skip over 15, a skip over 30, a skip of 2+ tithis, the 30→1 wrap, and no event
- dedup:
  - a 2-day chain keeps the first day
  - events exactly 2 days apart are both kept
- `MoonLocation` validation, including a bad tz name

**Golden tests (`tristhana.moon`):**
- Parity with the generator for all 10 cities:
  - the default run covers 2025–2030 plus every 10th year
  - the full 2025–2100 run is marked `slow` (nightly or manual)
- Year-split parity: concatenating per-year results equals one continuous run (all cities, 2025–2035).
- SYC 2025 Mysuru dates match on **date + phase** (SYC never marks kshaya). The generator wins: any mismatch is listed in `syc_known_differences.yaml` with a reason, reviewed by the owner (Q2).
- Named cases:
  - Amavasya 19 Mar 2026 in Mysuru vs 18 Mar 2026 in Moscow, SPb, Kyiv and Minsk, and kshaya in Yekaterinburg
  - Amavasya 16 May 2026 is kshaya in Yekaterinburg, Novosibirsk, Astana and Almaty, and plain in Mysuru
- Errors:
  - a polar location (e.g. 78°N in December) raises `NoSunriseError`
  - a date outside coverage raises `MoonRangeError`
  - a missing ephemeris file raises instead of falling back to Moshier

**Use case, API contract and bot handler tests:** not applicable in this task (Phase 1).
**Gates:** `lint-imports` with the new contracts, pyright strict (add a local stub or `py.typed` shim for swisseph), and ruff.

## 8. Open questions for the owner
1. **Swiss Ephemeris licence (AGPL-3.0 or paid professional licence).** This is not legal advice. AGPL generally requires offering the source of a network service that uses it.
   - (A) Accept AGPL for the backend and publish its source. This keeps 1:1 parity and arbitrary locations at runtime.
   - (B) Keep pyswisseph only in an offline `tools/` generator and ship only generated data. The backend stays licence-free, but there is a fixed city list and new locations need a manual run.
   - (C) Buy the professional licence. This is clean, but it costs money.
   - (D) Run the same algorithm on a permissive engine (e.g. Skyfield + JPL DE440). The risk: the sunrise definition (refraction, limb, pressure defaults) and the delta-T model differ, so dates near boundaries may flip. Golden tests would catch this, but parity cannot be guaranteed. ADR-0006 also says "port 1:1".
   - **Recommendation:** A if you're fine with the backend being open source under AGPL, otherwise B. Either way, this task's code is the same: swisseph is isolated in `tristhana.moon` and could become an optional dependency group for B. Your decision; it gets recorded as ADR-0009.
2. If SYC's posted 2025 dates or your city calendars disagree with the generator on any date, which source wins in the tests: the generator (we document the difference) or the published calendar (we investigate the algorithm)?
3. Do we drop the Mysuru master/local **index**? I recommend yes: store per-location lists only. For MD-04, match events by phase within ±1 day, which is more robust than sequential indices.
4. Polar or high-latitude locations without a daily sunrise (e.g. Murmansk in December): should we reject the location and fall back to Mysuru with a gentle notice, or use another rule?
5. Is the 2025–2100 range enough for stored calendars, or should pre-computation be rolling (current year + 2)?

### Answers (owner, 2026-10-18)
1. **A**: accept AGPL-3.0; the backend source will be published under AGPL. Recorded in ADR-0009.
2. **The generator wins.** Mismatches with published calendars go into a reviewed known-differences fixture with a reason. The algorithm is never changed to fit. Real SYC differences are handled by the MD-05 official override.
   - 2b. The owner's city calendars were produced by generator.py, so they are not independent evidence. They are dropped as a separate fixture set.
3. **Drop the index.** Store per-location lists; MD-04 pairs events by phase within ±1 day.
4. **Reject locations with no sunrise** (any NoSunriseError in the year). Fall back to the teacher's calendar, else Mysuru, else a city the user picks, with a gentle notice. No twilight or nearest-sunrise rule.
5. **Rolling window**: current year + 2, plus on-demand backfill for imported history, and recompute when `algo_version` changes. Fixtures still cover 2025–2100.
