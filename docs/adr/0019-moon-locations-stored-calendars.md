# ADR-0019: Moon locations are a curated city list; calendars are stored per location
- Status: accepted
- Date: 2026-10-19
## Context
MD-01 requires pre-computed, stored moon calendars per location (rolling, recomputed on `algo_version` change; decisions 2026-10-18). The verified module `tristhana.moon` takes lat/lon/zone and is too slow for a tap path. Accounts carry only an IANA zone (often null), never coordinates. Locating a user from coordinates needs `timezonefinder` (tens of MB), and the image is at ~245 of 250 MB. Polar locations must be rejected. MD-02 (teacher/shala calendars) arrives in Phase 3. Spec: `docs/specs/MD-03-moon-reminders.md`.
## Decision
- Locations are a **curated city list** in `data/seed/cities.yaml` (slug, en/ru names, lat/lon, IANA zone), loaded into memory at startup like the catalog (ADR-0017). Mysuru is the default. The 10 golden-fixture cities use the fixtures' exact coordinates. CI checks that every city computes its window without `NoSunriseError`, so no polar city ships.
- The account stores `moon_location` (a slug, null = Mysuru). No coordinates are stored.
- Calendars are stored in `moon_day(location, date, kind)` with a ledger `moon_calendar(location, year, algo_version)`. The scheduler tick (ADR-0018) fills **previous year … current + 2** for every city, and recomputes a city-year when `algo_version` (port version + pyswisseph + tzdata) changes. Reads never compute.
- `location` is a text key, so MD-02 can add shala/teacher locations later (e.g. a `location` table or `geo:<lat>,<lon>` keys rounded to 0.01°) without changing `moon_day`. MD-05 adds a `source` column for the official SYC import.
## Consequences
- No new dependency; ~140 city-years computed once, then ~35 each January; ~3.5 k rows.
- People outside the list pick the nearest city or Mysuru until MD-02 or a coordinate-based option exists.
- A new city ships with a deploy; its calendar appears within one tick.
## Alternatives considered
- **"Share location" + own coordinates or nearest city:** precise, but the zone lookup needs `timezonefinder` (over the image budget), and a nearest-city zone can be hours off for sparse lists.
- **Guess the city from the account zone:** many cities share a zone, and a guess would silently pick the moon date; Mysuru plus an explicit pick is clearer.
- **Compute on demand per request:** too slow for a tap and needs the swisseph lock on the hot path.
- **Ship pre-computed JSON in the image:** no runtime compute, but then a new city or algorithm change needs an offline step, and MD-02's arbitrary locations would need runtime compute anyway.
