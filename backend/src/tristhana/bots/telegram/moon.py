"""Moon screens (MD-03): `/moon`, the city picker, reminder settings, and the reminder
message itself (rendered here for the notifier, so wording lives in one place)."""

from datetime import date

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from tristhana.application.moon import MoonView, UnknownLocation
from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import DateArg, TimeArg, Translator
from tristhana.application.ports.notifications import MoonPatch, MoonReminder
from tristhana.bots.telegram.moon_callbacks import PREFIX, MoonCallback, decode, encode
from tristhana.bots.telegram.runtime import MoonUseCases
from tristhana.bots.telegram.screens import Reply, Screen, answered, button, show
from tristhana.domain.accounts import Account
from tristhana.domain.locale import Locale
from tristhana.domain.moon import City, MoonDay, MoonDayKind, MoonPhase
from tristhana.domain.notifications import DEFAULTS, SEND_TIMES, InvalidSettings

UPCOMING = 4  # moon days on the /moon screen (~2 months)
CITY_PAGE = 12  # 2 columns x 6 rows


def _data(**kw: object) -> str:
    return encode(MoonCallback(**kw))  # type: ignore[arg-type]


def reminder_screen(
    t: Translator, locale: Locale, r: MoonReminder, status: str | None = None
) -> Screen:
    """The reminder message (also re-rendered after a quick action, with a status line)."""
    phase = r.moon_day.kind.phase.value
    text = t.t(
        locale,
        "moon-reminder",
        days=r.days_before,
        phase=t.t(locale, "moon-phase", phase=phase),
        **{"phase-lower": t.t(locale, "moon-phase-lower", phase=phase)},
        date=DateArg(r.moon_day.date, with_year=r.moon_day.date.year != r.today.year),
        city=r.city.name(locale),
    )
    if r.intro:
        code = int("".join(str(k) for k in sorted(r.offsets, reverse=True)) or "1")
        intro = t.t(locale, "moon-reminder-intro", offsets=t.t(locale, "moon-offsets", code=code))
        text = intro + "\n\n" + text
    if status:
        text += "\n\n" + t.t(locale, status)
    quick = {
        "moon_date": r.moon_day.date,
        "phase": r.moon_day.kind.phase,
        "days_before": r.days_before,
    }
    first = (
        [button(t, locale, "moon-turn-back-on", _data(action="quick", quick="on", **quick))]
        if status == "moon-reminder-off"
        else [
            button(
                t, locale, "moon-only-day-before", _data(action="quick", quick="only1", **quick)
            ),
            button(t, locale, "moon-turn-off", _data(action="quick", quick="off", **quick)),
        ]
    )
    rows = [first, [button(t, locale, "moon-all-days", _data(action="view"))]]
    return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))


