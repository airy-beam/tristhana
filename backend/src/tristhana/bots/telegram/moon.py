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
from tristhana.bots.telegram import remind_callbacks as rcb
from tristhana.bots.telegram import settings_callbacks as scb
from tristhana.bots.telegram.calendar_feed import entry_button
from tristhana.bots.telegram.moon_callbacks import PREFIX, MoonCallback, decode, encode
from tristhana.bots.telegram.runtime import MoonUseCases
from tristhana.bots.telegram.screens import Reply, Screen, answered, button, show
from tristhana.domain.accounts import Account, home_city_of, moon_follow_of
from tristhana.domain.locale import Locale
from tristhana.domain.moon import City, MoonDay, MoonDayKind, MoonFollow, MoonPhase, MoonSource
from tristhana.domain.notifications import (
    DEFAULTS,
    SEND_TIMES,
    InvalidSettings,
    NotificationSettings,
)
from tristhana.domain.teacher_links import shown_name

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


def moon_status(
    t: Translator,
    locale: Locale,
    settings: NotificationSettings,
    zone: str | None,
    today: date,
    place: City | None = None,
) -> str:
    """The moon reminder line ("🔔 Reminders: 7 and 1 day before at 19:00 …")."""
    if zone is None:
        return t.t(locale, "moon-zone-needed")
    if not settings.moon.on:
        return t.t(locale, "moon-reminders-off")
    code = "".join(str(k) for k in sorted(settings.moon.offsets, reverse=True))
    return t.t(
        locale,
        "moon-reminders-on",
        offsets=t.t(locale, "moon-offsets", code=int(code)),  # numeric variant keys
        time=TimeArg(today, settings.moon.at, zone, place),
    )


