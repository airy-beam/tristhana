"""The days off picker (PR-09), opened from /settings (`s1:o`) or /remind (`r1:dp`). One
setting: the other days are the practice days, and practice reminders come on them. A tap
toggles a day off (at most two) and stays on the picker."""

from collections.abc import Callable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from tristhana.application.ports.i18n import Translator
from tristhana.bots.telegram.screens import Screen
from tristhana.domain.locale import Locale
from tristhana.domain.rest_days import MAX_DAYS_OFF, Weekdays

# Saturday and Sunday first: the usual choices (ashtanga-expert), then the rest.
_ROWS = ((6, 7), (1, 2, 3), (4, 5))


def day_off_line(t: Translator, locale: Locale, days: Weekdays | None) -> str:
    """The /settings line: one or two days off, "no fixed day off", or not chosen yet."""
    if days is None:
        return t.t(locale, "settings-day-off-unset-line")
    if not days:
        return t.t(locale, "settings-day-off-none-line")
    first, *rest = sorted(days)
    if rest:
        return t.t(locale, "settings-days-off-line", d=first, e=rest[0])
    return t.t(locale, "settings-day-off-line", d=first)


def day_off_picker(
    t: Translator,
    locale: Locale,
    current: Weekdays | None,
    choose: Callable[[Weekdays], str],
    reopen: str,
    back: InlineKeyboardButton,
) -> Screen:
    """`choose(days)` = the callback data that sets these days off; `reopen` = this picker
    again (a third day off can't be added: untick one first)."""
    off = current or frozenset()

    def toggle(d: int) -> InlineKeyboardButton:
        name = t.t(locale, "day-off-button", d=d)
        if d in off:
            return InlineKeyboardButton(text=f"😌 {name}", callback_data=choose(off - {d}))
        full = len(off) >= MAX_DAYS_OFF
        return InlineKeyboardButton(text=name, callback_data=reopen if full else choose(off | {d}))

    rows = [[toggle(d) for d in row] for row in _ROWS]
    none = t.t(locale, "day-off-none")
    rows.append(
        [
            InlineKeyboardButton(
                text=("✓ " if current == frozenset() else "") + none,
                callback_data=choose(frozenset()),
            )
        ]
    )
    rows.append([back])
    first = "yes" if current is None else "no"
    text = t.t(locale, "day-off-pick") + "\n\n" + t.t(locale, "day-off-explain", first=first)
    return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))
