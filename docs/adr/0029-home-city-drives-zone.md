# ADR-0029: The home city drives the time zone
- Status: accepted (owner, 2026-10-30)
- Date: 2026-10-30

## Context
Settings (ID-06, ADR-0021) offer the time zone "by city" from `data/seed/cities.yaml` (ADR-0019), but only `account.timezone` is stored. Several cities share a zone (Almaty/Astana, Moscow/Sochi/Kazan), so the UI guesses which one to mark, and tapping Astana marks Almaty. The time label (ADR-0005, "07:00 Almaty (UTC+5)") names the zone, not where the person lives. MD-04 needs the person's own city to compare its moon days with the followed calendar. People outside the list need a zone without a city. Telegram gives bots no zone, but it can send a location. Spec: `docs/specs/MD-04-my-city-and-local-fyi.md`.

## Decision
- **`account.home_city`** (text, no FK, like `moon_location`):
  - `NULL` = never chosen (drives a one-time nudge)
  - `'-'` = chosen: not listed / not now
  - otherwise a city slug
- **Invariant:** a city slug implies `timezone == city.tz`. It is enforced in one pure domain function (`resolve_profile`), which every account settings write goes through:
  - picking a city writes the city and its zone together;
  - any zone write (travel prompt, UTC, location, phone zone) that doesn't match the city's zone sets `'-'`.

  The DB enforces only what it can see: the slug format, and that a slug needs a zone.
- The city is **never inferred from the zone**, and existing accounts get no backfill.
- **Time labels** use the city name iff the city is set and its zone equals the labelled zone. Otherwise they use the zone's own name. The city comes from the already loaded account plus the in-memory city list, so labels need no extra query.
- **"Moon days: same as my city"** stores the city slug in `moon_location` (a snapshot), not a link. A city cleared by travel or changed later never moves the moon calendar silently.
- **"My city isn't listed":**
  - Mini App: the device zone.
  - Bot: a one-time `request_location`. The coordinates go to an IANA zone through **tzfpy** (Rust core, MIT code, ODbL boundary data from timezone-boundary-builder; ~3 MB wheel, no numpy; lazy-imported in `infrastructure/zone_lookup.py` on the first location, ~15 ms build, about +40 MB RSS).
  - Coordinates are neither stored nor logged.
  - UTC stays an explicit fallback.
- Adding a city is a one-line `cities.yaml` change.

## Consequences
- The UI marks exactly what was chosen, and the label reads "07:00 Astana (UTC+5)".
- A person's city survives only while they live by its clock. After a trip it has to be picked again (one tap).
- `GET /me` carries `home_city` (+ names) and `home_city_chosen`, so the Mini App labels need no city-list request.
- Removing or renaming a city slug in YAML degrades to "no city" (no label, no FYI) until the next zone write normalises it. Slugs should therefore be treated as permanent.
- New dependency tzfpy:
  - its ODbL data needs attribution (README licences, `/privacy`);
  - the lite data can misplace points within ~100 m of a zone border, which is acceptable for picking one's own zone;
  - its memory is paid only by instances that receive a location.
- Location sharing may not work in Telegram Desktop/Web, where UTC and the Mini App remain.

## Alternatives considered
- **Keep zone-only and improve the guess** (the current `_zone_city`): this can't tell Astana from Almaty or Sochi from Moscow, and MD-04 needs a real city.
- **Store the city and derive the zone at read time:** this has no answer for unlisted cities, and every zone reader (the tick, day writes) would need the city list.
- **A DB FK to a `city` table:** cities live in YAML (ADR-0019). A table plus a sync step costs more than the domain check.
- **A link for "same as my city" (`moon_location = 'home'`):** travel would silently change moon days and reminders.
- **timezonefinder:** MIT and accurate, but ~50 MB of data plus numpy (image is 189 MB, Cloud Run 512 MiB).
- **A full IANA zone search in the bot:** long lists in inline keyboards. ID-06 already rejected it ("no full IANA search", 06 Time Zones).
- **Storing coordinates:** this enables a nearest-city guess, but it is sensitive data with no current use.
