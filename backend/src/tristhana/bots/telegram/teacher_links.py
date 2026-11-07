"""Teacher links in the bot (ID-04, ADR-0030): the consent screen on `/start t_<code>`, and
`/teachers`, one screen for both sides. The student always taps last, and the code rides in
the callback, so a new person loses nothing and no pending row exists. The code is never
logged, and no exception carries it. A teacher never learns whether they are someone's main.
"""

from collections.abc import Awaitable
from contextlib import suppress
from typing import TYPE_CHECKING
from urllib.parse import quote, urlencode
from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.methods import SendMessage
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from tristhana.application.policies import Principal
from tristhana.application.ports.i18n import Translator
from tristhana.application.ports.teacher_links import LinksChanged, NotLinked
from tristhana.application.teacher_links import LinkUseCases
from tristhana.bots.telegram import teacher_links_callbacks as cb
from tristhana.bots.telegram.runtime import SettingsUseCases
from tristhana.bots.telegram.screens import (
    Reply,
    Screen,
    answered,
    app_button,
    button,
    nothing,
    show,
)
from tristhana.bots.telegram.settings import client_profile
from tristhana.domain.accounts import Account, ExternalProfile, ProfilePatch
from tristhana.domain.locale import LOCALES, Locale
from tristhana.domain.teacher_links import (
    InviteState,
    Linked,
    effective_primary,
    invite_url,
    next_primary,
    shown_name,
)

if TYPE_CHECKING:
    from tristhana.bots.telegram.start import StartScreens

PAGE = 10
QR_FILE = "tristhana-invite.png"
QR_TIMEOUT_S = 10


def _name(t: Translator, locale: Locale, name: str | None) -> str:
    return shown_name(name) or t.t(locale, "link-no-name")


def joined_screen(t: Translator, locale: Locale, name: str | None) -> Screen:
    """The note a teacher gets when a student confirms, in the teacher's language."""
    open_list = button(t, locale, "link-students-open", cb.students(0))
    return Screen(
        t.t(locale, "link-student-joined", name=_name(t, locale, name)),
        InlineKeyboardMarkup(inline_keyboard=[[open_list]]),
    )


def _find(people: tuple[Linked, ...], id: UUID) -> Linked | None:
    return next((p for p in people if p.id == id), None)


