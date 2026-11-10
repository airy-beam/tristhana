"""Teacher-student links (ID-04, ADR-0030): both adapters use these, except `AcceptInvite`
and `PreviewInvite`, because an invite always lands in the bot (Q12).

A link exposes names here; what a teacher sees of a student is `teacher_view` (ST-06). Every
write is keyed on the caller's account, so an id from a client can only ever touch the
caller's own rows.
"""

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING
from uuid import UUID

from tristhana.application.labels import PracticeLabels
from tristhana.application.policies import (
    NotAllowed,
    Principal,
    can_choose_primary,
    can_manage_invite,
    can_unlink,
)
from tristhana.application.ports.notifications import KeepOffer, Notifier, Recipient
from tristhana.application.ports.storage import Clock
from tristhana.application.ports.teacher_links import (
    Accepted,
    Caps,
    CodeSource,
    Links,
    NotLinked,
    QrCodes,
    TeacherLinkRepository,
)
from tristhana.application.settings import caller_today
from tristhana.application.teacher_marks import MarkForStudent
from tristhana.application.teacher_view import TeacherViewUseCases
from tristhana.domain.accounts import Account, moon_follow_of
from tristhana.domain.directory_listing import ListingMark
from tristhana.domain.moon import Cities, MoonFollow, MoonSource, TeacherMoon, moon_follow
from tristhana.domain.practice import PracticeCatalog
from tristhana.domain.teacher_links import MAX_STUDENTS, MAX_TEACHERS, InviteState, invite_state

if TYPE_CHECKING:
    from tristhana.application.announcements import AnnouncementUseCases
    from tristhana.application.shalas import ShalaUseCases

CAPS = Caps(MAX_TEACHERS, MAX_STUDENTS)


@dataclass(frozen=True, slots=True)
class Previewed:
    state: InviteState
    name: str | None
    listing: ListingMark | None = None  # ID-05


def _moved(account: Account, main: TeacherMoon | None, cities: Cities) -> MoonFollow | None:
    """MD-02: the caller's effective moon city with `main` as the main teacher, if its slug
    differs from now: the one-line notice on the result of their own tap."""
    after = moon_follow(account.moon_location, account.teaches, main, account.shala, cities)
    return after if after.city.slug != moon_follow_of(account, cities).city.slug else None


def _keep_offer(accepted: Accepted, cities: Cities) -> KeepOffer | None:
    """The city a teacher stops inheriting with their first student (Q76 flip, decision 3)."""
    own, main = accepted.teacher_moon, accepted.teacher_main
    # Only a NULL can be kept (`set_moon_location_if_unset`): a removed slug or a chosen
    # follow gets no offer.
    if accepted.teacher_students_before or own is not None or main is None:
        return None
    shala = accepted.teacher_shala
    before = moon_follow(own, False, main, shala, cities)
    after = moon_follow(own, True, main, shala, cities)
    if before.source is not MoonSource.TEACHER or after.city.slug == before.city.slug:
        return None
    return KeepOffer(before.city, after.city, main.name)


class PreviewInvite:
    def __init__(self, links: TeacherLinkRepository) -> None:
        self._links = links

    async def execute(self, principal: Principal, code: str) -> Previewed | None:
        """None: the code is unknown or was rotated."""
        me = principal.account.id
        found = await self._links.preview(code, me)
        if found is None:
            return None
        state = invite_state(
            me, found.teacher_id, found.already, found.my_teachers, found.their_students
        )
        return Previewed(state, found.teacher_name, found.listing)


