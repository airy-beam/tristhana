"""Shalas in the bot (SC-01, ADR-0033): the consent screens on `/start h_<code>` (students) and
`/start hs_<code>` (staff), the card, the students list, links, remove and leave. Creating,
editing, roles and deleting are in the Mini App (Q103). Codes ride in the callback and are
never logged. A preview names no one but the inviter of a staff link; students never see
other students.
"""

import asyncio
from collections.abc import Awaitable
from datetime import date
from typing import TYPE_CHECKING
from urllib.parse import quote, urlencode
from uuid import UUID

from aiogram import F, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from tristhana.application.policies import (
    NotAllowed,
    NotFound,
    Principal,
    can_announce_to_shala,
    can_edit_shala,
    can_remove_staff,
    can_remove_student,
    can_show_join_link,
    can_view_shala_students,
)
from tristhana.application.ports.i18n import Translator
from tristhana.application.ports.shalas import CapReached, ShalaCard
from tristhana.application.settings import caller_today
from tristhana.application.shalas import ShalaUseCases
from tristhana.bots.telegram import classes_callbacks as classes_cb
from tristhana.bots.telegram import moon_callbacks
from tristhana.bots.telegram import shalas_callbacks as cb
from tristhana.bots.telegram.runtime import SettingsUseCases
from tristhana.bots.telegram.screens import Reply, Screen, answered, nothing, show, zone_label
from tristhana.bots.telegram.settings import client_profile
from tristhana.domain.accounts import Account, ExternalProfile, ProfilePatch
from tristhana.domain.announcements import Source, SourceKind
from tristhana.domain.locale import LOCALES, Locale
from tristhana.domain.moon import City, MoonFollow, MoonSource
from tristhana.domain.shalas import (
    JoinState,
    Membership,
    ShalaInvite,
    ShalaRole,
    grantable,
    shala_join_url,
    staff_invite_url,
)
from tristhana.domain.teacher_links import shown_name

if TYPE_CHECKING:
    from tristhana.bots.telegram.start import StartScreens
    from tristhana.bots.telegram.teacher_links import LinkScreens

PAGE = 10
QR_FILE = "tristhana-shala.png"
QR_TIMEOUT_S = 10
_ROLE_ORDER = (ShalaRole.TEACHER, ShalaRole.ASSISTANT, ShalaRole.OFFICE, ShalaRole.ADMIN)


def can_remove_staff_of(card: ShalaCard, target: UUID) -> bool:
    staff = next((s for s in card.staff if s.id == target), None)
    if staff is None:
        return False
    them = Membership(card.id, staff.owner, staff.roles, False)
    return can_remove_staff(card.me, them, own=False)


