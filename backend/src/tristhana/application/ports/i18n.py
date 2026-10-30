from dataclasses import dataclass
from datetime import date, time
from typing import Protocol

from tristhana.domain.locale import Locale
from tristhana.domain.moon import City


@dataclass(frozen=True, slots=True)
class DateArg:
    """A date for a message: "Sun, Oct 18", or "Sun, Oct 18, 2025" with `with_year`. The
    caller decides (it knows the person's "today"; the translator has no clock)."""

    day: date
    with_year: bool = False


@dataclass(frozen=True, slots=True)
class TimeArg:
    """A wall-clock time in a zone on a date: "06:30 Almaty (UTC+5)" (CLAUDE.md time label;
    the offset is the one on that date, so daylight saving is right)."""

    day: date
    at: time
    zone: str
    place: City | None = None  # the home city: names the zone only if it is its zone (MD-04)


class Translator(Protocol):
    def t(self, locale: Locale, key: str, **args: str | int | DateArg | TimeArg) -> str:
        """The message `key` in `locale`; raises KeyError for an unknown key. `DateArg`s are
        formatted for the locale ("Sun, Oct 18" / «вс, 18 окт.»)."""
        ...