def register_moon(
    router: Router, moon: MoonUseCases, translator: Translator, calendar_entry: bool = False
) -> None:
    screens = MoonScreens(moon, translator, calendar_entry)

    @router.message(Command("moon"))
    async def on_moon(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        screen = await screens.view(Principal(account))
        return message.answer(screen.text, reply_markup=screen.markup)

    @router.callback_query(F.data.startswith(f"{PREFIX}:"))
    async def on_moon_tap(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        cb = decode(callback.data)
        note = callback.message.text if isinstance(callback.message, Message) else None
        screen = await answered(callback, screens.handle(Principal(account), cb, note))
        return show(callback, screen) if screen else None


class MoonScreens:
    def __init__(
        self, moon: MoonUseCases, translator: Translator, calendar_entry: bool = False
    ) -> None:
        self._m = moon
        self._t = translator
        self._calendar = calendar_entry  # SC-06: "📅 Add to calendar"

    async def handle(
        self, principal: Principal, cb: MoonCallback | None, note: str | None = None
    ) -> Screen | None:
        """`note`: the tapped message's text, which Keep edits in place (stateless)."""
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
                case "follow":
                    account = await self._m.set_location.execute(principal, None)
                    return await self.view(Principal(account))
                case "follow_shala":
                    account = await self._m.set_location.execute(principal, None, follow="shala")
                    return await self.view(Principal(account))
                case "keep":
                    return await self._keep(principal, cb.slug or "", note, locale)
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

    async def _keep(
        self, principal: Principal, slug: str, note: str | None, locale: Locale
    ) -> Screen:
        """The first-student note, edited in place: the Keep row goes, 👥 My students stays."""
        from tristhana.bots.telegram import teacher_links

        result = await self._m.keep.execute(principal, slug)
        city = result.follow.city.name(locale)
        line = self._t.t(locale, "moon-kept" if result.kept else "moon-keep-already", city=city)
        joined = (note or "").split("\n\n", 1)[0]  # `link-student-joined` is one paragraph
        markup = teacher_links.joined_screen(self._t, locale, None).markup
        return Screen(f"{joined}\n\n{line}" if joined else line, markup)

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
        source = self._source(locale, v.follow)
        if source:
            lines.append(source)
        upcoming = v.days[:UPCOMING]
        if upcoming:
            lines.append("\n".join(self._day_lines(locale, d, v) for d in upcoming))
        else:
            lines.append(self._t.t(locale, "moon-none"))
        lines.append(self._t.t(locale, "moon-calc-note", city=city))
        if v.shared is not None:  # MD-02: told to anyone with students
            # What the students get: this choice, else the default (one hop, never inherited).
            theirs = city if v.shared else self._m.cities.default.name(locale)
            # "like yours" is untrue for one who follows their own teacher.
            chosen = "yes" if v.shared else "follow" if v.follow.follow_chosen else "no"
            lines.append(self._t.t(locale, "moon-teacher-shared", chosen=chosen, city=theirs))
        lines.append(self._status(locale, v, principal.account))
        rows = [
            [
                button(self._t, locale, "moon-change-city", _data(action="cities", page=0)),
                button(self._t, locale, "moon-reminders", _data(action="reminders")),
            ]
        ]
        # Only for a chosen city: a teacher's city is not where the student lives (MD-04 Q3).
        chosen = v.follow.source is MoonSource.CHOSEN
        if not v.zone_known and chosen and v.city is not self._m.cities.default:
            rows.append(
                [
                    InlineKeyboardButton(
                        text=self._t.t(locale, "moon-use-city-zone", city=city),
                        callback_data=_data(action="zone", slug=v.city.slug),
                    )
                ]
            )
        if self._calendar:
            rows.append([entry_button(self._t, locale)])
        return Screen("\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

    def _source(self, locale: Locale, follow: MoonFollow) -> str | None:
        """Where the city comes from (MD-02, SC-01), under the title; nothing for a plain
        city."""
        if follow.source is MoonSource.SHALA and follow.shala is not None:
            return self._t.t(locale, "moon-source-shala", shala=follow.shala.name)
        teacher = follow.teacher
        if teacher is None:
            return None
        name = shown_name(teacher.name) or self._t.t(locale, "link-no-name")
        if follow.source is MoonSource.TEACHER:
            return self._t.t(locale, "moon-source-teacher", name=name)
        return self._t.t(
            locale, "moon-source-teacher-none", name=name, city=follow.city.name(locale)
        )

    def _day_lines(self, locale: Locale, d: MoonDay, v: MoonView) -> str:
        """The day, and the home city's date under it when that differs (MD-04)."""
        line = self._day_line(locale, d, v.today)
        other = v.home_dates.get(d.date)
        if v.home is None or other is None:
            return line
        fyi = self._t.t(
            locale,
            "moon-home-fyi",
            city=v.home.name(locale),
            date=DateArg(other, with_year=other.year != v.today.year),
        )
        return f"{line}\n{fyi}"

    def _day_line(self, locale: Locale, d: MoonDay, today: date) -> str:
        return self._t.t(
            locale,
            "moon-day-line",
            phase=self._t.t(locale, "moon-phase-long", phase=d.kind.phase.value),
            date=DateArg(d.date, with_year=d.date.year != today.year),
            **{"in": self._t.t(locale, "moon-in-days", n=(d.date - today).days)},
        )

    def _status(self, locale: Locale, v: MoonView, account: Account) -> str:
        place = home_city_of(account, self._m.cities)
        return moon_status(self._t, locale, v.settings, v.zone, v.today, place)

    def cities(self, principal: Principal, page: int) -> Screen:
        locale = principal.account.locale
        ordered = self._m.cities.ordered(locale)
        pages = max(1, -(-len(ordered) // CITY_PAGE))
        page = min(page, pages - 1)
        account = principal.account
        follow = moon_follow_of(account, self._m.cities)
        teacher = account.main_teacher
        # One tick per page: the follow row, else the city in use.
        following = teacher is not None and (
            follow.source is MoonSource.TEACHER or follow.follow_chosen
        )
        shala = account.shala
        on_shala = shala is not None and follow.source is MoonSource.SHALA
        current = None if following or on_shala else follow.city.slug
        shown = ordered[page * CITY_PAGE : (page + 1) * CITY_PAGE]
        buttons = [self._city_button(locale, c, c.slug == current) for c in shown]
        rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
        home = home_city_of(account, self._m.cities)
        if home is not None and home.slug != current:  # MD-04: a snapshot, not a link
            same = InlineKeyboardButton(
                text=self._t.t(locale, "moon-same-as-city", city=home.name(locale)),
                callback_data=_data(action="city", slug=home.slug),
            )
            rows.insert(0, [same])
        if shala is not None:  # SC-01: after "Follow my teacher", only with a shala
            text = self._t.t(locale, "moon-follow-shala", shala=shala.name)
            rows.insert(
                0,
                [
                    InlineKeyboardButton(
                        text=f"✓ {text}" if on_shala else text,
                        callback_data=_data(action="follow_shala"),
                    )
                ],
            )
        if teacher is not None:  # MD-02: first, only with a main teacher
            name = shown_name(teacher.name) or self._t.t(locale, "link-no-name")
            text = self._t.t(locale, "moon-follow-teacher", name=name)
            rows.insert(
                0,
                [
                    InlineKeyboardButton(
                        text=f"✓ {text}" if following else text,
                        callback_data=_data(action="follow"),
                    )
                ],
            )
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
            [
                button(
                    self._t, locale, "remind-practice-link", rcb.encode(rcb.RemindCallback("view"))
                ),
                button(self._t, locale, "log-back", _data(action="view")),
            ],
            [button(self._t, locale, "settings-link", scb.encode(scb.SettingsCallback("view")))],
        ]
        return Screen(
            self._status(locale, v, principal.account), InlineKeyboardMarkup(inline_keyboard=rows)
        )