class ShalaScreens:
    def __init__(
        self,
        shalas: ShalaUseCases,
        start: "StartScreens",
        links: "LinkScreens",
        settings: SettingsUseCases,
        translator: Translator,
        bot_username: str,
    ) -> None:
        self._h = shalas
        self._start = start
        self._links = links
        self._s = settings
        self._t = translator
        self._cities = shalas.cities
        self._clock = shalas.clock
        self._username = bot_username

    def _name(self, locale: Locale, name: str | None) -> str:
        return shown_name(name) or self._t.t(locale, "link-no-name")

    def _button(self, locale: Locale, key: str, data: str, **args: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=self._t.t(locale, key, **args), callback_data=data)

    def _city(self, locale: Locale, slug: str) -> str:
        city = self._cities.find(slug)
        return city.name(locale) if city else slug

    def _role(self, locale: Locale, role: ShalaRole) -> str:
        return self._t.t(locale, "shala-role", role=role.value)

    def _me(self, account: Account) -> str:
        own = shown_name(account.display_name)
        return f" ({own})" if own else ""

    def _other(self, locale: Locale) -> Locale:
        return next(c for c in LOCALES if c != locale)  # type: ignore[return-value]  # two languages today

    # Joining

    async def invited(self, principal: Principal, invite: ShalaInvite) -> Screen:
        """`/start h_<code>` / `hs_<code>`: the consent, or the grid with one line on top."""
        account = principal.account
        locale = account.locale
        found = await self._h.preview.execute(principal, invite)
        if found is None:
            return await self._start.start(principal, self._t.t(locale, "shala-invalid"))
        match found.state:
            case JoinState.ALREADY:
                lead = self._t.t(locale, "shala-already", shala=found.name)
                return await self._start.start(principal, lead)
            case JoinState.STAFF:
                lead = self._t.t(locale, "shala-already-staff", shala=found.name)
                return await self._start.start(principal, lead)
            case JoinState.FULL:
                return await self._start.start(principal, self._t.t(locale, "shala-full"))
            case JoinState.OPEN:
                pass
        city = self._city(locale, found.city)
        if found.staff and found.role is not None:
            ask = self._t.t(
                locale,
                "shala-staff-ask",
                name=self._name(locale, found.inviter_name),
                shala=found.name,
                role=self._role(locale, found.role),
            )
            consent = self._t.t(locale, "shala-staff-consent", me=self._me(account))
            rows = [
                [
                    self._button(locale, "shala-staff-yes", cb.accept_staff(invite.code)),
                    self._button(locale, "invite-decline", cb.not_now()),
                ]
            ]
        else:
            ask = self._t.t(locale, "shala-join-ask", shala=found.name, city=city)
            consent = self._t.t(locale, "shala-join-consent", me=self._me(account))
            other = self._other(locale)
            switch = self._t.t(
                locale, "start-switch-language", language=self._t.t(other, f"language-{other}")
            )
            rows = [
                [
                    self._button(locale, "shala-join-yes", cb.join(invite.code)),
                    self._button(locale, "invite-decline", cb.not_now()),
                ],
                [InlineKeyboardButton(text=switch, callback_data=cb.language(other, invite.code))],
            ]
        text = "\n\n".join([ask, consent, self._t.t(locale, "shala-know-them")])
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def language(
        self, principal: Principal, locale: Locale, code: str, client: ExternalProfile
    ) -> Screen:
        account = await self._s.profile.execute(principal, ProfilePatch(locale=locale), client)
        return await self.invited(Principal(account), ShalaInvite(code, False))

    async def join(self, principal: Principal, code: str) -> Screen:
        locale = principal.account.locale
        joined = await self._h.join.execute(principal, code)
        if joined is None:  # rotated since the consent screen
            return await self._start.start(principal, self._t.t(locale, "shala-invalid"))
        if joined.card is None:
            return await self._start.start(principal, self._t.t(locale, "shala-full"))
        return self._card(principal, joined.card, self._moved(locale, joined.moon))

    async def accept_staff(self, principal: Principal, code: str) -> Screen:
        locale = principal.account.locale
        accepted = await self._h.accept_staff.execute(principal, code)
        if accepted is None:  # used or expired
            return await self._start.start(principal, self._t.t(locale, "shala-invalid"))
        if accepted.card is None:
            return await self._start.start(principal, self._t.t(locale, "shala-full"))
        screen = self._card(principal, accepted.card, self._moved(locale, accepted.moon))
        if accepted.keep is None:
            return screen
        return self._with_keep(locale, screen, accepted.keep)

    def _with_keep(self, locale: Locale, screen: Screen, keep: City) -> Screen:
        """Q98: a never-chose teacher's students don't inherit the shala city (one hop)."""
        city = keep.name(locale)
        data = moon_callbacks.encode(moon_callbacks.MoonCallback("keep", slug=keep.slug))
        row = [
            InlineKeyboardButton(
                text=self._t.t(locale, "moon-keep-city", city=city), callback_data=data
            )
        ]
        markup = InlineKeyboardMarkup(inline_keyboard=[row, *screen.markup.inline_keyboard])
        return Screen(screen.text, markup)

    def _moved(self, locale: Locale, moon: MoonFollow | None) -> str | None:
        if moon is None:
            return None
        city = moon.city.name(locale)
        if moon.source is MoonSource.SHALA and moon.shala is not None:
            return self._t.t(locale, "settings-moon-line-shala", city=city, shala=moon.shala.name)
        return self._t.t(locale, "settings-moon-line", city=city)

    # The card

    def _card(
        self,
        principal: Principal,
        card: ShalaCard,
        note: str | None = None,
        pin: str | None = None,
    ) -> Screen:
        locale = principal.account.locale
        today: date = caller_today(principal, self._clock)
        city = self._cities.find(card.city)
        zone = zone_label(self._t, locale, city.location.tz, today, city) if city else card.city
        place = (
            self._t.t(locale, "shala-online")
            if card.online
            else self._t.t(locale, "shala-place", city=self._city(locale, card.city))
        )
        people = " · ".join(
            f"{self._name(locale, s.name)} ({', '.join(self._roles_of(locale, s.owner, s.roles))})"
            if s.owner or s.roles
            else self._name(locale, s.name)
            for s in card.staff
        )
        lines = [f"🏛 {card.name}", self._t.t(locale, "shala-time", place=place, zone=zone)]
        # A moon city since removed from the list falls back to the shala's own city (Q111).
        moon = self._cities.find(card.moon_city or card.city) or self._cities.find(card.city)
        if moon is not None:
            lines.append(self._t.t(locale, "shala-moon-line", city=moon.name(locale)))
        lines.append(self._t.t(locale, "shala-staff-title", people=people))
        days_off = self._days_off(locale, card.days_off)
        if days_off is not None:
            lines.append(self._t.t(locale, "shala-day-off-line", days=days_off))
        me = card.me
        if can_edit_shala(me):
            lines.append(self._t.t(locale, "shala-moon-shared"))
        text = "\n".join(lines)
        if pin:  # NT-03: the live pin
            text = f"{text}\n\n{pin}"
        if note:
            text = f"{text}\n\n{note}"
        rows: list[list[InlineKeyboardButton]] = []
        ann = self._links.announcements
        if ann is not None:  # NT-03
            rows.append([ann.card_button(locale, Source(SourceKind.SHALA, card.id))])
            announce = self._links.announce_button(locale, card.id)
            if announce is not None and can_announce_to_shala(me):
                rows.append([announce])
        if self._h.classes is not None:  # SC-02
            rows.append([self._button(locale, "schedule-open", classes_cb.week(card.id, 0))])
            if days_off is not None and principal.account.day_off.days is None:  # Q119
                adopt = classes_cb.adopt_day_off(card.id)
                rows.append([self._button(locale, "shala-day-off-adopt", adopt, days=days_off)])
        if can_view_shala_students(me) and card.students_total is not None:
            rows.append(
                [
                    self._button(
                        locale,
                        "shala-students",
                        cb.students(card.id, 0),
                        n=card.students_total,  # type: ignore[arg-type]
                    )
                ]
            )
        if can_show_join_link(me) and self._username:
            rows.append([self._button(locale, "shala-invite-students", cb.on_shala("i", card.id))])
        if grantable(me) and self._username:
            rows.append([self._button(locale, "shala-invite-staff", cb.on_shala("e", card.id))])
        if not me.owner:
            rows.append([self._button(locale, "shala-leave", cb.on_shala("k", card.id))])
        rows.append([self._button(locale, "log-back", "t1:o")])
        # A pin is the author's text: no preview for a URL in it (NT-03).
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows), no_preview=bool(pin))

    def _days_off(self, locale: Locale, days: frozenset[int] | None) -> str | None:
        if not days:
            return None
        return ", ".join(self._t.t(locale, "day-off-weekday", d=d) for d in sorted(days))

    def _roles_of(self, locale: Locale, owner: bool, roles: frozenset[ShalaRole]) -> list[str]:
        names = ["owner"] if owner else []
        names += [r.value for r in _ROLE_ORDER if r in roles]
        return [self._t.t(locale, "shala-role-in-list", role=n) for n in names]

    async def card(self, principal: Principal, shala: UUID, note: str | None = None) -> Screen:
        ann = self._links.announcements
        try:
            if ann is None:
                found, pin = await self._h.get.execute(principal, shala), None
            else:  # NT-03: the live pin loads alongside the card
                found, pin = await asyncio.gather(
                    self._h.get.execute(principal, shala),
                    ann.pin_line(principal, Source(SourceKind.SHALA, shala)),
                )
        except NotFound:  # gone, left, or a forged id
            return await self._links.overview(principal)
        return self._card(principal, found, note, pin)

    # Students (staff only)

    async def students(self, principal: Principal, shala: UUID, page: int) -> Screen:
        locale = principal.account.locale
        try:
            found = await self._h.students.execute(principal, shala, page * PAGE, PAGE)
            if not found.students and page > 0:
                page = 0
                found = await self._h.students.execute(principal, shala, 0, PAGE)
        except NotFound:
            return await self._links.overview(principal)
        except NotAllowed:
            return await self.card(principal, shala)
        removes = found.me is not None and can_remove_student(found.me, own=False)
        rows = [
            [
                InlineKeyboardButton(
                    text=self._name(locale, s.name),
                    callback_data=cb.on_member("u", shala, s.id),
                )
            ]
            for s in (found.students if removes else ())
        ]
        last = max(0, (found.total - 1) // PAGE)
        turn: list[InlineKeyboardButton] = []
        if page > 0:
            turn.append(self._button(locale, "page-prev", cb.students(shala, page - 1)))
        if page < last:
            turn.append(self._button(locale, "page-next", cb.students(shala, page + 1)))
        if turn:
            rows.append(turn)
        rows.append([self._button(locale, "log-back", cb.on_shala("c", shala))])
        if not found.students:
            text = self._t.t(locale, "shala-no-students")
        else:
            text = self._t.t(locale, "shala-students", n=found.total)  # type: ignore[arg-type]
            if not removes:  # names only: nothing to tap
                text = "\n".join([text, *(self._name(locale, s.name) for s in found.students)])
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def ask_remove(self, principal: Principal, shala: UUID, target: UUID) -> Screen:
        locale = principal.account.locale
        try:
            found = await self._h.member.execute(principal, shala, target)
        except NotFound:
            return await self._links.overview(principal)
        card = found.card
        if not found.found or target == principal.account.id:
            return self._card(principal, card)
        allowed = (
            can_remove_staff_of(card, target)
            if found.staff
            else can_remove_student(card.me, own=False)
        )
        if not allowed:
            return self._card(principal, card)
        back = cb.on_shala("c", shala) if found.staff else cb.students(shala, 0)
        rows = [
            [self._button(locale, "shala-remove-yes", cb.on_member("x", shala, target))],
            [self._button(locale, "log-back", back)],
        ]
        text = self._t.t(locale, "shala-remove-ask", name=self._name(locale, found.name))
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def remove(self, principal: Principal, shala: UUID, target: UUID) -> Screen:
        try:
            found = await self._h.member.execute(principal, shala, target)
            if found.staff:
                await self._h.remove_staff.execute(principal, shala, target)
            else:
                await self._h.remove_student.execute(principal, shala, target)
        except NotFound:
            return await self._links.overview(principal)
        except NotAllowed:
            return await self.card(principal, shala)
        return await self.students(principal, shala, 0)

    # Leaving

    async def ask_leave(self, principal: Principal, shala: UUID) -> Screen:
        locale = principal.account.locale
        try:
            card = await self._h.get.execute(principal, shala)
        except NotFound:
            return await self._links.overview(principal)
        if card.me.owner:  # Q102: the owner can't leave
            return self._card(principal, card)
        rows = [
            [self._button(locale, "shala-leave-yes", cb.on_shala("ky", shala))],
            [self._button(locale, "log-back", cb.on_shala("c", shala))],
        ]
        text = self._t.t(locale, "shala-leave-ask", shala=card.name)
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def leave(self, principal: Principal, shala: UUID) -> Screen:
        me = principal.account.id
        try:
            card = await self._h.get.execute(principal, shala)
            if card.me.student:
                await self._h.remove_student.execute(principal, shala, me)
            else:
                await self._h.remove_staff.execute(principal, shala, me)
        except NotFound:
            pass
        except NotAllowed:
            return await self.card(principal, shala)
        return await self._links.overview(principal)

    # Links

    def _share(self, locale: Locale, url: str, shala: str) -> InlineKeyboardButton:
        query = urlencode(
            {"url": url, "text": self._t.t(locale, "shala-share-text", shala=shala)},
            quote_via=quote,
        )
        return InlineKeyboardButton(
            text=self._t.t(locale, "invite-share"), url=f"https://t.me/share/url?{query}"
        )

    async def join_link(self, principal: Principal, shala: UUID, rotate: bool = False) -> Screen:
        locale = principal.account.locale
        if not self._username:
            return await self.card(principal, shala)
        try:
            card = await self._h.get.execute(principal, shala)
            get = self._h.rotate if rotate else self._h.join_link
            code = await get.execute(principal, shala)
        except NotFound:
            return await self._links.overview(principal)
        except NotAllowed:
            return await self.card(principal, shala)
        url = shala_join_url(self._username, code)
        rows = [
            [self._share(locale, url, card.name)],
            [self._button(locale, "invite-qr", cb.on_shala("q", shala))],
        ]
        if can_edit_shala(card.me):
            rows.append([self._button(locale, "invite-new", cb.on_shala("w", shala))])
        rows.append([self._button(locale, "log-back", cb.on_shala("c", shala))])
        text = "\n\n".join((url, self._t.t(locale, "shala-join-hint")))
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def ask_new_link(self, principal: Principal, shala: UUID) -> Screen:
        locale = principal.account.locale
        try:
            card = await self._h.get.execute(principal, shala)
        except NotFound:
            return await self._links.overview(principal)
        if not can_edit_shala(card.me):
            return self._card(principal, card)
        rows = [
            [self._button(locale, "invite-new-yes", cb.on_shala("wy", shala))],
            [self._button(locale, "log-back", cb.on_shala("i", shala))],
        ]
        return Screen(
            self._t.t(locale, "invite-new-ask"), InlineKeyboardMarkup(inline_keyboard=rows)
        )

    async def qr(self, principal: Principal, shala: UUID) -> tuple[bytes, str] | None:
        if not self._username:
            return None
        try:
            card = await self._h.get.execute(principal, shala)
            code = await self._h.join_link.execute(principal, shala)
        except (NotFound, NotAllowed):
            return None
        png = self._links.qr_png(shala_join_url(self._username, code))
        return png, self._t.t(principal.account.locale, "shala-qr-caption", shala=card.name)

    async def pick_role(self, principal: Principal, shala: UUID) -> Screen:
        locale = principal.account.locale
        try:
            card = await self._h.get.execute(principal, shala)
        except NotFound:
            return await self._links.overview(principal)
        allowed = grantable(card.me)
        if not allowed or not self._username:
            return self._card(principal, card)
        rows = [
            [
                InlineKeyboardButton(
                    text=self._role(locale, role), callback_data=cb.staff_link(shala, role)
                )
            ]
            for role in _ROLE_ORDER
            if role in allowed
        ]
        rows.append([self._button(locale, "log-back", cb.on_shala("c", shala))])
        return Screen(
            self._t.t(locale, "shala-staff-pick"), InlineKeyboardMarkup(inline_keyboard=rows)
        )

    async def staff_link(self, principal: Principal, shala: UUID, role: ShalaRole) -> Screen:
        locale = principal.account.locale
        if not self._username:
            return await self.card(principal, shala)
        try:
            card = await self._h.get.execute(principal, shala)
            invite = await self._h.invite_staff.execute(principal, shala, role)
        except NotFound:
            return await self._links.overview(principal)
        except NotAllowed:
            return await self.card(principal, shala)
        except CapReached:
            return await self.card(principal, shala, self._t.t(locale, "shala-caps"))
        url = staff_invite_url(self._username, invite.code)
        rows = [
            [self._share(locale, url, card.name)],
            [self._button(locale, "log-back", cb.on_shala("c", shala))],
        ]
        hint = self._t.t(locale, "shala-staff-link-hint", role=self._role(locale, role))
        return Screen(f"{url}\n\n{hint}", InlineKeyboardMarkup(inline_keyboard=rows))

    # Dispatch

    def work(
        self, tap: cb.ShalaTap, principal: Principal, callback: CallbackQuery
    ) -> Awaitable[Screen]:
        match tap:
            case cb.Join(code):
                return self.join(principal, code)
            case cb.AcceptStaff(code):
                return self.accept_staff(principal, code)
            case cb.Language(locale, code):
                return self.language(principal, locale, code, client_profile(callback.from_user))
            case cb.NotNow():
                return self._start.start(principal)  # stores nothing, tells no one
            case cb.Students(shala, page):
                return self.students(principal, shala, page)
            case cb.StaffLink(shala, role):
                return self.staff_link(principal, shala, role)
            case cb.Member("v" | "u", shala, target):
                return self.ask_remove(principal, shala, target)
            case cb.Member("x", shala, target):
                return self.remove(principal, shala, target)
            case cb.Shala("i", shala):
                return self.join_link(principal, shala)
            case cb.Shala("w", shala):
                return self.ask_new_link(principal, shala)
            case cb.Shala("wy", shala):
                return self.join_link(principal, shala, rotate=True)
            case cb.Shala("e", shala):
                return self.pick_role(principal, shala)
            case cb.Shala("k", shala):
                return self.ask_leave(principal, shala)
            case cb.Shala("ky", shala):
                return self.leave(principal, shala)
            case cb.Shala(_, shala):
                return self.card(principal, shala)
            case _:
                return self._links.overview(principal)


def register_shalas(router: Router, screens: ShalaScreens) -> None:
    @router.callback_query(F.data.startswith(f"{cb.PREFIX}:"))
    async def on_shala(callback: CallbackQuery, account: Account) -> Reply | None:  # pyright: ignore[reportUnusedFunction]
        tap = cb.decode(callback.data)
        if tap is None:
            await answered(callback, nothing())
            return None
        principal = Principal(account)
        if isinstance(tap, cb.Shala) and tap.action == "q":
            qr = await answered(callback, screens.qr(principal, tap.id))
            if qr is not None and callback.bot is not None:
                png, caption = qr  # a file can't be a webhook reply (ADR-0012)
                await callback.bot.send_photo(
                    chat_id=callback.from_user.id,
                    photo=BufferedInputFile(png, QR_FILE),
                    caption=caption,
                    request_timeout=QR_TIMEOUT_S,
                )
            return None
        screen = await answered(callback, screens.work(tap, principal, callback))
        return show(callback, screen)
