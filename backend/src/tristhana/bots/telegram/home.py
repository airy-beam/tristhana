"""The simple journey's own screens (UI-06): the front door and what follows it, the Menu,
"For teachers and shalas", Help. Also `/help`, `/menu`, and the one reply to anything typed.

Every screen but two is a pure render from the loaded account (no statement): the first-run
invite reads (or creates) the invite code, and a language tap on the front door writes the
language. Today itself is `days.py`. Buttons that lead into other features carry those
features' own callback data, so nothing here handles them.

A non-admin's `/admin` must answer byte for byte like any typed text (ADR-0042), so both go
through `HomeScreens.typed_reply`.
"""

from collections.abc import Awaitable

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.methods import SendMessage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)

from tristhana.application.policies import Principal, can_manage_schedule, main_shala_seat
from tristhana.application.ports.i18n import Translator
from tristhana.application.teacher_links import LinkUseCases
from tristhana.bots.telegram import classes_callbacks as ccb
from tristhana.bots.telegram import home_callbacks as cb
from tristhana.bots.telegram import moon_callbacks as mcb
from tristhana.bots.telegram import progression_callbacks as gcb
from tristhana.bots.telegram import remind_callbacks as rcb
from tristhana.bots.telegram import settings_callbacks as scb
from tristhana.bots.telegram import shalas_callbacks as shalas_cb
from tristhana.bots.telegram import teacher_links_callbacks as tcb
from tristhana.bots.telegram import tour_callbacks as qcb
from tristhana.bots.telegram.callbacks import DayCallback
from tristhana.bots.telegram.callbacks import encode as day_data
from tristhana.bots.telegram.days import DayScreens
from tristhana.bots.telegram.runtime import SettingsUseCases
from tristhana.bots.telegram.screens import (
    Reply,
    Screen,
    answered,
    app_url,
    button,
    guide_url,
    menu_row,
    nothing,
    show,
)
from tristhana.bots.telegram.settings import client_profile
from tristhana.bots.telegram.teacher_links import invite_screen
from tristhana.domain.accounts import Account, ExternalProfile, ProfilePatch
from tristhana.domain.journey import MenuItem, menu_for
from tristhana.domain.locale import LOCALES, Locale
from tristhana.domain.teacher_links import invite_url

# Where a Menu row leads: another feature's callback data. "My practice" opens the Mini App
# instead (`?open=practice`), so it has no entry here.
_MENU_DATA: dict[MenuItem, str] = {
    MenuItem.TODAY: cb.TODAY,
    MenuItem.ASANAS: gcb.encode(gcb.ProgressionCallback("open")),  # as Help's row (C9)
    MenuItem.MOON: mcb.encode(mcb.MoonCallback("view")),
    MenuItem.CLASSES: ccb.my_week(0, "a"),
    MenuItem.TEACHER: tcb.plain("o"),
    MenuItem.STUDENTS: tcb.students(0),
    MenuItem.SETTINGS: scb.encode(scb.SettingsCallback("view")),
    MenuItem.HELP: cb.HELP,
    MenuItem.TEACH: cb.TEACH,
}
# Where Back on "Shala and classes" goes, by the letter it was opened with.
_SHALA_BACK: dict[cb.ShalaBack, str] = {"f": cb.FRONT, "o": cb.TEACH, "c": cb.CLOSING}


