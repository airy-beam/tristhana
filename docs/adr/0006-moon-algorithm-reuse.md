# ADR-0006: Reuse the verified moon-day algorithm
- Status: accepted · Date: 2026-10-18
## Decision
Port `Programming/ashtanga/moon_days/generator/generator.py` 1:1 (Swiss Ephemeris, tithi at local sunrise, Purnima = 15, Amavasya = 30, kshaya detection, 2-day de-dup). No alternative algorithms. Pre-compute per location per year into the DB. Admins can import official SYC Mysuru dates to override. Golden tests: SYC 2025 list + the owner's 2025/2026 city calendars.
