"""Shalas in the bot (SC-01, ADR-0033): the consent on `/start h_<code>` (students) and
`/start hs_<code>` (staff), each a short screen with the full text one tap away (ADR-0045);
the card, the students list, links, remove and leave. Creating,
editing, roles and deleting are in the Mini App (Q103). Codes ride in the callback and are
never logged. A preview names no one but the inviter of a staff link; students never see
other students.
"""

import asyncio
import logging
from collections.abc import Awaitable, Sequence
from datetime import date
from typing import TYPE_CHECKING, Literal
from urllib.parse import quote, urlencode
from uuid import UUID

from aiogram import F, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from tristhana.application.classes import current_of, shala_today, type_name
from tristhana.application.policies import (
    NotAllowed,
    NotFound,
    Principal,
    can_announce_to_shala,
    can_be_asked_as_teacher,
    can_edit_shala,
    can_manage_schedule,
    can_remove_staff,
    can_remove_student,
    can_show_join_link,
    can_view_shala_students,
)
from tristhana.application.ports.classes import StoredClass
from tristhana.application.ports.i18n import DateArg, Translator
from tristhana.application.ports.shalas import CapReached, ShalaCard
from tristhana.application.ports.teacher_requests import CardRequests, Choices
from tristhana.application.settings import caller_today
from tristhana.application.shalas import ShalaUseCases
from tristhana.bots.telegram import classes_callbacks as classes_cb
from tristhana.bots.telegram import moon_callbacks
from tristhana.bots.telegram import shalas_callbacks as cb
from tristhana.bots.telegram import teacher_links_callbacks as links_cb
from tristhana.bots.telegram.runtime import SettingsUseCases
from tristhana.bots.telegram.screens import (
    Reply,
    Screen,
    answered,
    app_button,
    app_url,
    nothing,
    show,
    zone_label,
)
from tristhana.bots.telegram.settings import client_profile
from tristhana.bots.telegram.teacher_requests import waiting_row
from tristhana.domain.accounts import Account, ExternalProfile, ProfilePatch
from tristhana.domain.announcements import Source, SourceKind
from tristhana.domain.classes import day_runs
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
from tristhana.domain.time_label import canonical_zone

if TYPE_CHECKING:
    from tristhana.bots.telegram.start import StartScreens
    from tristhana.bots.telegram.teacher_links import LinkScreens

PAGE = 10
CLASS_LINES = 12  # the Classes block on the card, then "…" (the rest is in the app)
CARD_ROWS = 7  # Q373 (a): more action rows than this, and the card keeps its main ones + More…
type Place = Literal["main", "more", "passing"]  # where a card row goes (`_actions`)
MAIN: Place = "main"
MORE: Place = "more"
PASSING: Place = "passing"
DASH = "\u2013"  # en dash: Mon-Fri, 06:00-09:30
QR_FILE = "tristhana-shala.png"
QR_TIMEOUT_S = 10
MINUTES_PER_DAY = 24 * 60
_ROLE_ORDER = (ShalaRole.TEACHER, ShalaRole.ASSISTANT, ShalaRole.OFFICE, ShalaRole.ADMIN)

log = logging.getLogger(__name__)


