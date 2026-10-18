"""Practice-details screens (PR-02 context, PR-03 length, PR-05 duration) after 🧘 Practiced.

The common path is 2 taps (🧘 → 🔁 same as last time). Every tap saves at once and edits
the message in place; picker screens need no DB access (the catalog is in memory).
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import TimeArg, Translator
from tristhana.application.practice import DayNotPracticed, NoPreviousPractice
from tristhana.application.practice_patch import PracticePatch
from tristhana.bots.telegram import callbacks as dcb
from tristhana.bots.telegram.practice_callbacks import (
    PREFIX,
    PracticeCallback,
    Range,
    decode,
    encode,
)
from tristhana.bots.telegram.runtime import DayUseCases, PracticeUseCases
from tristhana.bots.telegram.screens import Reply, Screen, answered, button, show
from tristhana.domain.accounts import Account
from tristhana.domain.days import DayStatus
from tristhana.domain.locale import Locale
from tristhana.domain.practice import (
    FULL_PRIMARY,
    HALF_PRIMARY,
    SERIES_HALVES,
    SHORT,
    InvalidLength,
    InvalidPractice,
    Practice,
    PracticeContext,
    PracticeLength,
)

if TYPE_CHECKING:
    from tristhana.bots.telegram.days import DayScreens

DURATIONS = ((30, 45, 60, 75), (90, 120, 150, 180))
GRID_PAGE = 16  # 2 columns x 8 rows
_CONTEXT_ROWS = (
    (PracticeContext.MYSORE, PracticeContext.LED),
    (PracticeContext.PRIVATE, PracticeContext.SELF),
)
_STATIC_KEYS = {
    SHORT: "preset-short",
    HALF_PRIMARY: "preset-half-primary",
    FULL_PRIMARY: "preset-full-primary",
}


def register_practice(router: Router, screens: PracticeScreens) -> None:
    @router.callback_query(F.data.startswith(f"{PREFIX}:"))
    async def on_practice(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        cb = decode(callback.data)
        screen = await answered(callback, screens.handle(Principal(account), cb))
        return show(callback, screen) if screen else None


def _data(action: str, day: date, **kw: object) -> str:
    return encode(PracticeCallback(action, day, **kw))  # type: ignore[arg-type]


def has_details(p: Practice | None) -> bool:
    return p is not None and any(
        v is not None for v in (p.context, p.length, p.duration_min, p.start_time)
    )


class PracticeScreens:
    def __init__(
        self,
        days: DayUseCases,
        practices: PracticeUseCases,
        translator: Translator,
        day_screens: DayScreens,
    ) -> None:
        self._days = days
        self._p = practices
        self._t = translator
        self._day_screens = day_screens

    async def handle(self, principal: Principal, cb: PracticeCallback | None) -> Screen | None:
        if cb is None:
            return None
        try:
            return await self._handle(principal, cb)
        except DayNotPracticed:  # a stale keyboard, or the status changed in another message
            return await self._day_screens.status(
                principal, cb.day, note="practice-day-not-practiced"
            )

    async def _handle(self, principal: Principal, cb: PracticeCallback) -> Screen:
        day = cb.day
        try:
            match cb.action:
                case "open":
                    return await self.details(principal, day)
                case "done":
                    return await self.summary(principal, day)
                case "context":
                    return await self._save(principal, day, PracticePatch.of(context=cb.context))
                case "online":
                    return await self._save(principal, day, PracticePatch.of(online=cb.flag))
                case "duration":
                    return await self._save(
                        principal, day, PracticePatch.of(duration_min=cb.number or None)
                    )
                case "length":
                    return await self._set_length(principal, cb)
                case "same":
                    copied = await self._p.copy_last.execute(principal, day)
                    return await self.details(principal, day, practice=copied)
                case "clear":
                    await self._p.clear.execute(principal, day)
                    return await self.details(principal, day)  # re-read: still practiced?
                case "lengths":
                    return await self.lengths(principal, day)
                case "series":
                    return self.series_screen(principal.account.locale, day)
                case "range":
                    return self.range_screen(principal.account.locale, day, cb.number)
                case "grid":
                    assert cb.range is not None  # noqa: S101 - decoded with a range
                    return self.grid(principal.account.locale, day, cb.range, cb.number)
                case "durations":
                    return await self.durations(principal, day)
        except NoPreviousPractice:
            return await self.details(principal, day, note="practice-no-previous")
        except (InvalidLength, InvalidPractice):
            return await self.details(principal, day)  # forged or stale: just reshow

    async def _save(self, principal: Principal, day: date, patch: PracticePatch) -> Screen:
        saved = await self._p.save.execute(principal, day, patch)
        return await self.details(principal, day, practice=saved)

    async def _set_length(self, principal: Principal, cb: PracticeCallback) -> Screen:
        assert cb.range is not None  # noqa: S101 - decoded with a range
        length = cb.range.length(self._p.catalog, cb.key)
        if length is None:
            raise InvalidLength("unknown series")
        return await self._save(principal, cb.day, PracticePatch.of(length=length))

    async def _current(self, principal: Principal, day: date) -> Practice | None:
        """The day's practice; raises `DayNotPracticed` when the day isn't Practiced."""
        view = await self._days.get.execute(principal, day, day)
        if not view.days or view.days[0].status is not DayStatus.PRACTICED:
            raise DayNotPracticed(day.isoformat())
        practices = view.days[0].practices
        return practices[0] if practices else None

    # Screen P: what was saved + one-tap details.
    async def details(
        self,
        principal: Principal,
        day: date,
        practice: Practice | None = None,
        note: str | None = None,
    ) -> Screen:
        if practice is None:
            practice = await self._current(principal, day)
        locale = principal.account.locale
        lines = self._day_screens.saved_lines(principal, day, DayStatus.PRACTICED)
        if note:
            lines.insert(0, self._t.t(locale, note))
        rows: list[list[InlineKeyboardButton]] = []
        if has_details(practice):
            lines.append(self.summary_text(locale, day, practice))
        else:
            lines.append(self._t.t(locale, "practice-details-prompt"))
        if not has_details(practice):  # only then is "same as last time" offered
            last = (await self._p.presets.execute(principal, day)).last
            if last is not None and has_details(last):
                lines.append(
                    self._t.t(
                        locale, "practice-last-time", summary=self.summary_text(locale, day, last)
                    )
                )
                rows.append([self._button(locale, "practice-same-as-last", _data("same", day))])
        current = practice.context if practice else None
        for pair in _CONTEXT_ROWS:
            rows.append(
                [
                    self._button(
                        locale,
                        f"context-{c.value}",
                        _data("context", day, context=c),
                        mark=c is current,
                    )
                    for c in pair
                ]
            )
        extras: list[InlineKeyboardButton] = []
        if current is not None and current is not PracticeContext.SELF:
            online = bool(practice and practice.online)
            extras.append(
                self._button(
                    locale, "practice-online", _data("online", day, flag=not online), mark=online
                )
            )
        extras.append(self._button(locale, "practice-duration", _data("durations", day)))
        rows.append(extras)
        rows.append([self._button(locale, "practice-length", _data("lengths", day))])
        last_row = [self._button(locale, "practice-done", _data("done", day))]
        if has_details(practice):
            last_row.append(self._button(locale, "practice-clear", _data("clear", day)))
        rows.append(last_row)
        return Screen("\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

    # Screen V: done, a compact summary.
    async def summary(self, principal: Principal, day: date) -> Screen:
        practice = await self._current(principal, day)
        locale = principal.account.locale
        lines = self._day_screens.saved_lines(principal, day, DayStatus.PRACTICED)
        if has_details(practice):
            lines.append(self.summary_text(locale, day, practice))
        today, _ = self._days.get.today(principal)
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    self._button(locale, "practice-details", _data("open", day)),
                    self._button(locale, "log-change", dcb.encode(dcb.DayCallback("open", day))),
                    self._button(
                        locale, "log-another-day", dcb.encode(dcb.DayCallback("week", today))
                    ),
                ]
            ]
        )
        return Screen("\n\n".join(lines), markup)

    # Screen L: presets, recent lengths, "Other…".
    async def lengths(self, principal: Principal, day: date) -> Screen:
        locale = principal.account.locale
        presets = await self._p.presets.execute(principal, day)
        rows: list[list[InlineKeyboardButton]] = [
            [self._length_button(locale, day, SHORT)],
            [
                self._length_button(locale, day, HALF_PRIMARY),
                self._length_button(locale, day, FULL_PRIMARY),
            ],
        ]
        for kind, length in presets.presets:
            if kind == "recent":
                rows.append([self._length_button(locale, day, length)])
        rows.append([self._button(locale, "preset-other", _data("series", day))])
        rows.append([self._button(locale, "log-back", _data("open", day))])
        return Screen(self._t.t(locale, "length-pick"), InlineKeyboardMarkup(inline_keyboard=rows))

    def _length_button(
        self, locale: Locale, day: date, length: PracticeLength
    ) -> InlineKeyboardButton:
        key = _STATIC_KEYS.get(length)
        text = self._t.t(locale, key) if key else self.length_text(locale, length)
        rng = Range.of(self._p.catalog, length)
        assert rng is not None  # noqa: S101 - presets are validated lengths
        return InlineKeyboardButton(
            text=text, callback_data=_data("length", day, range=rng, key=length.end)
        )

    # Screen O: which series did the practice end with?
    def series_screen(self, locale: Locale, day: date) -> Screen:
        buttons: list[InlineKeyboardButton] = []
        for s in self._p.catalog.series:
            data = (
                _data("grid", day, range=Range(s.number, s.number), number=0)
                if s.number == 1
                else _data("range", day, number=s.number)
            )
            buttons.append(
                InlineKeyboardButton(text=self._series(locale, s.number), callback_data=data)
            )
        rows: list[list[InlineKeyboardButton]] = [
            buttons[i : i + 2] for i in range(0, len(buttons), 2)
        ]
        rows.append([self._button(locale, "log-back", _data("lengths", day))])
        return Screen(
            self._t.t(locale, "length-pick-series"), InlineKeyboardMarkup(inline_keyboard=rows)
        )

    # Screen S: only this series, or with the previous one (whole, or one half of it).
    def range_screen(self, locale: Locale, day: date, last: int) -> Screen:
        options = [Range(last, last), Range(last - 1, last)]
        previous = self._p.catalog.by_number(last - 1)
        if previous is not None and previous.slug in SERIES_HALVES:
            options += [Range(last - 1, last, "first_half"), Range(last - 1, last, "second_half")]
        rows = [
            [
                InlineKeyboardButton(
                    text=self._range_text(locale, r, only=True),
                    callback_data=_data("grid", day, range=r, number=0),
                )
            ]
            for r in options
        ]
        rows.append([self._button(locale, "log-back", _data("series", day))])
        return Screen(
            self._t.t(locale, "length-pick-range"), InlineKeyboardMarkup(inline_keyboard=rows)
        )

    # Screen G: the last asana of the last series (stop points only), paged.
    def grid(self, locale: Locale, day: date, rng: Range, page: int) -> Screen:
        series = self._p.catalog.by_number(rng.last)
        if series is None:
            return self.series_screen(locale, day)
        stops = series.stops
        pages = max(1, -(-len(stops) // GRID_PAGE))
        page = min(page, pages - 1)
        shown = stops[page * GRID_PAGE : (page + 1) * GRID_PAGE]
        rows = [
            [self._button(locale, "length-full-series", _data("length", day, range=rng, key=None))]
        ]
        buttons = [
            InlineKeyboardButton(
                text=s.label(locale), callback_data=_data("length", day, range=rng, key=s.key)
            )
            for s in shown
        ]
        rows += [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        paging: list[InlineKeyboardButton] = []
        if page > 0:
            paging.append(
                InlineKeyboardButton(
                    text=self._t.t(locale, "page-prev"),
                    callback_data=_data("grid", day, range=rng, number=page - 1),
                )
            )
        if page < pages - 1:
            paging.append(
                InlineKeyboardButton(
                    text=self._t.t(locale, "page-next"),
                    callback_data=_data("grid", day, range=rng, number=page + 1),
                )
            )
        if paging:
            rows.append(paging)
        back = _data("series", day) if rng.last == 1 else _data("range", day, number=rng.last)
        rows.append([self._button(locale, "log-back", back)])
        text = self._t.t(
            locale, "length-pick-asana", series=self._series(locale, rng.last, lower=True)
        )
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    # Screen D: duration chips.
    async def durations(self, principal: Principal, day: date) -> Screen:
        practice = await self._current(principal, day)
        locale = principal.account.locale
        current = practice.duration_min if practice else None
        rows = [
            [
                InlineKeyboardButton(
                    text=("✓ " if m == current else "") + self._t.t(locale, "duration-min", min=m),
                    callback_data=_data("duration", day, number=m),
                )
                for m in row
            ]
            for row in DURATIONS
        ]
        rows.append(
            [
                self._button(locale, "duration-none", _data("duration", day, number=0)),
                self._button(locale, "log-back", _data("open", day)),
            ]
        )
        return Screen(
            self._t.t(locale, "duration-pick"), InlineKeyboardMarkup(inline_keyboard=rows)
        )

    # Text helpers.
    def summary_text(self, locale: Locale, day: date, p: Practice | None) -> str:
        """E.g. "Mysore · Primary + intermediate → Pasasana · 90 min · 06:30 Almaty (UTC+5)"."""
        if p is None:
            return ""
        parts: list[str] = []
        if p.context is not None:
            parts.append(self._t.t(locale, f"context-{p.context.value}"))
            if p.online:
                parts.append(self._t.t(locale, "practice-online-suffix"))
        if p.length is not None:
            parts.append(self.length_text(locale, p.length))
        if p.duration_min:
            parts.append(self._t.t(locale, "duration-min", min=p.duration_min))
        if p.start_time is not None and p.timezone:
            parts.append(
                self._t.t(locale, "time-label", time=TimeArg(day, p.start_time, p.timezone))
            )
        return " · ".join(parts)

    def length_text(self, locale: Locale, length: PracticeLength) -> str:
        if not length.series:
            return self._t.t(locale, "length-summary", kind="short")
        rng = Range.of(self._p.catalog, length)
        if rng is None:
            return " + ".join(length.series)  # stale catalog keys: still readable
        range_text = self._range_text(locale, rng)
        if length.end is None:
            kind = "full-one" if len(length.series) == 1 and not length.first_part else "full"
            return self._t.t(locale, "length-summary", kind=kind, range=range_text)
        stop = self._p.catalog.stop(length.series[-1], length.end)
        asana = stop.label(locale) if stop else length.end
        return self._t.t(locale, "length-summary", kind="to", range=range_text, asana=asana)

    def _range_text(self, locale: Locale, rng: Range, only: bool = False) -> str:
        names: list[str] = []
        for n in range(rng.first, rng.last + 1):
            if n == rng.first and rng.first_part is not None:
                key = "half-first" if rng.first_part == "first_half" else "half-second"
                names.append(self._t.t(locale, key, series=self._t.t(locale, "series-half", n=n)))
            else:
                names.append(self._series(locale, n, lower=bool(names)))
        if only and rng.first == rng.last and rng.first_part is None:
            return self._t.t(
                locale, "length-only", series=self._series(locale, rng.last, lower=True)
            )
        return " + ".join(names)

    def _series(self, locale: Locale, n: int, lower: bool = False) -> str:
        return self._t.t(locale, "series-lower" if lower else "series-name", n=n)

    def _button(
        self, locale: Locale, key: str, data: str, mark: bool = False
    ) -> InlineKeyboardButton:
        return button(self._t, locale, key, data, mark)
