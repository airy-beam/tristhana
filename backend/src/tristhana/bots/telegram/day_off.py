"""The weekly day off picker (PR-09), opened from /settings (`s1:o`) or /remind (`r1:dp`).
The same screen, with the callback data and back button of where it was opened."""

from collections.abc import Callable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from tristhana.application.ports.i18n import Translator
from tristhana.bots.telegram.screens import Screen
from tristhana.domain.locale import Locale
from tristhana.domain.rest_days import Weekdays

# Saturday and Sunday first: the usual choices (ashtanga-expert), then the rest.
_ROWS = ((6, 7), (1, 2, 3), (4, 5))


def day_off_line(t: Translator, locale: Locale, days: Weekdays | None) -> str:
    """The /settings line: one day, "no fixed day off", or not chosen yet."""
    if days is None:
        return t.t(locale, "settings-day-off-unset-line")
    if not days:
        return t.t(locale, "settings-day-off-none-line")
    return t.t(locale, "settings-day-off-line", d=min(days))


def day_off_picker(
    t: Translator,
    locale: Locale,
    current: Weekdays | None,
    choose: Callable[[int], str],
    back: InlineKeyboardButton,
) -> Screen:
    """`choose(d)` = the callback data that sets weekday d (0 = no fixed day off)."""

    def pick(d: int, text: str) -> InlineKeyboardButton:
        chosen = current == (frozenset({d}) if d else frozenset())
        return InlineKeyboardButton(text=("✓ " if chosen else "") + text, callback_data=choose(d))

    rows = [[pick(d, t.t(locale, "day-off-button", d=d)) for d in row] for row in _ROWS]
    rows.append([pick(0, t.t(locale, "day-off-none"))])
    rows.append([back])
    first = "yes" if current is None else "no"
    text = t.t(locale, "day-off-pick") + "\n\n" + t.t(locale, "day-off-explain", first=first)
    return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))
