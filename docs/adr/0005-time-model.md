# ADR-0005: Time model
- Status: accepted · Date: 2026-10-18
- Amended by ADR-0044 (2026-11-16): a displayed time always names its place; the UTC offset shows only outside the viewer's own zone.
## Decision
Instants are `timestamptz` (UTC). Practice days are a local `date` + the IANA tz at logging time. Classes are wall-clock time + IANA zone + RRULE, expanded in that zone. Users have an IANA tz, auto-detected from the Mini App (`Intl`), else asked when first needed. No fixed offsets anywhere. Every displayed time carries a zone label. Details: notes `06 Time Zones.md`.
