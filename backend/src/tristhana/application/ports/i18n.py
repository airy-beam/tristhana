from dataclasses import dataclass
from datetime import date
from typing import Protocol

from tristhana.domain.locale import Locale


@dataclass(frozen=True, slots=True)
class DateArg:
    """A date for a message: "Sun, Oct 18", or "Sun, Oct 18, 2025" with `with_year`. The
    caller decides (it knows the person's "today"; the translator has no clock)."""

    day: date
    with_year: bool = False


class Translator(Protocol):
    def t(self, locale: Locale, key: str, **args: str | int | DateArg) -> str:
        """The message `key` in `locale`; raises KeyError for an unknown key. `DateArg`s are
        formatted for the locale ("Sun, Oct 18" / «вс, 18 окт.»)."""
        ...
