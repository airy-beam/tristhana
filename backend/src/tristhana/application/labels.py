"""Readable names for practice lengths, asanas and milestone items, from Fluent and the
catalog. Shared by the bot screens and the export (ST-09), so a length reads the same in a
reply and in `days.csv`."""

from tristhana.application.ports.i18n import Translator
from tristhana.domain.locale import Locale
from tristhana.domain.practice import FirstPart, PracticeCatalog, PracticeLength, Series
from tristhana.domain.progression import STANDING_ONLY, Position, Track


class PracticeLabels:
    def __init__(self, translator: Translator, catalog: PracticeCatalog, track: Track) -> None:
        self._t = translator
        self._catalog = catalog
        self._track = track

    def length(self, locale: Locale, length: PracticeLength) -> str:
        if not length.series:
            return self._t.t(locale, "length-summary", kind="short")
        first, last = self._catalog.get(length.series[0]), self._catalog.get(length.series[-1])
        if first is None or last is None:
            return " + ".join(length.series)  # stale catalog keys: still readable
        range_text = self.range_text(locale, first.number, last.number, length.first_part)
        if length.end is None:
            kind = "full-one" if len(length.series) == 1 and not length.first_part else "full"
            return self._t.t(locale, "length-summary", kind=kind, range=range_text)
        asana = self.stop(locale, length.series[-1], length.end)
        return self._t.t(locale, "length-summary", kind="to", range=range_text, asana=asana)

    def range_text(
        self,
        locale: Locale,
        first: int,
        last: int,
        first_part: FirstPart | None,
        only: bool = False,
    ) -> str:
        names: list[str] = []
        for n in range(first, last + 1):
            if n == first and first_part is not None:
                key = "half-first" if first_part == "first_half" else "half-second"
                names.append(self._t.t(locale, key, series=self._t.t(locale, "series-half", n=n)))
            else:
                names.append(self.series(locale, n, lower=bool(names)))
        if only and first == last and first_part is None:
            return self._t.t(locale, "length-only", series=self.series(locale, last, lower=True))
        return " + ".join(names)

    def all_series(self) -> tuple[Series, ...]:
        return self._catalog.series

    def series(self, locale: Locale, n: int, lower: bool = False) -> str:
        return self._t.t(locale, "series-lower" if lower else "series-name", n=n)

    def stop(self, locale: Locale, series: str, key: str) -> str:
        """The asana name: simple Latin in EN, the catalog's Cyrillic in RU (stale: the key)."""
        stop = self._catalog.stop(series, key)
        return stop.label(locale) if stop else key

    def position(self, locale: Locale, p: Position) -> str:
        """The last given asana, or "sun salutations and standing" for standing only."""
        if p == STANDING_ONLY:
            return self._t.t(locale, "progression-standing-only")
        return self.stop(locale, p.series or "", p.key or "")

    def item(self, locale: Locale, key: str) -> str:
        """The catalog name (+ "(tic-tacs)" where people use one, from Fluent)."""
        item = next((i for i in self._track.items if i.key == key), None)
        name = item.label(locale) if item else key
        return self._t.t(locale, "milestone-label", slug=key, name=name)
