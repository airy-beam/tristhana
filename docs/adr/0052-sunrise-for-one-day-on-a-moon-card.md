# ADR-0052: The moon day card computes one sunrise when it is made
- Status: accepted 2026-11-21 (owner: "All as recommended", ST-10)
- Date: 2026-11-21
## Context
ST-10 adds a moon day share card that shows the local sunrise at the followed city ("Sunrise 06:25 Mysuru"). The stored calendar (`moon_day`, MD-01) holds only the date and kind. ADR-0006 and ADR-0009 keep the moon module off the tap path: calendars are computed ahead of time and read from Postgres. Computing a year takes 0.04–0.26 s, but one sunrise takes milliseconds.
## Decision
- `tristhana.moon.sunrise_at(location, day)` wraps the existing `_ephemeris.sunrise_jd` (the same function and rounding that decide moon days, under the same lock) and returns a UTC instant. It adds no new algorithm.
- A separate port, `SunriseCalculator.sunrise(location, day) -> datetime | None`, sits next to `MoonCalculator` (so nothing that computes calendars changes). `GeneratorMoonCalculator` implements both; it runs `sunrise_at` in a worker thread and returns None on any `MoonError`, so the card is drawn without the sunrise line rather than failing. The card shows the sunrise rounded to the nearest minute, as almanacs give it.
- Only `CreateShareCard` calls it, once per card, for a moon day within the card's window. Moon days themselves are still never computed on a tap: the date and kind come from the stored calendar.
- Nothing is stored: the PNG is kept 24 h (ADR-0040), and the sunrise lives only in it.
## Consequences
- The first moon card after a cold start pays the lazy swisseph import and ephemeris open (tens of ms), next to Pillow's own (ADR-0040). Later cards pay a few ms.
- The sunrise is the one the calendar is computed with, for the same city. (Without the ephemeris files `rise_trans` falls back to Moshier silently on this path, a difference of seconds; the calendar job fails loudly in that case.)
- `sunrise_at` takes the ephemeris lock, so a card made while the tick computes a city-year in the same process can wait for it, up to ~0.26 s.
- MD-05 (official SYC dates) doesn't change this: the sunrise shown is the sunrise on that date in that city, whichever source the date came from.
## Alternatives considered
- **Store sunrise in `moon_day` during pre-compute:** keeps the module off the tap path entirely, but adds a column, a recompute of every stored calendar (`ALGO_VERSION` bump) and a change to the 1:1 port's output, all for a single line on one card.
- **No sunrise on the card:** simpler, but the owner asked for it if it was already at hand, and it is.