class LinkScreens:
    def __init__(
        self,
        links: LinkUseCases,
        start: "StartScreens",
        settings: SettingsUseCases,
        translator: Translator,
        app: str,
        bot_username: str,
    ) -> None:
        self._links = links
        self._start = start
        self._s = settings
        self._t = translator
        self._app = app
        self._username = bot_username

    def _button(self, locale: Locale, key: str, data: str) -> InlineKeyboardButton:
        return button(self._t, locale, key, data)

    def _consent(self, principal: Principal, code: str, teacher: str | None) -> Screen:
        account = principal.account
        locale = account.locale
        name = _name(self._t, locale, teacher)
        own = shown_name(account.display_name)
        me = f" ({own})" if own else ""
        closing = (
            f"{self._t.t(locale, 'invite-know-them')} "
            f"{self._t.t(locale, 'invite-not-told', name=name)}"
        )
        text = "\n\n".join(
            [
                self._t.t(locale, "invite-ask", name=name),
                self._t.t(locale, "invite-consent", name=name, me=me),
                closing,
            ]
        )
        other: Locale = next(c for c in LOCALES if c != locale)  # type: ignore[assignment]  # two languages today
        switch = self._t.t(
            locale, "start-switch-language", language=self._t.t(other, f"language-{other}")
        )
        rows = [
            [
                self._button(locale, "invite-accept", cb.confirm(code)),
                self._button(locale, "invite-decline", cb.plain("n")),
            ],
            [InlineKeyboardButton(text=switch, callback_data=cb.language(other, code))],
        ]
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def invited(self, principal: Principal, code: str) -> Screen:
        """`/start t_<code>`: the consent screen, or the grid with one line on top."""
        locale = principal.account.locale
        found = await self._links.preview.execute(principal, code)
        if found is None:
            return await self._start.start(principal, self._t.t(locale, "invite-invalid"))
        name = _name(self._t, locale, found.name)
        match found.state:
            case InviteState.OPEN:
                return self._consent(principal, code, found.name)
            case InviteState.OWN:
                lead = self._t.t(locale, "invite-own")
            case InviteState.ALREADY:
                lead = self._t.t(locale, "invite-already", name=name)
            case InviteState.FULL:
                lead = self._t.t(locale, "invite-full")
        return await self._start.start(principal, lead)

    async def accept(self, principal: Principal, code: str) -> Screen:
        account = principal.account
        locale = account.locale
        done = await self._links.accept.execute(principal, code)
        if done is None:  # rotated since the consent screen
            return await self._start.start(principal, self._t.t(locale, "invite-invalid"))
        name = _name(self._t, locale, done.teacher_name)
        if done.created:
            make_main = None
            if done.my_teachers >= 2:
                make_main = [
                    self._button(locale, "links-make-main", cb.person("p", done.teacher_id))
                ]
            return await self._start.start(
                principal, self._t.t(locale, "invite-linked", name=name), make_main
            )
        if done.teacher_id == account.id:
            lead = self._t.t(locale, "invite-own")
        elif done.full and not done.already:
            lead = self._t.t(locale, "invite-full")
        else:  # a duplicate; maybe the second of a double tap
            lead = self._t.t(locale, "invite-already", name=name)
        return await self._start.start(principal, lead)

    async def language(
        self, principal: Principal, locale: Locale, code: str, client: ExternalProfile
    ) -> Screen:
        """The consent screen again in the other language; `o1:` would drop the invite."""
        account = await self._s.profile.execute(principal, ProfilePatch(locale=locale), client)
        return await self.invited(Principal(account), code)

    async def overview(self, principal: Principal) -> Screen:
        locale = principal.account.locale
        found = await self._links.get.execute(principal)
        several = len(found.teachers) >= 2
        main = effective_primary(found.teachers)
        lines = [self._t.t(locale, "links-title")]
        if not found.teachers:
            lines.append(self._t.t(locale, "links-empty"))
        rows: list[list[InlineKeyboardButton]] = []
        for teacher in found.teachers:
            star = "⭐ " if several and teacher.id == main else ""
            label = f"{star}{_name(self._t, locale, teacher.name)}"
            rows.append(
                [InlineKeyboardButton(text=label, callback_data=cb.person("c", teacher.id))]
            )
            if several and teacher.id == main:
                key = "links-main-chosen" if teacher.chosen_primary else "links-main-auto"
                lines.append(self._t.t(locale, key, name=_name(self._t, locale, teacher.name)))
                lines.append(self._t.t(locale, "links-primary-hint"))
        if found.students:
            count = self._t.t(locale, "links-students", count=len(found.students))
            rows.append([InlineKeyboardButton(text=count, callback_data=cb.students(0))])
            if self._username:
                rows.append([self._button(locale, "links-invite", cb.plain("i"))])
        if self._app:
            rows.append([app_button(self._t, locale, self._app)])
        if not found.students and self._username:  # a label, not a toggle; last on purpose
            rows.append([self._button(locale, "links-invite-first", cb.plain("i"))])
        return Screen("\n\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows))

    async def students(self, principal: Principal, page: int) -> Screen:
        locale = principal.account.locale
        people = (await self._links.get.execute(principal)).students
        last = max(0, (len(people) - 1) // PAGE)
        page = min(page, last)
        rows = [
            [
                InlineKeyboardButton(
                    text=_name(self._t, locale, p.name), callback_data=cb.person("v", p.id)
                )
            ]
            for p in people[page * PAGE : (page + 1) * PAGE]
        ]
        turn: list[InlineKeyboardButton] = []
        if page > 0:
            turn.append(self._button(locale, "page-prev", cb.students(page - 1)))
        if page < last:
            turn.append(self._button(locale, "page-next", cb.students(page + 1)))
        if turn:
            rows.append(turn)
        rows.append([self._button(locale, "log-back", cb.plain("o"))])
        text = (
            self._t.t(locale, "links-students", count=len(people))
            if people
            else self._t.t(locale, "links-no-students")
        )
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def teacher(self, principal: Principal, id: UUID) -> Screen:
        locale = principal.account.locale
        found = await self._links.get.execute(principal)
        teacher = _find(found.teachers, id)
        if teacher is None:  # removed meanwhile, or a forged id
            return await self.overview(principal)
        rows: list[list[InlineKeyboardButton]] = []
        if len(found.teachers) >= 2 and effective_primary(found.teachers) != id:
            rows.append([self._button(locale, "links-make-main", cb.person("p", id))])
        rows.append([self._button(locale, "links-remove", cb.person("u", id))])
        rows.append([self._button(locale, "log-back", cb.plain("o"))])
        return Screen(
            _name(self._t, locale, teacher.name), InlineKeyboardMarkup(inline_keyboard=rows)
        )

    async def ask_remove_teacher(self, principal: Principal, id: UUID) -> Screen:
        locale = principal.account.locale
        found = await self._links.get.execute(principal)
        teacher = _find(found.teachers, id)
        if teacher is None:
            return await self.overview(principal)
        parts = [self._t.t(locale, "link-unlink-ask", name=_name(self._t, locale, teacher.name))]
        heir = next_primary(found.teachers, id)
        taking_over = _find(found.teachers, heir) if heir else None
        if taking_over is not None:
            name = _name(self._t, locale, taking_over.name)
            parts.append(self._t.t(locale, "link-next-main", name=name))
        rows = [
            [self._button(locale, "links-remove-yes", cb.person("x", id))],
            [self._button(locale, "log-back", cb.person("c", id))],
        ]
        return Screen("\n\n".join(parts), InlineKeyboardMarkup(inline_keyboard=rows))

    async def student(self, principal: Principal, id: UUID) -> Screen:
        locale = principal.account.locale
        student = _find((await self._links.get.execute(principal)).students, id)
        if student is None:
            return await self.students(principal, 0)
        rows = [
            [self._button(locale, "links-remove", cb.person("r", id))],
            [self._button(locale, "log-back", cb.students(0))],
        ]
        return Screen(
            _name(self._t, locale, student.name), InlineKeyboardMarkup(inline_keyboard=rows)
        )

    async def ask_remove_student(self, principal: Principal, id: UUID) -> Screen:
        locale = principal.account.locale
        student = _find((await self._links.get.execute(principal)).students, id)
        if student is None:
            return await self.students(principal, 0)
        rows = [
            [self._button(locale, "links-remove-yes", cb.person("z", id))],
            [self._button(locale, "log-back", cb.person("v", id))],
        ]
        text = self._t.t(locale, "link-remove-ask", name=_name(self._t, locale, student.name))
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def make_main(self, principal: Principal, id: UUID) -> Screen:
        with suppress(NotLinked, LinksChanged):  # the list below shows what is true now
            await self._links.primary.execute(principal, id)
        return await self.overview(principal)

    async def remove_teacher(self, principal: Principal, id: UUID) -> Screen:
        await self._links.remove_teacher.execute(principal, id)
        return await self.overview(principal)

    async def remove_student(self, principal: Principal, id: UUID) -> Screen:
        await self._links.remove_student.execute(principal, id)
        return await self.students(principal, 0)

    async def invite(self, principal: Principal, rotate: bool = False) -> Screen:
        locale = principal.account.locale
        if not self._username:  # dev without a bot name: there's no link to show
            return await self.overview(principal)
        get = self._links.rotate if rotate else self._links.invite
        url = invite_url(self._username, await get.execute(principal))
        query = urlencode(
            {"url": url, "text": self._t.t(locale, "invite-share-text")}, quote_via=quote
        )
        rows = [
            [
                InlineKeyboardButton(
                    text=self._t.t(locale, "invite-share"),
                    url=f"https://t.me/share/url?{query}",
                )
            ],
            [self._button(locale, "invite-qr", cb.plain("q"))],
            [self._button(locale, "invite-new", cb.plain("w"))],
            [self._button(locale, "log-back", cb.plain("o"))],
        ]
        text = f"{url}\n\n{self._t.t(locale, 'invite-hint')}"
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def ask_new_link(self, principal: Principal) -> Screen:
        locale = principal.account.locale
        rows = [
            [self._button(locale, "invite-new-yes", cb.plain("wy"))],
            [self._button(locale, "log-back", cb.plain("i"))],
        ]
        return Screen(
            self._t.t(locale, "invite-new-ask"), InlineKeyboardMarkup(inline_keyboard=rows)
        )

    async def qr(self, principal: Principal) -> tuple[bytes, str] | None:
        """The PNG and its caption, or None when there is no bot name to link to."""
        if not self._username:
            return None
        code = await self._links.invite.execute(principal)
        png = self._links.qr.png(invite_url(self._username, code))
        return png, self._t.t(principal.account.locale, "invite-qr-caption")

    def work(
        self, tap: cb.LinkTap, principal: Principal, callback: CallbackQuery
    ) -> Awaitable[Screen]:
        match tap:
            case cb.Confirm(code):
                return self.accept(principal, code)
            case cb.Language(locale, code):
                client = client_profile(callback.from_user)
                return self.language(principal, locale, code, client)
            case cb.Students(page):
                return self.students(principal, page)
            case cb.OnPerson("c", id):
                return self.teacher(principal, id)
            case cb.OnPerson("p", id):
                return self.make_main(principal, id)
            case cb.OnPerson("u", id):
                return self.ask_remove_teacher(principal, id)
            case cb.OnPerson("x", id):
                return self.remove_teacher(principal, id)
            case cb.OnPerson("v", id):
                return self.student(principal, id)
            case cb.OnPerson("r", id):
                return self.ask_remove_student(principal, id)
            case cb.OnPerson("z", id):
                return self.remove_student(principal, id)
            case cb.Tap("n"):
                return self._start.start(principal)  # stores nothing, tells no one
            case cb.Tap("i"):
                return self.invite(principal)
            case cb.Tap("w"):
                return self.ask_new_link(principal)
            case cb.Tap("wy"):
                return self.invite(principal, rotate=True)
            case _:
                return self.overview(principal)


def register_links(router: Router, screens: LinkScreens) -> None:
    @router.message(Command("teachers"))
    async def on_teachers(message: Message, account: Account) -> SendMessage:  # pyright: ignore[reportUnusedFunction]
        screen = await screens.overview(Principal(account))
        return message.answer(screen.text, reply_markup=screen.markup)

    @router.callback_query(F.data.startswith(f"{cb.PREFIX}:"))
    async def on_link(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        tap = cb.decode(callback.data)
        if tap is None:
            await answered(callback, nothing())
            return None
        principal = Principal(account)
        if tap == cb.Tap("q"):
            qr = await answered(callback, screens.qr(principal))
            if qr is not None and callback.bot is not None:
                png, caption = qr  # a file can't be a webhook reply (ADR-0012)
                await callback.bot.send_photo(
                    chat_id=callback.from_user.id,  # private chats only: also the chat's id
                    photo=BufferedInputFile(png, QR_FILE),
                    caption=caption,
                    request_timeout=QR_TIMEOUT_S,
                )
            return None
        screen = await answered(callback, screens.work(tap, principal, callback))
        return show(callback, screen)
