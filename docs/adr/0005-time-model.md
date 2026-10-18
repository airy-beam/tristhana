# ADR-0005: Time model
- Status: accepted · Date: 2026-10-18
## Decision
Instants are `timestamptz` (UTC). Practice days are a local `date` + the IANA tz at logging time. Classes are wall-clock time + IANA zone + RRULE, expanded in that zone. Users have an IANA tz, auto-detected from the Mini App (`Intl`), else asked when first needed. No fixed offsets anywhere. Every displayed time carries a zone label. Details: notes `06 Time Zones.md`.