def register_moon(router: Router, moon: MoonUseCases, translator: Translator) -> None:
    screens = MoonScreens(moon, translator)

    @router.message(Command("moon"))
    async def on_moon(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        screen = await screens.view(Principal(account))
        return message.answer(screen.text, reply_markup=screen.markup)

    @router.callback_query(F.data.startswith(f"{PREFIX}:"))
    async def on_moon_tap(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        cb = decode(callback.data)
        screen = await answered(callback, screens.handle(Principal(account), cb))
        return show(callback, screen) if screen else None


class MoonScreens:
    def __init__(self, moon: MoonUseCases, translator: Translator) -> None:
        self._m = moon
        self._t = translator

    async def handle(self, principal: Principal, cb: MoonCallback | None) -> Screen | None:
        if cb is None:
            return None
        locale = principal.account.locale
        try:
            match cb.action:
                case "view":
                    return await self.view(principal)
                case "reminders":
                    return await self.reminders(principal)
                case "cities":
                    return self.cities(principal, cb.page)
                case "city":
                    account = await self._m.set_location.execute(principal, cb.slug)
                    return await self.view(Principal(account))
                case "zone":
                    account = await self._m.use_city_zone.execute(principal, cb.slug or "")
                    return await self.view(Principal(account))
                case "offsets":
                    await self._m.reminders.execute(principal, MoonPatch(offsets=cb.offsets))
                    return await self.reminders(principal)
                case "time":
                    await self._m.reminders.execute(principal, MoonPatch(at=cb.at))
                    return await self.reminders(principal)
                case "quick":
                    return await self._quick(principal, cb, locale)
        except (UnknownLocation, InvalidSettings):
            return await self.view(principal)  # stale or forged: just reshow

    async def _quick(self, principal: Principal, cb: MoonCallback, locale: Locale) -> Screen:
        offsets, status = {
            "only1": (frozenset({1}), "moon-reminder-only-1"),
            "off": (frozenset[int](), "moon-reminder-off"),
            "on": (DEFAULTS.moon.offsets, "moon-reminder-on"),
        }[cb.quick or "on"]
        await self._m.reminders.execute(principal, MoonPatch(offsets=offsets))
        view = await self._m.view.execute(principal)
        assert cb.moon_date  # noqa: S101 - decoded with it
        assert cb.phase  # noqa: S101
        kind = MoonDayKind.PURNIMA if cb.phase is MoonPhase.PURNIMA else MoonDayKind.AMAVASYA
        reminder = MoonReminder(
            MoonDay(cb.moon_date, kind), cb.days_before, view.city, False, offsets, view.today
        )
        return reminder_screen(self._t, locale, reminder, status)

    async def view(self, principal: Principal) -> Screen:
        v = await self._m.view.execute(principal)
        locale = principal.account.locale
        city = v.city.name(locale)
        lines = [self._t.t(locale, "moon-title", city=city)]
        upcoming = v.days[:UPCOMING]
        if upcoming:
            lines.append("\n".join(self._day_line(locale, d, v.today) for d in upcoming))
        else:
            lines.append(self._t.t(locale, "moon-none"))
        lines.append(self._t.t(locale, "moon-calc-note", city=city))
        lines.append(self._status(locale, v))
        rows = [
            [
                button(self._t, locale, "moon-change-city", _data(action="cities", page=0)),
                button(self._t, locale, "moon-reminders", _data(action="reminders")),
            ]
        ]
        if not v.zone_known and v.explicit:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=self._t.t(locale, "moon-use-city-zone", city=city),
                        callback_data=_data(action="zone", slug=v.city.slug),
                    )
                ]
            )
        return Screen("\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

    def _day_line(self, locale: Locale, d: MoonDay, today: date) -> str:
        return self._t.t(
            locale,
            "moon-day-line",
            phase=self._t.t(locale, "moon-phase-long", phase=d.kind.phase.value),
            date=DateArg(d.date, with_year=d.date.year != today.year),
            **{"in": self._t.t(locale, "moon-in-days", n=(d.date - today).days)},
        )

    def _status(self, locale: Locale, v: MoonView) -> str:
        if not v.zone_known:
            return self._t.t(locale, "moon-zone-needed")
        if not v.settings.moon.on:
            return self._t.t(locale, "moon-reminders-off")
        code = "".join(str(k) for k in sorted(v.settings.moon.offsets, reverse=True))
        assert v.zone is not None  # noqa: S101 - zone_known above
        zone = v.zone
        return self._t.t(
            locale,
            "moon-reminders-on",
            offsets=self._t.t(locale, "moon-offsets", code=int(code)),  # numeric variant keys
            time=TimeArg(v.today, v.settings.moon.at, zone),
        )

    def cities(self, principal: Principal, page: int) -> Screen:
        locale = principal.account.locale
        ordered = self._m.cities.ordered(locale)
        pages = max(1, -(-len(ordered) // CITY_PAGE))
        page = min(page, pages - 1)
        current = principal.account.moon_location or self._m.cities.default.slug
        shown = ordered[page * CITY_PAGE : (page + 1) * CITY_PAGE]
        buttons = [self._city_button(locale, c, c.slug == current) for c in shown]
        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        paging: list[InlineKeyboardButton] = []
        if page > 0:
            paging.append(
                button(self._t, locale, "page-prev", _data(action="cities", page=page - 1))
            )
        if page < pages - 1:
            paging.append(
                button(self._t, locale, "page-next", _data(action="cities", page=page + 1))
            )
        if paging:
            rows.append(paging)
        rows.append([button(self._t, locale, "log-back", _data(action="view"))])
        return Screen(
            self._t.t(locale, "moon-pick-city"), InlineKeyboardMarkup(inline_keyboard=rows)
        )

    def _city_button(self, locale: Locale, city: City, current: bool) -> InlineKeyboardButton:
        text = city.name(locale)
        return InlineKeyboardButton(
            text=f"✓ {text}" if current else text,
            callback_data=_data(action="city", slug=city.slug),
        )

    async def reminders(self, principal: Principal) -> Screen:
        v = await self._m.view.execute(principal)
        locale = principal.account.locale
        offsets = v.settings.moon.offsets
        toggles = [
            InlineKeyboardButton(
                text=("✓ " if k in offsets else "") + self._t.t(locale, "moon-offset", n=k),
                callback_data=_data(action="offsets", offsets=offsets ^ {k}),
            )
            for k in (7, 3, 1)
        ]
        times = [
            InlineKeyboardButton(
                text=("✓ " if at == v.settings.moon.at else "") + f"{at:%H:%M}",
                callback_data=_data(action="time", at=at),
            )
            for at in SEND_TIMES
        ]
        switch = (
            button(
                self._t, locale, "moon-turn-off", _data(action="offsets", offsets=frozenset[int]())
            )
            if v.settings.moon.on
            else button(
                self._t,
                locale,
                "moon-turn-on",
                _data(action="offsets", offsets=DEFAULTS.moon.offsets),
            )
        )
        rows = [
            toggles,
            times,
            [switch],
            [button(self._t, locale, "log-back", _data(action="view"))],
        ]
        return Screen(self._status(locale, v), InlineKeyboardMarkup(inline_keyboard=rows))
