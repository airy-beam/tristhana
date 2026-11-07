"""Shalas (SC-01, ADR-0033): both adapters use these, except `PreviewShalaInvite`, `JoinShala`
and `AcceptStaffInvite`, because a shala link always lands in the bot (as ID-04's Q12).

A shala exposes names and roles only; no use case here reads a log. Non-members get
`NotFound`, never `NotAllowed`, so shala ids can't be probed. Every guarded write reads the
caller's membership in its own statement (`Guarded`).
"""

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

from tristhana.application.moon import UnknownLocation
from tristhana.application.policies import NotAllowed, NotFound, Principal, can_view_shala_students
from tristhana.application.ports.notifications import Notifier, Recipient
from tristhana.application.ports.shalas import (
    CapReached,
    Guarded,
    Joined,
    MemberLookup,
    MyShala,
    NewShala,
    ShalaCaps,
    ShalaCard,
    ShalaRepository,
    StaffAccepted,
    StaffInvite,
    StudentsPage,
)
from tristhana.application.ports.storage import Clock
from tristhana.application.ports.teacher_links import CodeSource
from tristhana.application.settings import caller_today
from tristhana.domain.accounts import Account, moon_follow_of
from tristhana.domain.moon import Cities, City, MoonFollow, MoonSource, ShalaMoon, moon_follow
from tristhana.domain.shalas import (
    MAX_OWNED,
    MAX_PENDING_STAFF_INVITES,
    MAX_STAFF,
    MAX_STAFF_OF,
    MAX_STUDENT_OF,
    MAX_STUDENTS,
    STAFF_INVITE_TTL,
    InvalidShalaName,
    JoinState,
    ShalaInvite,
    ShalaPatch,
    ShalaRole,
    join_state,
    main_shala,
    normalize_shala_name,
)

CAPS = ShalaCaps(
    owned=MAX_OWNED,
    staff=MAX_STAFF,
    students=MAX_STUDENTS,
    staff_of=MAX_STAFF_OF,
    student_of=MAX_STUDENT_OF,
    pending_invites=MAX_PENDING_STAFF_INVITES,
)
_OLDER, _NEWER = datetime.min.replace(tzinfo=UTC), datetime.max.replace(tzinfo=UTC)


def _unwrap[T](guarded: Guarded[T]) -> T | None:
    if guarded.me is None:
        raise NotFound
    if not guarded.done:
        raise NotAllowed
    return guarded.value


def _value[T](guarded: Guarded[T]) -> T:
    """As `_unwrap`, for writes that always return a value: a missing one means the shala
    went in the same instant."""
    value = _unwrap(guarded)
    if value is None:
        raise NotFound
    return value


def _projected(card: ShalaCard) -> ShalaCard:
    """Students never learn how many students there are (Q106)."""
    return card if can_view_shala_students(card.me) else replace(card, students_total=None)


def _city(cities: Cities, slug: str) -> str:
    if cities.find(slug) is None:
        raise UnknownLocation(slug)
    return slug


def _with(account: Account, card: ShalaCard) -> ShalaMoon:
    """The caller's main shala once they're in `card` (the newest of their memberships)."""
    teacher = account.main_teacher
    joined = ShalaMoon(
        card.id,
        card.name,
        card.moon_city or card.city,
        card.me.staff,
        # Q108 reads it for student rows only; staff rows carry False, as the account load.
        not card.me.staff and teacher is not None and any(s.id == teacher.id for s in card.staff),
        card.city,
    )
    current = account.shala
    if current is None or current.id == card.id:
        return joined
    return main_shala([(current, _OLDER), (joined, _NEWER)]) or joined


def _moved(account: Account, shala: ShalaMoon, cities: Cities) -> MoonFollow | None:
    """The caller's moon city with `shala` as their main shala, if its slug moved."""
    after = moon_follow(account.moon_location, account.teaches, account.main_teacher, shala, cities)
    return after if after.city.slug != moon_follow_of(account, cities).city.slug else None


def _keep(account: Account, shala: ShalaMoon, cities: Cities) -> City | None:
    """Q98: a never-chose teacher now follows their shala, but their students read only the
    stored NULL (one hop): offer to keep the shala city as their own."""
    if account.moon_location is not None or not account.teaches:
        return None
    after = moon_follow(None, True, account.main_teacher, shala, cities)
    return after.city if after.source is MoonSource.SHALA else None