async def _given[T](value: T) -> T:
    """A value already in hand, for a slot of `asyncio.gather`."""
    return value


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
        app: str = "",
    ) -> None:
        self._h = shalas
        self._start = start
        self._links = links
        self._s = settings
        self._t = translator
        self._cities = shalas.cities
        self._clock = shalas.clock
        self._username = bot_username
        self._app = app  # the Mini App's address: the card's buttons into it (UI-06 stage 6)

    def _app_button(self, locale: Locale, key: str, url: str) -> InlineKeyboardButton:
        return app_button(self._t, locale, key, url)

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

    async def invited(
        self, principal: Principal, invite: ShalaInvite, details: bool = False
    ) -> Screen:
        """`/start h_<code>` / `hs_<code>`: the short consent (`details`: the full text), or
        Today with one line on top. The full text is the consent record, and the confirm
        button is the same on both screens (ADR-0045). Every render re-reads the invite."""
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
        role = found.role if found.staff else None
        if role is not None:
            ask = self._t.t(
                locale,
                "shala-staff-ask",
                name=self._name(locale, found.inviter_name),
                shala=found.name,
                role=self._role(locale, role),
            )
            full, short = "shala-staff-consent", "shala-staff-consent-short"
            yes = self._button(locale, "shala-staff-yes", cb.accept_staff(invite.code))
        else:
            city = self._city(locale, found.city)
            ask = self._t.t(locale, "shala-join-ask", shala=found.name, city=city)
            full, short = "shala-join-consent", "shala-join-consent-short"
            yes = self._button(locale, "shala-join-yes", cb.join(invite.code))
        consent = self._t.t(locale, full if details else short, me=self._me(account))
        rows = [[yes, self._button(locale, "invite-decline", cb.not_now())]]
        if details:  # the layer switch re-reads the same kind of link
            back = cb.consent(invite.code, invite.staff, details=False)
            rows.append([self._button(locale, "consent-short-back", back)])
        else:
            more = cb.consent(invite.code, invite.staff, details=True)
            rows.append([self._button(locale, "consent-details", more)])
            # The staff link's language row has its own letter (UI-06 stage 6, C4): `h1:l`
            # keeps meaning the join consent's.
            other = self._other(locale)
            switch = self._t.t(
                locale, "start-switch-language", language=self._t.t(other, f"language-{other}")
            )
            data = cb.language(other, invite.code, staff=role is not None)
            rows.append([InlineKeyboardButton(text=switch, callback_data=data)])
        text = "\n\n".join([ask, consent, self._t.t(locale, "shala-know-them")])
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def language(
        self,
        principal: Principal,
        locale: Locale,
        code: str,
        client: ExternalProfile,
        staff: bool = False,
    ) -> Screen:
        account = await self._s.profile.execute(principal, ProfilePatch(locale=locale), client)
        return await self.invited(Principal(account), ShalaInvite(code, staff))

    async def join(self, principal: Principal, code: str) -> Screen:
        locale = principal.account.locale
        joined = await self._h.join.execute(principal, code)
        if joined is None:  # rotated since the consent screen
            return await self._start.start(principal, self._t.t(locale, "shala-invalid"))
        if joined.card is None:
            return await self._start.start(principal, self._t.t(locale, "shala-full"))
        note = self._moved(locale, joined.moon)
        requests = self._links.requests
        if requests is None:
            return self._card(principal, joined.card, note)
        # ID-07: with a teacher to ask, the reply is the question instead of the card.
        asked = await requests.choices(principal, joined.card.id)
        if asked is not None and asked.offer:
            return requests.question(principal.account, asked, note=note)
        return self._card(principal, joined.card, note, asked=asked)

    async def accept_staff(self, principal: Principal, code: str) -> Screen:
        locale = principal.account.locale
        accepted = await self._h.accept_staff.execute(principal, code)
        if accepted is None:  # used or expired
            return await self._start.start(principal, self._t.t(locale, "shala-invalid"))
        if accepted.card is None:
            return await self._start.start(principal, self._t.t(locale, "shala-full"))
        welcome = None
        if accepted.created:  # UI-06 stage 6 (C4): where things are, above the card
            welcome = self._t.t(
                locale,
                "shala-staff-welcome",
                shala=accepted.card.name,
                role=self._role(locale, accepted.role),
            )
        screen = self._card(
            principal, accepted.card, self._moved(locale, accepted.moon), lead=welcome
        )
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
            return self._t.t(locale, "shala-moon-yours-shala", city=city, shala=moon.shala.name)
        return self._t.t(locale, "shala-moon-yours", city=city)

    # The card

    def _card(
        self,
        principal: Principal,
        card: ShalaCard,
        note: str | None = None,
        pin: str | None = None,
        asked: Choices | None = None,
        waiting: int = 0,
        classes: Sequence[StoredClass] | None = None,
        lead: str | None = None,
    ) -> Screen:
        """`asked`: the student's requests in this shala (ID-07); `waiting`: how many people
        wait for the caller's answer as a teacher; `classes`: the shala's classes, read for
        those who may manage the schedule (None: not read, or not theirs to read); `lead`: a
        line above the card."""
        locale = principal.account.locale
        today: date = caller_today(principal, self._clock)
        city = self._cities.find(card.city)
        mine = principal.account.timezone
        place = (
            self._t.t(locale, "shala-online")
            if card.online
            else self._t.t(locale, "shala-place", city=self._city(locale, card.city))
        )
        # "Shala time" only where it differs from the viewer's own, with the offset (ADR-0044).
        if city is None or mine is None or canonical_zone(city.location.tz) != canonical_zone(mine):
            zone = (
                zone_label(self._t, locale, city.location.tz, today, city, mine)
                if city
                else card.city
            )
            place = self._t.t(locale, "shala-time", place=place, zone=zone)
        people = " · ".join(
            f"{self._name(locale, s.name)} ({', '.join(self._roles_of(locale, s.owner, s.roles))})"
            if s.owner or s.roles
            else self._name(locale, s.name)
            for s in card.staff
        )
        lines = [f"🏛 {card.name}", place]
        # A moon city since removed from the list falls back to the shala's own city (Q111).
        moon = self._cities.find(card.moon_city or card.city) or self._cities.find(card.city)
        if moon is not None:  # UI-06 stage 6 (C15): one line, the policy included
            policy = self._t.t(locale, "shala-moon-policy-short", p=str(card.moon_policy))
            lines.append(
                self._t.t(locale, "shala-moon-summary", city=moon.name(locale), policy=policy)
            )
        lines.append(self._t.t(locale, "shala-staff-title", people=people))
        days_off = self._days_off(locale, card.days_off)
        if days_off is not None:
            lines.append(self._t.t(locale, "shala-day-off-line", days=days_off))
        me = card.me
        if can_edit_shala(me):
            lines.append(self._t.t(locale, "shala-moon-shared"))
        text = "\n".join(lines)
        # UI-06 stage 6 (spec §3.1): the Classes, read-only; the app's button changes them.
        manages = can_manage_schedule(me)
        current = None
        if manages and classes is not None:
            here = shala_today(self._cities, card.city, self._clock) or today  # the shala's
            current = current_of(classes, here)
            text = f"{text}\n\n{self._classes_block(principal, card, current, here)}"
        requests = self._links.requests
        asking: list[list[InlineKeyboardButton]] = []
        if requests is not None and asked is not None:  # ID-07: who I wait for, and Withdraw
            waiting_lines, asking = requests.card_parts(locale, asked)
            if waiting_lines:
                text = "\n\n".join([text, "\n".join(waiting_lines)])
        teachers = any(ShalaRole.TEACHER in s.roles for s in card.staff)
        no_teachers = requests is not None and can_edit_shala(me) and not teachers
        if no_teachers:
            text = f"{text}\n\n{self._t.t(locale, 'request-no-teachers-hint')}"
        if pin:  # NT-03: the live pin
            text = f"{text}\n\n{pin}"
        if note:
            text = f"{text}\n\n{note}"
        if lead:
            text = f"{lead}\n\n{text}"
        rows = self._actions(principal, card, current, waiting, asking, no_teachers)
        # The waiting and day-off rows come and go, so they never flip the card's layout.
        steady = sum(1 for _, place in rows if place != PASSING)
        if steady > CARD_ROWS and sum(1 for _, place in rows if place == MORE) > 1:
            # Q373 (a): the main actions stay; the rest is one tap away behind More…
            more = self._button(locale, "shala-more-button", cb.on_shala("mo", card.id))
            shown = [row for row, place in rows if place != MORE] + [[more]]
        else:
            shown = [row for row, _ in rows]
        shown.append([self._button(locale, "log-back", "t1:o")])
        # A pin is the author's text: no preview for a URL in it (NT-03).
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=shown), no_preview=bool(pin))

    def _actions(
        self,
        principal: Principal,
        card: ShalaCard,
        current: Sequence[StoredClass] | None,
        waiting: int,
        asking: list[list[InlineKeyboardButton]],
        no_teachers: bool,
    ) -> list[tuple[list[InlineKeyboardButton], Place]]:
        """The card's action rows in their order, each with its place (Q373 (a)): MAIN stays
        on the card, MORE goes behind More… on a long card, PASSING stays on the card and is
        not counted, since it comes and goes. Back is not among them."""
        locale = principal.account.locale
        me = card.me
        manages = can_manage_schedule(me)
        days_off = self._days_off(locale, card.days_off)
        rows: list[tuple[list[InlineKeyboardButton], Place]] = []
        if waiting > 0:  # ID-07: people waiting for my answer, in any shala
            rows.append((waiting_row(self._t, locale, waiting), PASSING))
        ann = self._links.announcements
        if ann is not None:  # NT-03
            rows.append(([ann.card_button(locale, Source(SourceKind.SHALA, card.id))], MORE))
            announce = self._links.announce_button(locale, card.id)
            if announce is not None and can_announce_to_shala(me):
                rows.append(([announce], MORE))
        if self._h.classes is not None:  # SC-02
            week = self._button(locale, "schedule-open", classes_cb.week(card.id, 0))
            rows.append(([week], MAIN))
            if manages and self._app:  # UI-06 stage 6 (B1): the forms are in the app
                none = not current if current is not None else card.classes_total == 0
                if none:
                    url = app_url(self._app, "class", shala=str(card.id))
                    rows.append(([self._app_button(locale, "schedule-add-class", url)], MAIN))
                else:
                    url = app_url(self._app, "shala", shala=str(card.id))
                    rows.append(([self._app_button(locale, "shala-classes-edit", url)], MAIN))
            if days_off is not None and principal.account.day_off.days is None:  # Q119
                adopt = classes_cb.adopt_day_off(card.id)
                button = self._button(locale, "shala-day-off-adopt", adopt, days=days_off)
                rows.append(([button], PASSING))  # goes once a day off is set
        rows.extend((row, MAIN) for row in asking)
        if can_view_shala_students(me) and card.students_total is not None:
            n = card.students_total
            students = self._button(locale, "shala-students", cb.students(card.id, 0), n=n)  # type: ignore[arg-type]
            rows.append(([students], MAIN))
        if can_show_join_link(me) and self._username:
            invite = self._button(locale, "shala-invite-students", cb.on_shala("i", card.id))
            rows.append(([invite], MAIN))
        if grantable(me) and self._username:
            staff = self._button(locale, "shala-invite-staff", cb.on_shala("e", card.id))
            rows.append(([staff], MORE))
        if self._app:  # UI-06 stage 6 (B1): roles and the shala's own form are in the app
            if no_teachers:  # the no-teachers hint's own button stays under the hint
                url = app_url(self._app, "shala", shala=str(card.id))
                rows.append(([self._app_button(locale, "app-open-shala", url)], MAIN))
            if can_edit_shala(me):
                url = app_url(self._app, "edit-shala", shala=str(card.id))
                rows.append(([self._app_button(locale, "shala-edit", url)], MORE))
        if not me.owner:
            rows.append(([self._button(locale, "shala-leave", cb.on_shala("k", card.id))], MORE))
        return rows

    async def more(self, principal: Principal, shala: UUID) -> Screen:
        """`h1:mo` (Q373 (a)): the card's other actions, Back to the card. One read."""
        locale = principal.account.locale
        try:
            card = await self._h.get.execute(principal, shala)
        except NotFound:
            return await self._links.overview(principal)
        teachers = any(ShalaRole.TEACHER in s.roles for s in card.staff)
        no_teachers = self._links.requests is not None and can_edit_shala(card.me) and not teachers
        rows = [
            row
            for row, place in self._actions(principal, card, None, 0, [], no_teachers)
            if place == MORE
        ]
        if not rows:  # nothing more for this seat (a role changed since): the card
            return await self.card(principal, shala)
        rows.append([self._button(locale, "log-back", cb.on_shala("c", shala))])
        return Screen(f"🏛 {card.name}", InlineKeyboardMarkup(inline_keyboard=rows))

    def _classes_block(
        self, principal: Principal, card: ShalaCard, classes: Sequence[StoredClass], today: date
    ) -> str:
        """`Classes` and one line per class as the app's list shows it ("Mysore · Mon-Fri ·
        06:00-09:30 · Anna"), at most CLASS_LINES; or "No classes yet."""
        locale = principal.account.locale
        title = self._t.t(locale, "shala-classes-title")
        if not classes:
            return f"{title}\n{self._t.t(locale, 'shala-classes-none')}"
        shown = [self._class_line(principal, card, c, today) for c in classes[:CLASS_LINES]]
        if len(classes) > CLASS_LINES:
            shown.append("…")
        return "\n".join([title, *shown])

    def _class_line(
        self, principal: Principal, card: ShalaCard, c: StoredClass, today: date
    ) -> str:
        """The Mini App's row (`ShalaClasses.tsx`) on one line: the class, its days and times,
        then, " · " between: the teacher, every N weeks, a first date still to come, a last
        date, 🌐 (with the zone it is timed in when that is another city's, ADR-0044)."""
        locale = principal.account.locale
        name = type_name(self._t, locale, c.type)
        weekly = bool(c.weekdays)
        if not weekly:
            days = self._t.t(locale, "day-label", rel="other", date=DateArg(c.starts_on))
        elif (runs := day_runs(c.weekdays)) == ((1, 7),):
            days = self._t.t(locale, "shala-class-every-day")
        else:

            def day(d: int) -> str:
                return self._t.t(locale, "remind-weekday", d=d)

            days = ", ".join(day(a) if a == b else f"{day(a)}{DASH}{day(b)}" for a, b in runs)
        ends = (c.start.hour * 60 + c.start.minute + c.minutes) % MINUTES_PER_DAY
        parts = [
            self._t.t(
                locale,
                "shala-class-row",
                **{"class": f"{name} {c.title}" if c.title else name},
                days=days,
                start=f"{c.start:%H:%M}",
                end=f"{ends // 60:02d}:{ends % 60:02d}",
            )
        ]
        teacher = next((s for s in card.staff if s.id == c.teacher_id), None)
        if teacher is not None:
            parts.append(self._name(locale, teacher.name))
        if weekly and c.every > 1:
            parts.append(self._t.t(locale, "class-form-every-n", n=c.every))
        if weekly and c.starts_on > today:
            parts.append(self._t.t(locale, "class-form-sum-from", date=DateArg(c.starts_on)))
        if weekly and c.ends_on is not None:
            parts.append(self._t.t(locale, "class-form-sum-end", date=DateArg(c.ends_on)))
        if c.online:
            runs_in = self._cities.find(c.city) if c.city else None
            if runs_in is None:
                parts.append("🌐")
            else:
                zone = runs_in.location.tz
                viewer = principal.account.timezone
                parts.append(f"🌐 {zone_label(self._t, locale, zone, today, runs_in, viewer)}")
        return " · ".join(parts)

    def _days_off(self, locale: Locale, days: frozenset[int] | None) -> str | None:
        if not days:
            return None
        return ", ".join(self._t.t(locale, "day-off-weekday", d=d) for d in sorted(days))

    def _roles_of(self, locale: Locale, owner: bool, roles: frozenset[ShalaRole]) -> list[str]:
        names = ["owner"] if owner else []
        names += [r.value for r in _ROLE_ORDER if r in roles]
        return [self._t.t(locale, "shala-role-in-list", role=n) for n in names]

    async def card(
        self,
        principal: Principal,
        shala: UUID,
        note: str | None = None,
        asked: Choices | None = None,
    ) -> Screen:
        """`asked`: the caller's requests here, when the tap has just read them."""
        ann = self._links.announcements
        requests = self._links.requests
        try:
            # NT-03's live pin and ID-07's requests load alongside the card. Whether the
            # caller is a student or a teacher here is known only once the card is read, so
            # the requests are one read that serves either side (spec §7: +1, in parallel).
            # So are the Classes (UI-06 stage 6, §3.1: +1, in parallel), whose own guard
            # turns away those who may not manage the schedule.
            found, pin, side, classes = await asyncio.gather(
                self._h.get.execute(principal, shala),
                _given(None)
                if ann is None
                else ann.pin_line(principal, Source(SourceKind.SHALA, shala)),
                _given(CardRequests(asked))
                if requests is None or asked is not None
                else requests.beside_card(principal, shala),
                self._classes_of(principal, shala),
            )
        except NotFound:  # gone, left, or a forged id
            return await self._links.overview(principal)
        return self._card(principal, found, note, pin, side.asked, side.waiting, classes)

    async def _classes_of(
        self, principal: Principal, shala: UUID
    ) -> tuple[StoredClass, ...] | None:
        """The shala's classes, or None where the read's guard says no (a student, an
        assistant; a shala left) or classes are not wired."""
        if self._h.classes is None:
            return None
        try:
            return await self._h.classes.classes.execute(principal, shala)
        except (NotAllowed, NotFound):
            return None
        except Exception:  # an optional block: the card shows without it
            log.exception("shala card: the classes read failed")
            return None

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
        if not removes and self._username:  # C3 (UI-06 stage 6): my own students' way in
            rows.append([self._button(locale, "links-invite", links_cb.plain("i"))])
        rows.append([self._button(locale, "log-back", cb.on_shala("c", shala))])
        if not found.students:
            text = self._t.t(locale, "shala-no-students")
        else:
            text = self._t.t(locale, "shala-students", n=found.total)  # type: ignore[arg-type]
            if not removes:  # names only: nothing to tap, and whose students they are
                names = "\n".join([text, *(self._name(locale, s.name) for s in found.students)])
                teacher = "yes" if can_be_asked_as_teacher(found.me) else "no"
                hint = self._t.t(locale, "shala-students-not-yours", teacher=teacher)
                text = f"{names}\n\n{hint}"
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
        if can_be_asked_as_teacher(card.me):  # their own students are not the shala's
            text = f"{text} {self._t.t(locale, 'shala-leave-own-students')}"
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

    async def gone(self, principal: Principal) -> Screen:
        """Where a tap about a shala the caller is not in (any more) lands: their list."""
        return await self._links.overview(principal)

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
        offered = [role for role in _ROLE_ORDER if role in allowed]
        rows = [
            [
                InlineKeyboardButton(
                    text=self._role(locale, role), callback_data=cb.staff_link(shala, role)
                )
            ]
            for role in offered
        ]
        rows.append([self._button(locale, "log-back", cb.on_shala("c", shala))])
        # C14 (UI-06 stage 6): what each role offered can do, as `application/policies` says.
        hints = [
            self._t.t(
                locale,
                "shala-role-hint-line",
                role=self._role(locale, role),
                hint=self._t.t(locale, "shala-role-hint", role=role.value),
            )
            for role in offered
        ]
        text = "\n\n".join([self._t.t(locale, "shala-staff-pick"), "\n".join(hints)])
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

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
        requests = self._links.requests  # ID-07
        match tap:
            case cb.Join(code):
                return self.join(principal, code)
            case cb.AcceptStaff(code):
                return self.accept_staff(principal, code)
            case cb.Language(locale, code, staff):
                client = client_profile(callback.from_user)
                return self.language(principal, locale, code, client, staff)
            case cb.Consent(code, staff, details):
                return self.invited(principal, ShalaInvite(code, staff), details)
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
            case cb.Member("ta" | "tw" | "tx" as action, shala, target) if requests is not None:
                if action == "ta":  # ID-07: the consent tap
                    return requests.ask(principal, shala, target)
                if action == "tw":
                    return requests.ask_withdraw(principal, shala, target)
                return requests.withdraw(principal, shala, target)
            case cb.Member(_, shala, _):
                return self.card(principal, shala)
            case cb.Shala("t" | "td" as action, shala) if requests is not None:
                return requests.ask_screen(principal, shala, details=action == "td")
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
            case cb.Shala("mo", shala):
                return self.more(principal, shala)
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
            if qr is None:  # not my shala (any more), or no bot name: the list, not silence
                return show(callback, await screens.gone(principal))
            if callback.bot is not None:
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
