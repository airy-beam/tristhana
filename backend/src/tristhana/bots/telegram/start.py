"""`/start` (UI-01, UI-06): the front door for a person who has done nothing here yet, shown
once; Today for everyone else, and from then on.

"Shown once" is `account.welcomed`, written by `MarkWelcomed` on the first `/start`. A link
from a teacher or a shala (`/start t_…`, `h_…`, `hs_…`) writes it too, alongside its own
read: someone who arrived by invitation never meets the front door, then or later.

    o1:l:en / o1:l:ru   the language button under greetings sent before UI-06: switches the
                        language and shows Today
"""

import asyncio
from collections.abc import Awaitable
from typing import TYPE_CHECKING

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.methods import SendMessage
from aiogram.types import CallbackQuery, InlineKeyboardButton, Message

from tristhana.application.accounts import MarkWelcomed
from tristhana.application.policies import Principal
from tristhana.bots.telegram.days import DayScreens
from tristhana.bots.telegram.home import HomeScreens
from tristhana.bots.telegram.runtime import SettingsUseCases
from tristhana.bots.telegram.screens import Reply, Screen, answered, nothing, show
from tristhana.bots.telegram.settings import client_profile
from tristhana.domain.accounts import Account, ExternalProfile, ProfilePatch
from tristhana.domain.locale import LOCALES, Locale
from tristhana.domain.shalas import parse_shala_invite
from tristhana.domain.teacher_links import parse_invite

if TYPE_CHECKING:
    from tristhana.bots.telegram.shalas import ShalaScreens
    from tristhana.bots.telegram.teacher_links import LinkScreens

PREFIX = "o1"


def decode(data: str | None) -> Locale | None:
    """The language to switch to, or None for anything malformed or from another version."""
    parts = (data or "").split(":")
    if len(parts) == 3 and parts[:2] == [PREFIX, "l"] and parts[2] in LOCALES:
        return parts[2]  # type: ignore[return-value]
    return None


def register_start(
    router: Router,
    screens: "StartScreens",
    invites: "LinkScreens | None" = None,
    shalas: "ShalaScreens | None" = None,
) -> None:
    # Only `t_<code>` (ID-04), `h_<code>` and `hs_<code>` (SC-01) mean anything; no payload
    # is ever logged.
    @router.message(CommandStart())
    async def on_start(  # pyright: ignore[reportUnusedFunction]
        message: Message, account: Account, command: CommandObject
    ) -> SendMessage:
        principal = Principal(account)
        code = parse_invite(command.args)
        shala = parse_shala_invite(command.args)
        if code is not None and invites is not None:
            screen = await screens.by_invite(principal, invites.invited(principal, code))
        elif shala is not None and shalas is not None:
            screen = await screens.by_invite(principal, shalas.invited(principal, shala))
        else:
            screen = await screens.entry(principal)
        return message.answer(screen.text, reply_markup=screen.markup)

    @router.callback_query(F.data.startswith(f"{PREFIX}:"))
    async def on_language(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        locale = decode(callback.data)
        if locale is None:
            await answered(callback, nothing())
            return None
        work = screens.switch(Principal(account), locale, client_profile(callback.from_user))
        screen = await answered(callback, work)
        return show(callback, screen)


class StartScreens:
    def __init__(
        self,
        days: DayScreens,
        settings: SettingsUseCases,
        home: HomeScreens,
        welcome: MarkWelcomed | None = None,
    ) -> None:
        self._days = days
        self._s = settings
        self._home = home
        self._welcome = welcome  # None: a runtime built without it never shows the front door

    async def entry(self, principal: Principal) -> Screen:
        """`/start` with no invite. The first one records that the person was welcomed (one
        write, which also says whether they have a logged day): the front door for someone
        who has done nothing yet, Today with the one-time Menu hint for anyone else. Every
        later one is Today (one read)."""
        if principal.account.welcomed or self._welcome is None:
            return await self.start(principal)
        met = await self._welcome.execute(principal)
        if met.front_door:
            return self._home.front(principal.account.locale)
        return await self._days.today_screen(principal, hint=met.first)

    async def by_invite(self, principal: Principal, invited: Awaitable[Screen]) -> Screen:
        """`/start` with an invite: its own screen. Until the person is welcomed, that is
        recorded alongside the invite's read, so the front door never shows later."""
        if principal.account.welcomed or self._welcome is None:
            return await invited
        screen, _ = await asyncio.gather(invited, self._welcome.execute(principal))
        return screen

    async def start(
        self,
        principal: Principal,
        lead: str | None = None,
        lead_row: list[InlineKeyboardButton] | None = None,
    ) -> Screen:
        """Today. An answered invite (ID-04, SC-01) puts its line and button on top."""
        return await self._days.today_screen(principal, lead=lead, lead_row=lead_row)

    async def switch(self, principal: Principal, locale: Locale, client: ExternalProfile) -> Screen:
        account = await self._s.profile.execute(principal, ProfilePatch(locale=locale), client)
        return await self.start(Principal(account))  # the same message, in the new language
