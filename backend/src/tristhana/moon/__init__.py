"""Moon-day computation: a 1:1 port of the owner-verified generator.py (Swiss Ephemeris).

Moon days are computed offline/pre-computed only, never on a tap path (ADR-0006, ADR-0009).
The one exception is `sunrise_at` for a single day, when a moon card is made (ADR-0052).
"""

from importlib.metadata import version as _version

from tristhana.moon._ephemeris import set_ephemeris_path
from tristhana.moon.compute import compute_moon_days, sunrise_at
from tristhana.moon.errors import (
    EphemerisMissingError,
    MoonError,
    MoonRangeError,
    NoSunriseError,
)

# Stored calendars carry this; a change (port, Swiss Ephemeris, tz data) recomputes them.
# Read from package metadata, so importing this module still doesn't load swisseph.
ALGO_VERSION = f"generator-port-1;pyswisseph-{_version('pyswisseph')};tzdata-{_version('tzdata')}"

__all__ = [
    "ALGO_VERSION",
    "EphemerisMissingError",
    "MoonError",
    "MoonRangeError",
    "NoSunriseError",
    "compute_moon_days",
    "set_ephemeris_path",
    "sunrise_at",
]