class HomeScreens:
    def __init__(
        self,
        days: DayScreens,
        settings: SettingsUseCases,
        translator: Translator,
        links: LinkUseCases | None = None,
        app: str = "",
        site: str = "",
        bot_username: str = "",
    ) -> None:
        self._days = days
        self._s = settings
        self._t = translator
        self._links = links
        self._app = app
        self._site = site
        self._username = bot_username

    def _button(self, locale: Locale, key: str, data: str) -> InlineKeyboardButton:
        return button(self._t, locale, key, data)

    # --- the front door and what follows it -------------------------------------------

    def front(self, locale: Locale) -> Screen:
        """F0: who are you here as? Three paths and the other language."""
        other: Locale = next(code for code in LOCALES if code != locale)  # type: ignore[assignment]  # two languages today
        switch = self._t.t(
            locale, "start-switch-language", language=self._t.t(other, f"language-{other}")
        )
        rows = [
            [self._button(locale, "welcome-path-practice", cb.PRACTICE)],
            [self._button(locale, "welcome-path-invite", cb.INVITE)],
            [self._button(locale, "welcome-path-shala", cb.shala("f"))],
            [InlineKeyboardButton(text=switch, callback_data=cb.language(other))],
        ]
        text = f"{self._t.t(locale, 'start-greeting')}\n\n{self._t.t(locale, 'welcome-ask')}"
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def switch(self, principal: Principal, locale: Locale, client: ExternalProfile) -> Screen:
        """The front door again, in the chosen language (an explicit choice, ID-06)."""
        account = await self._s.profile.execute(principal, ProfilePatch(locale=locale), client)
        return self.front(account.locale)

    async def invite(self, principal: Principal) -> Screen:
        """F1: the invite on the first run: send the link, or show its QR code. One
        statement (the code is read, or created on the first visit)."""
        locale = principal.account.locale
        if self._links is None or not self._username:  # dev without a bot name: no link
            return self.closing(locale)
        url = invite_url(self._username, await self._links.invite.execute(principal))
        # The same screen as the Menu path's invite (I0), with its own last row.
        return invite_screen(
            self._t,
            locale,
            url,
            [[self._button(locale, "welcome-later", cb.CLOSING)]],
            staff=_staff(principal.account),
        )

    def closing(self, locale: Locale) -> Screen:
        """F2: where the link lives from now on, and what a teacher may want next."""
        rows = [
            [self._button(locale, "welcome-own-practice", cb.TODAY)],
            [self._button(locale, "welcome-path-shala", cb.shala("c"))],
            menu_row(self._t, locale),
        ]
        return Screen(
            self._t.t(locale, "welcome-teacher-next"), InlineKeyboardMarkup(inline_keyboard=rows)
        )

    async def shala(self, principal: Principal, back: cb.ShalaBack) -> Screen:
        """F3: the shalas I am in (each opens its card), what a shala is here, the way to
        create one (the form is in the Mini App), and a line for a student who came for their
        shala's classes, first (UI-06 stage 6, B3, C12). One statement, only for someone in a
        shala (`account.shala`); a pure render for everyone else."""
        account = principal.account
        locale = account.locale
        shalas = self._links.shalas if self._links is not None else None
        mine = (
            () if account.shala is None or shalas is None else await shalas.mine.execute(principal)
        )
        staff = any(s.me.staff for s in mine)
        rows: list[list[InlineKeyboardButton]] = [
            [InlineKeyboardButton(text=f"🏛 {s.name}", callback_data=shalas_cb.on_shala("c", s.id))]
            for s in mine
        ]
        if self._app:
            create = "shala-create-another" if staff else "shala-create"
            rows.append(
                [
                    InlineKeyboardButton(
                        text=self._t.t(locale, create),
                        web_app=WebAppInfo(url=app_url(self._app, "new-shala")),
                    )
                ]
            )
        rows.append([self._button(locale, "log-back", _SHALA_BACK[back])])
        if staff:
            text = self._t.t(locale, "welcome-shala-mine")
        else:
            text = (
                f"{self._t.t(locale, 'welcome-shala-student')}\n\n"
                f"{self._t.t(locale, 'welcome-shala-text')}"
            )
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    # --- the Menu ---------------------------------------------------------------------

    def menu(self, account: Account, typed: bool = False) -> Screen:
        """M0: one row per thing the person can reach, by what they are (`menu_for`). `typed`
        puts a line on top for someone who wrote to the bot instead of tapping."""
        locale = account.locale
        rows: list[list[InlineKeyboardButton]] = []
        for item in menu_for(account):
            label = self._t.t(locale, f"menu-{item.value}")
            if item is MenuItem.PRACTICE:
                if self._app:  # the practice log and stats are the Mini App
                    url = app_url(self._app, "practice")
                    rows.append([InlineKeyboardButton(text=label, web_app=WebAppInfo(url=url))])
                continue
            rows.append([InlineKeyboardButton(text=label, callback_data=_MENU_DATA[item])])
        title = self._t.t(locale, "menu-title")
        text = f"{self._t.t(locale, 'menu-text-lead')}\n\n{title}" if typed else title
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    def typed_reply(self, message: Message, account: Account) -> SendMessage:
        """The reply to anything typed, and to `/admin` from anyone who is not a platform
        admin: the one place it is built, so the two can never differ (ADR-0042). The text
        itself is never read or stored."""
        screen = self.menu(account, typed=True)
        return message.answer(screen.text, reply_markup=screen.markup)

    def teach(self, account: Account) -> Screen:
        """M1: "For teachers and shalas". On a shala's staff, the first row is that shala's
        student invite, not the personal one (UI-06 stage 6, B5; spec §13.6)."""
        locale = account.locale
        if account.shala is not None and _staff(account):
            invite = shalas_cb.on_shala("i", account.shala.id)
            first = self._button(locale, "shala-invite-students", invite)
        else:
            first = self._button(locale, "welcome-path-invite", tcb.plain("i"))
        rows = [
            [first],
            [self._button(locale, "welcome-path-shala", cb.shala("o"))],
            menu_row(self._t, locale),
        ]
        return Screen(self._t.t(locale, "teach-title"), InlineKeyboardMarkup(inline_keyboard=rows))

    # --- Help -------------------------------------------------------------------------

    def help(self, principal: Principal) -> Screen:
        """H0: the things people ask how to do, each one tap away; the public guide (UI-05)
        in the person's language, when its address is set."""
        locale = principal.account.locale
        today, _ = self._days.today(principal)
        rows = [
            [self._button(locale, "help-earlier-day", day_data(DayCallback("week", today)))],
            [self._button(locale, "help-reminder", rcb.encode(rcb.RemindCallback("view")))],
            [self._button(locale, "help-asanas", gcb.encode(gcb.ProgressionCallback("open")))],
            [self._button(locale, "help-join", tcb.plain("o"))],
        ]
        shala = principal.account.shala
        # UI-06 stage 6 (C17): the card, its Classes; Q373 (d): only for a seat that may
        # manage the schedule there, read from the account (no extra statement).
        if shala is not None and can_manage_schedule(main_shala_seat(principal.account)):
            rows.append(
                [self._button(locale, "help-shala-classes", shalas_cb.on_shala("c", shala.id))]
            )
        rows.append([self._button(locale, "menu-teach", cb.TEACH)])
        if self._site:
            # Help's own page: the first steps (UI-06 stage 6, polish).
            url = guide_url(self._site, locale, "start/first-steps/")
            rows.append([InlineKeyboardButton(text=self._t.t(locale, "help-guide"), url=url)])
        rows.append(menu_row(self._t, locale))
        return Screen(self._t.t(locale, "help-title"), InlineKeyboardMarkup(inline_keyboard=rows))

    # --- taps -------------------------------------------------------------------------

    def work(
        self, tap: cb.HomeTap, principal: Principal, client: ExternalProfile
    ) -> Awaitable[Screen]:
        account = principal.account
        locale = account.locale
        match tap.action:
            case "practice" | "today":
                return self._days.today_screen(principal)
            case "invite":
                return self.invite(principal)
            case "language":
                return self.switch(principal, tap.locale or locale, client)
            case "front":
                return _now(self.front(locale))
            case "closing":
                return _now(self.closing(locale))
            case "shala":
                return self.shala(principal, tap.back or "f")
            case "menu":
                return _now(self.menu(account))
            case "teach":
                return _now(self.teach(account))
            case "help":
                return _now(self.help(principal))

    def tour(self, tap: qcb.TourTap, principal: Principal) -> Awaitable[Screen]:
        """A button of the retired bot tour (UI-02), still in chat history: "Done" under a
        tour opened from /start goes to Today, everything else to Help (UI-06 §5)."""
        if tap.n is None and tap.origin == "s":
            return self._days.today_screen(principal)
        return _now(self.help(principal))


async def _now(screen: Screen) -> Screen:
    return screen


def _staff(account: Account) -> bool:
    """On the staff of their main shala: that shala has a student link of its own (B5)."""
    return account.shala is not None and account.shala.staff


def register_home(router: Router, screens: HomeScreens) -> None:
    @router.message(Command("help"))
    async def on_help(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        screen = screens.help(Principal(account))
        return message.answer(screen.text, reply_markup=screen.markup)

    @router.message(Command("menu"))  # hidden: handled, in no command list
    async def on_menu(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        screen = screens.menu(account)
        return message.answer(screen.text, reply_markup=screen.markup)

    @router.callback_query(F.data.startswith(f"{cb.PREFIX}:"))
    async def on_home(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        tap = cb.decode(callback.data)
        if tap is None:
            await answered(callback, nothing())
            return None
        work = screens.work(tap, Principal(account), client_profile(callback.from_user))
        return show(callback, await answered(callback, work))

    @router.callback_query(F.data.startswith(f"{qcb.PREFIX}:"))
    async def on_old_tour(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        tap = qcb.decode(callback.data)
        if tap is None:
            await answered(callback, nothing())
            return None
        return show(callback, await answered(callback, screens.tour(tap, Principal(account))))
