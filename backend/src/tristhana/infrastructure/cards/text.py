"""The strings a share card shows, resolved before drawing (ST-07): Fluent `card.ftl`,
Babel month and weekday names, catalog names (simple Latin in EN, Cyrillic in RU, IAST as
small metadata). No Pillow here."""

from dataclasses import dataclass
from datetime import date

from tristhana.application.ports.i18n import Translator
from tristhana.domain.locale import Locale
from tristhana.domain.practice import PracticeCatalog
from tristhana.domain.progression import shows_traditional
from tristhana.domain.share_cards import (
    AsanaCard,
    AsanaVariant,
    Card,
    CountCard,
    MonthCard,
    YearCard,
)


@dataclass(frozen=True, slots=True)
class CardText:
    """Every string a card shows, already translated."""

    title: str = ""  # "October 2026"; the asana card's kicker ("New asana")
    headline: str = ""  # "18 practice days in October"; the asana or series name
    subline: str = ""  # the series' traditional name ("Yoga Chikitsa"), in serif
    lines: tuple[str, ...] = ()  # series names, time on the mat; IAST, series, date
    legend_practice: str = ""
    legend_moon: str = ""
    weekdays: tuple[str, ...] = ()  # Monday first
    months: tuple[str, ...] = ()  # 12 short month names (the year card)
    number: str = ""  # the count card's "1,000" / «1 000»
    footer: str = ""


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def month_year(day: date, locale: Locale) -> str:
    """ "October 2026" / «Октябрь 2026» (standalone month)."""
    from babel.dates import format_date

    return _cap(str(format_date(day, "LLLL y", locale=locale)))


def resolve(t: Translator, catalog: PracticeCatalog, card: Card, locale: Locale) -> CardText:
    from babel.dates import get_day_names, get_month_names
    from babel.numbers import format_decimal

    footer = t.t(locale, "card-footer")
    practice, moon = t.t(locale, "card-legend-practice"), t.t(locale, "card-legend-moon")
    match card:
        case MonthCard():
            names = get_day_names("short", context="stand-alone", locale=locale)
            lines: list[str] = []
            if card.series:
                lines.append(" · ".join(t.t(locale, "card-series-name", n=n) for n in card.series))
            if card.minutes:
                hours, minutes = divmod(card.minutes, 60)
                lines.append(t.t(locale, "card-month-time", hours=hours, minutes=minutes))
            return CardText(
                title=month_year(date(card.year, card.month, 1), locale),
                headline=t.t(
                    locale, "card-month-practices", count=card.practiced, month=card.month
                ),
                lines=tuple(lines),
                weekdays=tuple(_cap(str(names[i])) for i in range(7)),
                footer=footer,
                legend_practice=practice,
                legend_moon=moon,
            )
        case YearCard():
            key = "card-year-done" if card.finished else "card-year-so-far"
            months = get_month_names("abbreviated", context="stand-alone", locale=locale)
            return CardText(
                headline=t.t(locale, key, count=card.practiced, year=str(card.year)),
                months=tuple(_cap(str(months[m])) for m in range(1, 13)),
                footer=footer,
                legend_practice=practice,
                legend_moon=moon,
            )
        case AsanaCard():
            return _asana(t, catalog, card, locale, footer)
        case CountCard():
            return CardText(
                number=str(format_decimal(card.count, locale=locale)),
                headline=t.t(locale, "card-count", count=card.count),
                footer=footer,
            )


def _asana(
    t: Translator, catalog: PracticeCatalog, card: AsanaCard, locale: Locale, footer: str
) -> CardText:
    when = month_year(date(card.year, card.month, 1), locale)
    series = catalog.get(card.series)
    number = series.number if series else 1
    if card.variant is AsanaVariant.NEW_ASANA:
        stop = catalog.stop(card.series, card.key or "")
        name = stop.label(locale) if stop else (card.key or "")
        iast = stop.names.iast if stop else None
        if iast and stop and stop.variant:
            iast = f"{iast} {stop.variant.upper()}"
        lines = [line for line in (iast, t.t(locale, "card-series-name", n=number), when) if line]
        return CardText(
            title=t.t(locale, "card-new-asana"), headline=name, lines=tuple(lines), footer=footer
        )
    key = (
        "card-series-begins"
        if card.variant is AsanaVariant.SERIES_BEGINS
        else "card-series-complete"
    )
    subline, lines = "", [when]
    if series is not None and series.traditional is not None and shows_traditional(series):
        names = series.traditional
        subline = names.ru if locale == "ru" else names.latin
        if names.iast:
            lines.insert(0, names.iast)
    elif number >= 3:  # Advanced: the other name ("Third series" / «Advanced A»), no Sthira Bhaga
        subline = t.t(locale, "card-series-other-name", n=number)
    return CardText(
        headline=t.t(locale, key, n=number), subline=subline, lines=tuple(lines), footer=footer
    )