class AcceptInvite:
    def __init__(
        self, links: TeacherLinkRepository, notifier: Notifier, clock: Clock, cities: Cities
    ) -> None:
        self._links = links
        self._notifier = notifier
        self._clock = clock
        self._cities = cities

    async def execute(self, principal: Principal, code: str) -> Accepted | None:
        """The student's tap: the only way a link comes to exist. `linked_on` is their local
        date, the boundary of "from today on" in the consent. The note is best effort: the
        list is the record, so a blocked bot neither fails this nor marks anyone. `moon` is
        set when this first link moved the caller's moon city (MD-02)."""
        account = principal.account
        today = caller_today(principal, self._clock)
        accepted = await self._links.accept(code, account.id, CAPS, today)
        if accepted is None or not accepted.created:
            return accepted
        if account.main_teacher is None:
            teacher = TeacherMoon(accepted.teacher_id, accepted.teacher_name, accepted.teacher_moon)
            accepted = replace(accepted, moon=_moved(account, teacher, self._cities))
        if accepted.teacher_telegram_id is not None:
            await self._notifier.tell_student_joined(
                Recipient(accepted.teacher_telegram_id, accepted.teacher_locale),
                account.display_name,
                _keep_offer(accepted, self._cities),
            )
        return accepted


class GetLinks:
    def __init__(self, links: TeacherLinkRepository) -> None:
        self._links = links

    async def execute(self, principal: Principal) -> Links:
        return await self._links.overview(principal.account.id)


class GetInvite:
    def __init__(self, links: TeacherLinkRepository, codes: CodeSource) -> None:
        self._links = links
        self._codes = codes

    async def execute(self, principal: Principal) -> str:
        account = principal.account
        if not can_manage_invite(account, account):
            raise NotAllowed
        return await self._links.invite(account.id, self._codes.new())


class RotateInvite:
    """The only revoke: the old link and QR die, people already linked stay."""

    def __init__(self, links: TeacherLinkRepository, codes: CodeSource) -> None:
        self._links = links
        self._codes = codes

    async def execute(self, principal: Principal) -> str:
        account = principal.account
        if not can_manage_invite(account, account):
            raise NotAllowed
        return await self._links.rotate(account.id, self._codes.new())


class SetPrimaryTeacher:
    def __init__(self, links: TeacherLinkRepository, cities: Cities) -> None:
        self._links = links
        self._cities = cities

    async def execute(self, principal: Principal, teacher_id: UUID) -> MoonFollow | None:
        """The caller's new moon city, if the slug moved (MD-02). Raises `NotLinked`,
        `LinksChanged`."""
        account = principal.account
        if not can_choose_primary(account, account.id):
            raise NotAllowed
        main = await self._links.set_primary(account.id, teacher_id)
        if main is None:
            raise NotLinked
        return _moved(account, main, self._cities)


class RemoveTeacher:
    def __init__(self, links: TeacherLinkRepository, cities: Cities) -> None:
        self._links = links
        self._cities = cities

    async def execute(self, principal: Principal, teacher_id: UUID) -> MoonFollow | None:
        """Silent and idempotent (Q8). The caller's new moon city, if the slug moved."""
        account = principal.account
        if not can_unlink(account, account.id, teacher_id):
            raise NotAllowed
        unlinked = await self._links.unlink(account.id, teacher_id)
        return _moved(account, unlinked.main, self._cities) if unlinked.removed else None


class RemoveStudent:
    def __init__(self, links: TeacherLinkRepository) -> None:
        self._links = links

    async def execute(self, principal: Principal, student_id: UUID) -> None:
        """Silent and idempotent (Q8)."""
        account = principal.account
        if not can_unlink(account, student_id, account.id):
            raise NotAllowed
        await self._links.unlink(student_id, account.id)  # the student is never told


@dataclass(frozen=True, slots=True)
class LinkUseCases:
    preview: PreviewInvite
    accept: AcceptInvite
    get: GetLinks
    invite: GetInvite
    rotate: RotateInvite
    primary: SetPrimaryTeacher
    remove_teacher: RemoveTeacher
    remove_student: RemoveStudent
    qr: QrCodes
    view: TeacherViewUseCases
    labels: PracticeLabels
    catalog: PracticeCatalog
    mark: MarkForStudent  # PR-08 Phase 3: a new asana from the student card
    shalas: "ShalaUseCases | None" = None  # SC-01: /teachers lists them, the bot joins them
    announcements: "AnnouncementUseCases | None" = None  # NT-03: the feed, mute, pins on cards