class CreateShala:
    def __init__(
        self, shalas: ShalaRepository, codes: CodeSource, clock: Clock, cities: Cities
    ) -> None:
        self._shalas = shalas
        self._codes = codes
        self._clock = clock
        self._cities = cities

    async def execute(
        self,
        principal: Principal,
        name: str,
        city: str,
        online: bool,
        roles: frozenset[ShalaRole],
    ) -> ShalaCard:
        """The caller becomes the owner, with the roles they ticked. Raises
        `InvalidShalaName`, `UnknownLocation`, `CapReached`."""
        clean = normalize_shala_name(name)
        if clean is None:
            raise InvalidShalaName
        new = NewShala(clean, _city(self._cities, city), online, roles, self._codes.new())
        today = caller_today(principal, self._clock)
        card = await self._shalas.create(principal.account.id, new, CAPS, today)
        if card is None:
            raise CapReached
        return card


class GetMyShalas:
    def __init__(self, shalas: ShalaRepository) -> None:
        self._shalas = shalas

    async def execute(self, principal: Principal) -> tuple[MyShala, ...]:
        return await self._shalas.mine(principal.account.id)


class GetShala:
    def __init__(self, shalas: ShalaRepository) -> None:
        self._shalas = shalas

    async def execute(self, principal: Principal, shala: UUID) -> ShalaCard:
        card = await self._shalas.card(shala, principal.account.id)
        if card is None:
            raise NotFound
        return _projected(card)


class UpdateShala:
    def __init__(self, shalas: ShalaRepository, cities: Cities) -> None:
        self._shalas = shalas
        self._cities = cities

    async def execute(self, principal: Principal, shala: UUID, patch: ShalaPatch) -> ShalaCard:
        """Raises `InvalidShalaName`, `UnknownLocation`, `NotFound`, `NotAllowed`."""
        if isinstance(patch.name, str):
            clean = normalize_shala_name(patch.name)
            if clean is None:
                raise InvalidShalaName
            patch = replace(patch, name=clean)
        for slug in (patch.city, patch.moon_city):
            if isinstance(slug, str):
                _city(self._cities, slug)
        card = _value(await self._shalas.update(shala, principal.account.id, patch))
        return _projected(card)


class DeleteShala:
    def __init__(self, shalas: ShalaRepository) -> None:
        self._shalas = shalas

    async def execute(self, principal: Principal, shala: UUID) -> None:
        """Silent, for everyone in it."""
        _unwrap(await self._shalas.delete(shala, principal.account.id))


class GetShalaStudents:
    def __init__(self, shalas: ShalaRepository) -> None:
        self._shalas = shalas

    async def execute(
        self, principal: Principal, shala: UUID, offset: int, limit: int
    ) -> StudentsPage:
        guarded = await self._shalas.students(shala, principal.account.id, offset, limit)
        return replace(_value(guarded), me=guarded.me)


class GetShalaMember:
    def __init__(self, shalas: ShalaRepository) -> None:
        self._shalas = shalas

    async def execute(self, principal: Principal, shala: UUID, target: UUID) -> MemberLookup:
        """Staff are anyone's to see; a student only staff's (Q106)."""
        found = await self._shalas.member(shala, principal.account.id, target)
        if found is None:
            raise NotFound
        card = _projected(found.card)
        if found.found and not found.staff and not can_view_shala_students(card.me):
            return MemberLookup(card, False)
        return replace(found, card=card)


class GetJoinLink:
    def __init__(self, shalas: ShalaRepository) -> None:
        self._shalas = shalas

    async def execute(self, principal: Principal, shala: UUID) -> str:
        """The student join code (staff only)."""
        code = _value(await self._shalas.join_link(shala, principal.account.id))
        return code


class RotateJoinLink:
    """The only revoke: the old link and QR die, members stay."""

    def __init__(self, shalas: ShalaRepository, codes: CodeSource) -> None:
        self._shalas = shalas
        self._codes = codes

    async def execute(self, principal: Principal, shala: UUID) -> str:
        code = _value(
            await self._shalas.rotate_join(shala, principal.account.id, self._codes.new())
        )
        return code


class CreateStaffInvite:
    def __init__(self, shalas: ShalaRepository, codes: CodeSource, clock: Clock) -> None:
        self._shalas = shalas
        self._codes = codes
        self._clock = clock

    async def execute(self, principal: Principal, shala: UUID, role: ShalaRole) -> StaffInvite:
        """A link for one person in `role`, single use, for 7 days. Raises `CapReached`."""
        expires_at = self._clock.now() + STAFF_INVITE_TTL
        invite = _unwrap(
            await self._shalas.invite_staff(
                shala, principal.account.id, role, self._codes.new(), expires_at, CAPS
            )
        )
        if invite is None:
            raise CapReached
        return invite


