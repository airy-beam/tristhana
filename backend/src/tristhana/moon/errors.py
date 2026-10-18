from datetime import date


class MoonError(Exception):
    """Base class for moon-day computation errors."""


class MoonRangeError(MoonError):
    """The requested dates are empty or outside the bundled ephemeris coverage."""


class NoSunriseError(MoonError):
    """The sun does not rise at this location on this date (polar day or night)."""

    def __init__(self, day: date) -> None:
        super().__init__(f"no sunrise on {day.isoformat()}")
        self.day = day


class EphemerisMissingError(MoonError):
    """Swiss Ephemeris files were not found; we never fall back to the less precise Moshier."""
