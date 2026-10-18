"""Moon-day computation: a 1:1 port of the owner-verified generator.py (Swiss Ephemeris).

Offline/pre-compute use only, never on a tap path. See ADR-0006 and ADR-0009.
"""

from tristhana.moon._ephemeris import set_ephemeris_path
from tristhana.moon.compute import compute_moon_days
from tristhana.moon.errors import (
    EphemerisMissingError,
    MoonError,
    MoonRangeError,
    NoSunriseError,
)

__all__ = [
    "EphemerisMissingError",
    "MoonError",
    "MoonRangeError",
    "NoSunriseError",
    "compute_moon_days",
    "set_ephemeris_path",
]
