"""Teacher-student links (ID-04, ADR-0030): both adapters use these, except `AcceptInvite`
and `PreviewInvite`, because an invite always lands in the bot (Q12).

A link exposes only names. Every write is keyed on the caller's account, so an id from a
client can only ever touch the caller's own rows.
"""

from dataclasses import dataclass
from uuid import UUID

from tristhana.application.policies import (
    NotAllowed,
    Principal,
    can_choose_primary,
    can_manage_invite,
    can_unlink,
)
from tristhana.application.ports.notifications import Notifier, Recipient
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
from tristhana.domain.teacher_links import MAX_STUDENTS, MAX_TEACHERS, InviteState, invite_state

CAPS = Caps(MAX_TEACHERS, MAX_STUDENTS)


@dataclass(frozen=True, slots=True)
class Previewed:
    state: InviteState
    name: str | None


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
        return Previewed(state, found.teacher_name)


class AcceptInvite:
    def __init__(self, links: TeacherLinkRepository, notifier: Notifier, clock: Clock) -> None:
        self._links = links
        self._notifier = notifier
        self._clock = clock

    async def execute(self, principal: Principal, code: str) -> Accepted | None:
        """The student's tap: the only way a link comes to exist. `linked_on` is their local
        date, the boundary of "from today on" in the consent. The note is best effort: the
        list is the record, so a blocked bot neither fails this nor marks anyone."""
        today = caller_today(principal, self._clock)
        accepted = await self._links.accept(code, principal.account.id, CAPS, today)
        if accepted is not None and accepted.created and accepted.teacher_telegram_id is not None:
            await self._notifier.tell_student_joined(
                Recipient(accepted.teacher_telegram_id, accepted.teacher_locale),
                principal.account.display_name,
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
    def __init__(self, links: TeacherLinkRepository) -> None:
        self._links = links

    async def execute(self, principal: Principal, teacher_id: UUID) -> None:
        """Raises `NotLinked`, `LinksChanged`."""
        account = principal.account
        if not can_choose_primary(account, account.id):
            raise NotAllowed
        if not await self._links.set_primary(account.id, teacher_id):
            raise NotLinked


class RemoveTeacher:
    def __init__(self, links: TeacherLinkRepository) -> None:
        self._links = links

    async def execute(self, principal: Principal, teacher_id: UUID) -> None:
        """Silent and idempotent (Q8)."""
        account = principal.account
        if not can_unlink(account, account.id, teacher_id):
            raise NotAllowed
        await self._links.unlink(account.id, teacher_id)


class RemoveStudent:
    def __init__(self, links: TeacherLinkRepository) -> None:
        self._links = links

    async def execute(self, principal: Principal, student_id: UUID) -> None:
        """Silent and idempotent (Q8)."""
        account = principal.account
        if not can_unlink(account, student_id, account.id):
            raise NotAllowed
        await self._links.unlink(student_id, account.id)


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