class SetStaffRoles:
    def __init__(self, shalas: ShalaRepository) -> None:
        self._shalas = shalas

    async def execute(
        self, principal: Principal, shala: UUID, target: UUID, roles: frozenset[ShalaRole]
    ) -> ShalaCard:
        card = _value(await self._shalas.set_roles(shala, principal.account.id, target, roles))
        return _projected(card)


class RemoveStaff:
    def __init__(self, shalas: ShalaRepository) -> None:
        self._shalas = shalas

    async def execute(self, principal: Principal, shala: UUID, target: UUID) -> None:
        """Silent and idempotent; the caller's own id is leaving (never the owner, Q102)."""
        _unwrap(await self._shalas.remove_staff(shala, principal.account.id, target))


class RemoveShalaStudent:
    def __init__(self, shalas: ShalaRepository) -> None:
        self._shalas = shalas

    async def execute(self, principal: Principal, shala: UUID, target: UUID) -> None:
        """Silent and idempotent; the caller's own id is leaving."""
        _unwrap(await self._shalas.remove_student(shala, principal.account.id, target))


@dataclass(frozen=True, slots=True)
class ShalaPreviewed:
    """What a link shows before ✅: the shala, and for a staff link the role and the inviter.
    Never anyone else."""

    state: JoinState
    name: str
    city: str
    staff: bool = False
    role: ShalaRole | None = None
    inviter_name: str | None = None


class PreviewShalaInvite:
    def __init__(self, shalas: ShalaRepository) -> None:
        self._shalas = shalas

    async def execute(self, principal: Principal, invite: ShalaInvite) -> ShalaPreviewed | None:
        """None: an unknown, rotated, used or expired code."""
        me = principal.account.id
        if invite.staff:
            staff = await self._shalas.preview_staff(invite.code, me)
            if staff is None:
                return None
            state = JoinState.STAFF if staff.me is not None and staff.me.staff else JoinState.OPEN
            return ShalaPreviewed(
                state, staff.shala_name, staff.city, True, staff.role, staff.inviter_name
            )
        found = await self._shalas.preview(invite.code, me)
        if found is None:
            return None
        state = join_state(found.me, found.students, found.my_student_of)
        return ShalaPreviewed(state, found.name, found.city)


class JoinShala:
    def __init__(self, shalas: ShalaRepository, clock: Clock, cities: Cities) -> None:
        self._shalas = shalas
        self._clock = clock
        self._cities = cities

    async def execute(self, principal: Principal, code: str) -> Joined | None:
        """The student's ✅. Silent (Q105), and no teacher link. `moon` is set when joining
        moved the caller's moon city."""
        account = principal.account
        today = caller_today(principal, self._clock)
        joined = await self._shalas.join(code, account.id, CAPS, today)
        if joined is None or not joined.created or joined.card is None:
            return joined
        return replace(joined, moon=_moved(account, _with(account, joined.card), self._cities))


class AcceptStaffInvite:
    def __init__(
        self, shalas: ShalaRepository, notifier: Notifier, clock: Clock, cities: Cities
    ) -> None:
        self._shalas = shalas
        self._notifier = notifier
        self._clock = clock
        self._cities = cities

    async def execute(self, principal: Principal, code: str) -> StaffAccepted | None:
        """The invitee's ✅: the only way someone becomes staff (Q100). The inviter's note is
        best effort and silent. None: a used or expired link."""
        account = principal.account
        today = caller_today(principal, self._clock)
        accepted = await self._shalas.accept_staff(code, account.id, CAPS, today)
        if accepted is None or not accepted.created or accepted.card is None:
            return accepted
        card, shala = accepted.card, _with(account, accepted.card)
        accepted = replace(
            accepted,
            moon=_moved(account, shala, self._cities),
            # Only when this shala becomes the main one: no repeat offer for an older shala.
            keep=_keep(account, shala, self._cities) if shala.id == card.id else None,
        )
        if accepted.inviter_telegram_id is not None:
            await self._notifier.tell_staff_joined(
                Recipient(accepted.inviter_telegram_id, accepted.inviter_locale),
                account.display_name,
                card.name,
                accepted.role,
            )
        return accepted


@dataclass(frozen=True, slots=True)
class ShalaUseCases:
    create: CreateShala
    mine: GetMyShalas
    get: GetShala
    update: UpdateShala
    delete: DeleteShala
    students: GetShalaStudents
    member: GetShalaMember
    join_link: GetJoinLink
    rotate: RotateJoinLink
    invite_staff: CreateStaffInvite
    set_roles: SetStaffRoles
    remove_staff: RemoveStaff
    remove_student: RemoveShalaStudent
    preview: PreviewShalaInvite
    join: JoinShala
    accept_staff: AcceptStaffInvite
    cities: Cities
    clock: Clock
