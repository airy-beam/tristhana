"""Shalas, the use cases on fakes (SC-01 spec §3, §7, §8): create makes the owner and their staff
row; caps; joins store the joiner's local date; staff links work once, expire, convert a
student and note the inviter silently in their language; non-members get `NotFound`, members
without the right `NotAllowed`; leaving and removing are silent; the shala step reaches
`SetMoonLocation`, `_moved` and the Keep offers; no shala use case reads a log. A frozen
clock throughout."""

import ast
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from tests.fakes import FixedClock, cities
from tests.moon_follow_fakes import person
from tests.shala_fakes import (
    InMemoryShalas,
    ShalaAccounts,
    ShalaLinks,
    StaffNotifier,
)
from tests.teacher_link_fakes import FixedCodes
from tristhana.application.moon import SetMoonLocation, UnknownLocation
from tristhana.application.policies import (
    NotAllowed,
    NotFound,
    Principal,
    can_view_activity,
    can_view_last_asana,
)
from tristhana.application.ports.notifications import Recipient
from tristhana.application.ports.shalas import CapReached
from tristhana.application.ports.teacher_view import StudentLink
from tristhana.application.shalas import (
    AcceptStaffInvite,
    CreateShala,
    CreateStaffInvite,
    DeleteShala,
    GetJoinLink,
    GetMyShalas,
    GetShala,
    GetShalaStudents,
    JoinShala,
    PreviewShalaInvite,
    RemoveShalaStudent,
    RemoveStaff,
    RotateJoinLink,
    SetStaffRoles,
    ShalaPatch,
    UpdateShala,
)
from tristhana.application.teacher_links import AcceptInvite, RemoveTeacher
from tristhana.domain.accounts import Account
from tristhana.domain.locale import Locale
from tristhana.domain.moon import FOLLOW_SHALA, FOLLOW_TEACHER, MoonSource
from tristhana.domain.shalas import (
    MAX_OWNED,
    MAX_PENDING_STAFF_INVITES,
    MAX_STAFF,
    MAX_STUDENT_OF,
    MAX_STUDENTS,
    STAFF_INVITE_TTL,
    InvalidShalaName,
    JoinState,
    ShalaInvite,
    ShalaRole,
)

NOW = datetime(2026, 11, 7, 6, 0, tzinfo=UTC)  # 11:00 in Almaty
JOIN = "J0inC0deJ0inC0de"
STAFF_CODE = "St4ffC0deSt4ffC0"
NEW_CODE = "N3wC0deN3wC0deXy"
TEACHER, ASSISTANT, OFFICE, ADMIN = (
    ShalaRole.TEACHER,
    ShalaRole.ASSISTANT,
    ShalaRole.OFFICE,
    ShalaRole.ADMIN,
)


@dataclass
class World:
    instant: datetime = NOW
    clock: FixedClock = field(init=False)
    accounts: ShalaAccounts = field(init=False)
    links: ShalaLinks = field(init=False)
    shalas: InMemoryShalas = field(init=False)
    notifier: StaffNotifier = field(init=False)

    def __post_init__(self) -> None:
        self.clock = FixedClock(self.instant)
        self.accounts = ShalaAccounts(clock=self.clock)
        self.links = ShalaLinks(self.accounts)
        self.shalas = InMemoryShalas(self.accounts, self.links)
        self.links.shalas = self.shalas
        self.accounts.links = self.links
        self.accounts.shalas = self.shalas
        self.notifier = StaffNotifier()

    def person(
        self,
        telegram_id: str,
        name: str | None = "Person",
        *,
        moon: str | None = None,
        locale: Locale = "en",
        zone: str | None = "Asia/Almaty",
    ) -> Account:
        return person(self.accounts, telegram_id, name, moon=moon, locale=locale, zone=zone)

    def me(self, account: Account) -> Principal:
        """The principal as the middleware loads it: with MD-02's and SC-01's inputs."""
        return Principal(self.accounts.inputs(self.accounts.accounts[account.id]))

    def shala(self, owner: Account, city: str = "almaty", **kw: object) -> UUID:
        return self.shalas.add_shala(owner.id, city=city, **kw).id  # type: ignore[arg-type]

    def codes(self, *codes: str) -> FixedCodes:
        return FixedCodes(*codes)


@pytest.fixture
def world() -> World:
    return World()


# Create


async def test_create_makes_the_caller_owner_with_a_staff_row(world: World) -> None:
    anna = world.person("1", "Anna")

    card = await CreateShala(world.shalas, world.codes(JOIN), world.clock, cities()).execute(
        world.me(anna), "  Ashtanga   Almaty ", "almaty", False, frozenset({TEACHER})
    )

    assert (card.name, card.city, card.online, card.moon_city) == (
        "Ashtanga Almaty",
        "almaty",
        False,
        None,
    )
    assert card.owner_id == anna.id
    assert (card.me.owner, card.me.roles, card.me.student) == (True, frozenset({TEACHER}), False)
    assert [(s.id, s.owner, s.roles) for s in card.staff] == [(anna.id, True, frozenset({TEACHER}))]
    assert world.shalas.shalas[card.id].join_code == JOIN
    assert world.shalas.staff[(card.id, anna.id)].joined_on == date(2026, 11, 7)


async def test_an_owner_may_tick_no_role(world: World) -> None:
    anna = world.person("1", "Anna")

    card = await CreateShala(world.shalas, world.codes(JOIN), world.clock, cities()).execute(
        world.me(anna), "Front Office", "almaty", True, frozenset()
    )

    assert (card.me.owner, card.me.roles, card.online) == (True, frozenset(), True)


@pytest.mark.parametrize("name", ["", "   ", "‮‭"])
async def test_a_blank_name_is_refused(world: World, name: str) -> None:
    anna = world.person("1", "Anna")

    with pytest.raises(InvalidShalaName):
        await CreateShala(world.shalas, world.codes(JOIN), world.clock, cities()).execute(
            world.me(anna), name, "almaty", False, frozenset()
        )
    assert world.shalas.shalas == {}


@pytest.mark.parametrize("city", ["atlantis", FOLLOW_TEACHER, FOLLOW_SHALA, ""])
async def test_an_unlisted_city_is_refused(world: World, city: str) -> None:
    anna = world.person("1", "Anna")

    with pytest.raises(UnknownLocation):
        await CreateShala(world.shalas, world.codes(JOIN), world.clock, cities()).execute(
            world.me(anna), "Shala", city, False, frozenset()
        )
    assert world.shalas.shalas == {}


async def test_the_owned_cap(world: World) -> None:
    anna = world.person("1", "Anna")
    for i in range(MAX_OWNED):
        world.shalas.add_shala(anna.id, f"S{i}", code=f"Code{i:012d}")

    with pytest.raises(CapReached):
        await CreateShala(world.shalas, world.codes(JOIN), world.clock, cities()).execute(
            world.me(anna), "One more", "almaty", False, frozenset()
        )
    assert len(world.shalas.shalas) == MAX_OWNED


# Reading: members only; students never see each other


async def test_a_member_reads_the_card_and_a_stranger_gets_not_found(world: World) -> None:
    anna, ash, mallory = world.person("1", "Anna"), world.person("2", "Ash"), world.person("3")
    shala = world.shala(anna)
    world.shalas.add_student(shala, ash.id)

    card = await GetShala(world.shalas).execute(world.me(ash), shala)

    assert card.me.student is True
    assert [s.name for s in card.staff] == ["Anna"]
    with pytest.raises(NotFound):
        await GetShala(world.shalas).execute(world.me(mallory), shala)
    with pytest.raises(NotFound):
        await GetShala(world.shalas).execute(world.me(mallory), uuid4())


async def test_an_unknown_id_and_a_stranger_are_the_same_answer(world: World) -> None:
    """Ids can't be probed: never `NotAllowed` for a non-member."""
    anna, mallory = world.person("1", "Anna"), world.person("3")
    shala = world.shala(anna)
    use_cases: list[Callable[[Principal, UUID], Awaitable[object]]] = [
        lambda p, s: GetShala(world.shalas).execute(p, s),
        lambda p, s: GetShalaStudents(world.shalas).execute(p, s, 0, 10),
        lambda p, s: UpdateShala(world.shalas, cities()).execute(p, s, ShalaPatch(name="X")),
        lambda p, s: DeleteShala(world.shalas).execute(p, s),
        lambda p, s: GetJoinLink(world.shalas).execute(p, s),
        lambda p, s: RotateJoinLink(world.shalas, world.codes(NEW_CODE)).execute(p, s),
        lambda p, s: CreateStaffInvite(world.shalas, world.codes(NEW_CODE), world.clock).execute(
            p, s, TEACHER
        ),
        lambda p, s: SetStaffRoles(world.shalas).execute(p, s, anna.id, frozenset()),
        lambda p, s: RemoveStaff(world.shalas).execute(p, s, anna.id),
        lambda p, s: RemoveShalaStudent(world.shalas).execute(p, s, anna.id),
    ]

    for run in use_cases:
        for target in (shala, uuid4()):
            with pytest.raises(NotFound):
                await run(world.me(mallory), target)
    assert world.shalas.writes == []


async def test_students_never_see_other_students(world: World) -> None:
    anna, ash, bea = world.person("1", "Anna"), world.person("2", "Ash"), world.person("3", "Bea")
    shala = world.shala(anna)
    world.shalas.add_student(shala, ash.id)
    world.shalas.add_student(shala, bea.id)

    with pytest.raises(NotAllowed):
        await GetShalaStudents(world.shalas).execute(world.me(ash), shala, 0, 10)
    card = await GetShala(world.shalas).execute(world.me(ash), shala)

    assert "Bea" not in [s.name for s in card.staff]


@pytest.mark.parametrize("role", list(ShalaRole))
async def test_every_staff_role_sees_student_names_and_the_count(
    world: World, role: ShalaRole
) -> None:
    anna, dana = world.person("1", "Anna"), world.person("4", "Dana")
    shala = world.shala(anna)
    world.shalas.add_staff(shala, dana.id, role)
    for i in range(12):
        world.shalas.add_student(shala, world.person(f"{100 + i}", f"S{i:02d}").id)

    page = await GetShalaStudents(world.shalas).execute(world.me(dana), shala, 10, 10)

    assert page.total == 12
    assert [s.name for s in page.students] == ["S10", "S11"]


async def test_my_shalas_lists_both_sides(world: World) -> None:
    anna, ash = world.person("1", "Anna"), world.person("2", "Ash")
    mine = world.shala(ash, "moscow", name="Mine", code="Mine000000000000")
    theirs = world.shala(anna, name="Theirs")
    world.shalas.add_student(theirs, ash.id)

    listed = await GetMyShalas(world.shalas).execute(world.me(ash))

    assert [(s.id, s.me.owner, s.me.student) for s in listed] == [
        (mine, True, False),
        (theirs, False, True),
    ]


# Edit and delete


async def test_owner_and_admin_edit_others_get_not_allowed(world: World) -> None:
    anna, dana, tom = world.person("1", "Anna"), world.person("4", "Dana"), world.person("5")
    shala = world.shala(anna)
    world.shalas.add_staff(shala, dana.id, ADMIN)
    world.shalas.add_staff(shala, tom.id, TEACHER)
    update = UpdateShala(world.shalas, cities())

    by_admin = await update.execute(world.me(dana), shala, ShalaPatch(moon_city="mysuru"))
    by_owner = await update.execute(world.me(anna), shala, ShalaPatch(name=" New  name "))

    assert (by_admin.moon_city, by_owner.name) == ("mysuru", "New name")
    with pytest.raises(NotAllowed):
        await update.execute(world.me(tom), shala, ShalaPatch(online=True))
    assert world.shalas.shalas[shala].online is False


async def test_moon_city_none_means_same_as_the_city(world: World) -> None:
    anna = world.person("1", "Anna")
    shala = world.shala(anna, moon_city="mysuru")

    card = await UpdateShala(world.shalas, cities()).execute(
        world.me(anna), shala, ShalaPatch(moon_city=None)
    )

    assert card.moon_city is None
    assert world.shalas.main_of(anna.id) is not None
    assert world.shalas.main_of(anna.id).moon_city == "almaty"  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "patch",
    [ShalaPatch(city="atlantis"), ShalaPatch(moon_city="atlantis"), ShalaPatch(city=FOLLOW_SHALA)],
)
async def test_an_edit_to_an_unlisted_city_is_refused(world: World, patch: ShalaPatch) -> None:
    anna = world.person("1", "Anna")
    shala = world.shala(anna)

    with pytest.raises(UnknownLocation):
        await UpdateShala(world.shalas, cities()).execute(world.me(anna), shala, patch)


async def test_an_edit_to_a_blank_name_is_refused(world: World) -> None:
    anna = world.person("1", "Anna")
    shala = world.shala(anna)

    with pytest.raises(InvalidShalaName):
        await UpdateShala(world.shalas, cities()).execute(
            world.me(anna), shala, ShalaPatch(name="  ")
        )


async def test_only_the_owner_deletes_and_it_takes_everyone_out(world: World) -> None:
    anna, dana, ash = world.person("1", "Anna"), world.person("4", "Dana"), world.person("2")
    shala = world.shala(anna)
    world.shalas.add_staff(shala, dana.id, ADMIN)
    world.shalas.add_student(shala, ash.id)

    with pytest.raises(NotAllowed):
        await DeleteShala(world.shalas).execute(world.me(dana), shala)
    await DeleteShala(world.shalas).execute(world.me(anna), shala)

    assert world.shalas.shalas == {}
    assert world.shalas.membership(shala, ash.id) is None
    assert world.notifier.staff_joined == []  # silent


# The student link: join and rotate


async def test_join_previews_only_the_shala_never_people(world: World) -> None:
    anna, ash = world.person("1", "Anna"), world.person("2", "Ash")
    world.shala(anna, name="Ashtanga Almaty", code=JOIN)

    preview = await PreviewShalaInvite(world.shalas).execute(
        world.me(ash), ShalaInvite(JOIN, False)
    )

    assert preview is not None
    assert (preview.state, preview.name, preview.city) == (
        JoinState.OPEN,
        "Ashtanga Almaty",
        "almaty",
    )
    assert "Anna" not in repr(preview)


@pytest.mark.parametrize(
    ("zone", "local"),
    [("Pacific/Kiritimati", date(2026, 11, 7)), ("Pacific/Honolulu", date(2026, 11, 6))],
)
async def test_join_stores_the_joiners_local_date(world: World, zone: str, local: date) -> None:
    """09:59 UTC on 7 Nov is 23:59 on the 7th in Kiritimati (+14) and on the 6th in
    Honolulu (-10): `joined_on` is the joiner's date, as `linked_on`."""
    world.clock.instant = datetime(2026, 11, 7, 9, 59, tzinfo=UTC)
    anna, ash = world.person("1", "Anna"), world.person("2", "Ash", zone=zone)
    shala = world.shala(anna, code=JOIN)

    joined = await JoinShala(world.shalas, world.clock, cities()).execute(world.me(ash), JOIN)

    assert joined is not None
    assert joined.created is True
    assert world.shalas.students_rows[(shala, ash.id)].joined_on == local


async def test_join_is_silent_and_creates_no_teacher_link(world: World) -> None:
    anna, ash = world.person("1", "Anna"), world.person("2", "Ash")
    world.shala(anna, code=JOIN)

    await JoinShala(world.shalas, world.clock, cities()).execute(world.me(ash), JOIN)

    assert world.notifier.staff_joined == []
    assert world.notifier.joined == []
    assert world.links.rows == {}


async def test_join_states(world: World) -> None:
    anna, ash, dana = world.person("1", "Anna"), world.person("2", "Ash"), world.person("4")
    shala = world.shala(anna, code=JOIN)
    world.shalas.add_staff(shala, dana.id, TEACHER)
    join = JoinShala(world.shalas, world.clock, cities())

    first = await join.execute(world.me(ash), JOIN)
    again = await join.execute(world.me(ash), JOIN)
    staff = await join.execute(world.me(dana), JOIN)
    unknown = await join.execute(world.me(ash), NEW_CODE)

    assert first is not None
    assert again is not None
    assert staff is not None
    assert [(r.created, r.state) for r in (first, again, staff)] == [
        (True, JoinState.OPEN),
        (False, JoinState.ALREADY),
        (False, JoinState.STAFF),
    ]
    assert unknown is None
    assert world.shalas.membership(shala, dana.id) is not None
    assert world.shalas.membership(shala, dana.id).staff  # type: ignore[union-attr]


@pytest.mark.parametrize("side", ["shala", "mine"])
async def test_join_at_a_cap_is_full(world: World, side: str) -> None:
    anna, ash = world.person("1", "Anna"), world.person("2", "Ash")
    shala = world.shala(anna, code=JOIN)
    if side == "shala":
        for _ in range(MAX_STUDENTS):
            world.shalas.add_student(shala, uuid4())
    else:
        for i in range(MAX_STUDENT_OF):
            other = world.shala(world.person(f"9{i}"), code=f"Other{i:011d}")
            world.shalas.add_student(other, ash.id)

    joined = await JoinShala(world.shalas, world.clock, cities()).execute(world.me(ash), JOIN)

    assert joined is not None
    assert (joined.created, joined.state) == (False, JoinState.FULL)
    assert world.shalas.membership(shala, ash.id) is None


async def test_staff_see_the_join_link_and_only_owner_or_admin_rotate(world: World) -> None:
    anna, dana, tom, ash = (
        world.person("1", "Anna"),
        world.person("4", "Dana"),
        world.person("5", "Tom"),
        world.person("2", "Ash"),
    )
    shala = world.shala(anna, code=JOIN)
    world.shalas.add_staff(shala, dana.id, ADMIN)
    world.shalas.add_staff(shala, tom.id, ASSISTANT)
    world.shalas.add_student(shala, ash.id)

    assert await GetJoinLink(world.shalas).execute(world.me(tom), shala) == JOIN
    with pytest.raises(NotAllowed):
        await GetJoinLink(world.shalas).execute(world.me(ash), shala)
    with pytest.raises(NotAllowed):
        await RotateJoinLink(world.shalas, world.codes(NEW_CODE)).execute(world.me(tom), shala)
    rotated = await RotateJoinLink(world.shalas, world.codes(NEW_CODE)).execute(
        world.me(dana), shala
    )

    assert rotated == NEW_CODE
    assert (
        await JoinShala(world.shalas, world.clock, cities()).execute(
            world.me(world.person("6")), JOIN
        )
        is None
    )  # the old link is dead
    assert world.shalas.membership(shala, ash.id) is not None  # members stay


# Staff invites: single use, 7 days, role-bound, confirmed by the invitee


async def test_create_staff_invite_expires_in_seven_days(world: World) -> None:
    anna = world.person("1", "Anna")
    shala = world.shala(anna)

    invite = await CreateStaffInvite(world.shalas, world.codes(STAFF_CODE), world.clock).execute(
        world.me(anna), shala, ASSISTANT
    )

    assert (invite.code, invite.expires_at) == (STAFF_CODE, NOW + STAFF_INVITE_TTL)
    assert world.shalas.invites[STAFF_CODE].role is ASSISTANT


@pytest.mark.parametrize(
    ("inviter_roles", "role", "allowed"),
    [
        ((ADMIN,), TEACHER, True),
        ((ADMIN,), OFFICE, True),
        ((ADMIN,), ADMIN, False),
        ((TEACHER,), TEACHER, False),
        ((OFFICE,), ASSISTANT, False),
    ],
)
async def test_who_may_invite_which_role(
    world: World, inviter_roles: tuple[ShalaRole, ...], role: ShalaRole, allowed: bool
) -> None:
    anna, dana = world.person("1", "Anna"), world.person("4", "Dana")
    shala = world.shala(anna)
    world.shalas.add_staff(shala, dana.id, *inviter_roles)
    create = CreateStaffInvite(world.shalas, world.codes(STAFF_CODE), world.clock)

    if allowed:
        await create.execute(world.me(dana), shala, role)
        assert STAFF_CODE in world.shalas.invites
    else:
        with pytest.raises(NotAllowed):
            await create.execute(world.me(dana), shala, role)
        assert world.shalas.invites == {}


async def test_the_pending_invite_cap(world: World) -> None:
    anna = world.person("1", "Anna")
    shala = world.shala(anna)
    for i in range(MAX_PENDING_STAFF_INVITES):
        world.shalas.add_invite(shala, f"Pend{i:012d}")

    with pytest.raises(CapReached):
        await CreateStaffInvite(world.shalas, world.codes(STAFF_CODE), world.clock).execute(
            world.me(anna), shala, TEACHER
        )


async def test_expired_invites_dont_count_toward_the_cap(world: World) -> None:
    anna = world.person("1", "Anna")
    shala = world.shala(anna)
    for i in range(MAX_PENDING_STAFF_INVITES):
        world.shalas.add_invite(shala, f"Pend{i:012d}", expires_at=NOW - timedelta(seconds=1))

    invite = await CreateStaffInvite(world.shalas, world.codes(STAFF_CODE), world.clock).execute(
        world.me(anna), shala, TEACHER
    )

    assert invite.code == STAFF_CODE


async def _accept(world: World, who: Account, code: str = STAFF_CODE):
    use_case = AcceptStaffInvite(world.shalas, world.notifier, world.clock, cities())
    return await use_case.execute(world.me(who), code)


async def test_accept_makes_staff_and_notes_the_inviter_silently_in_their_language(
    world: World,
) -> None:
    anna = world.person("1001", "Anna", locale="ru")
    boris = world.person("2", "Boris")
    shala = world.shala(anna, name="Ashtanga Almaty")
    world.shalas.add_invite(shala, STAFF_CODE, ASSISTANT)

    accepted = await _accept(world, boris)

    assert accepted is not None
    assert (accepted.created, accepted.role, accepted.was_student) == (True, ASSISTANT, False)
    assert world.shalas.membership(shala, boris.id).roles == frozenset({ASSISTANT})  # type: ignore[union-attr]
    assert world.shalas.staff[(shala, boris.id)].joined_on == date(2026, 11, 7)
    assert world.notifier.staff_joined == [
        (Recipient("1001", "ru"), "Boris", "Ashtanga Almaty", ASSISTANT)
    ]
    assert world.links.rows == {}  # no teacher link either


async def test_a_staff_link_works_once(world: World) -> None:
    anna, boris, clara = world.person("1", "Anna"), world.person("2"), world.person("3")
    shala = world.shala(anna)
    world.shalas.add_invite(shala, STAFF_CODE)

    first = await _accept(world, boris)
    second = await _accept(world, clara)

    assert first is not None
    assert second is None
    assert world.shalas.membership(shala, clara.id) is None
    assert STAFF_CODE not in world.shalas.invites
    assert len(world.notifier.staff_joined) == 1


async def test_a_double_tap_accepts_once(world: World) -> None:
    import asyncio

    anna, boris = world.person("1", "Anna"), world.person("2")
    shala = world.shala(anna)
    world.shalas.add_invite(shala, STAFF_CODE)

    results = await asyncio.gather(_accept(world, boris), _accept(world, boris))

    assert sorted(r is None for r in results) == [False, True]
    assert len(world.notifier.staff_joined) == 1
    assert world.shalas.staff_of(shala) == [anna.id, boris.id]


@pytest.mark.parametrize(
    ("after", "works"),
    [
        (STAFF_INVITE_TTL - timedelta(seconds=1), True),
        (STAFF_INVITE_TTL, False),
        (STAFF_INVITE_TTL + timedelta(days=1), False),
    ],
)
async def test_a_staff_link_expires(world: World, after: timedelta, works: bool) -> None:
    anna, boris = world.person("1", "Anna"), world.person("2")
    shala = world.shala(anna)
    world.shalas.add_invite(shala, STAFF_CODE, expires_at=NOW + STAFF_INVITE_TTL)
    world.clock.instant = NOW + after

    preview = await PreviewShalaInvite(world.shalas).execute(
        world.me(boris), ShalaInvite(STAFF_CODE, True)
    )
    accepted = await _accept(world, boris)

    assert (preview is not None, accepted is not None) == (works, works)
    assert (world.shalas.membership(shala, boris.id) is not None) is works


@pytest.mark.parametrize("how", ["removed", "demoted"])
async def test_a_staff_link_dies_with_the_inviters_rights(world: World, how: str) -> None:
    """Review fix: a manager's pending link stops working once they can't grant the role."""
    anna, dana, boris = world.person("1", "Anna"), world.person("4", "Dana"), world.person("2")
    shala = world.shala(anna)
    world.shalas.add_staff(shala, dana.id, ADMIN)
    world.shalas.add_invite(shala, STAFF_CODE, TEACHER, by=dana.id)
    if how == "removed":
        await RemoveStaff(world.shalas).execute(world.me(anna), shala, dana.id)
    else:
        await SetStaffRoles(world.shalas).execute(
            world.me(anna), shala, dana.id, frozenset({TEACHER})
        )

    preview = await PreviewShalaInvite(world.shalas).execute(
        world.me(boris), ShalaInvite(STAFF_CODE, True)
    )
    accepted = await _accept(world, boris)

    assert (preview, accepted) == (None, None)
    assert world.shalas.membership(shala, boris.id) is None
    assert world.notifier.staff_joined == []


async def test_a_student_who_accepts_becomes_staff(world: World) -> None:
    anna, ash = world.person("1", "Anna"), world.person("2", "Ash")
    shala = world.shala(anna)
    world.shalas.add_student(shala, ash.id)
    world.shalas.add_invite(shala, STAFF_CODE, TEACHER)

    accepted = await _accept(world, ash)

    assert accepted is not None
    assert accepted.was_student is True
    assert (shala, ash.id) not in world.shalas.students_rows
    assert world.shalas.membership(shala, ash.id).staff  # type: ignore[union-attr]


async def test_staff_accepting_another_staff_link_stays_as_they_are(world: World) -> None:
    anna, dana = world.person("1", "Anna"), world.person("4")
    shala = world.shala(anna)
    world.shalas.add_staff(shala, dana.id, OFFICE)
    world.shalas.add_invite(shala, STAFF_CODE, TEACHER)

    accepted = await _accept(world, dana)

    assert accepted is not None
    assert (accepted.created, accepted.state) == (False, JoinState.STAFF)
    assert world.shalas.membership(shala, dana.id).roles == frozenset({OFFICE})  # type: ignore[union-attr]
    assert STAFF_CODE in world.shalas.invites  # not spent
    assert world.notifier.staff_joined == []


async def test_the_staff_cap(world: World) -> None:
    anna, boris = world.person("1", "Anna"), world.person("2")
    shala = world.shala(anna)
    for _ in range(MAX_STAFF - 1):
        world.shalas.add_staff(shala, uuid4(), TEACHER)
    world.shalas.add_invite(shala, STAFF_CODE)

    accepted = await _accept(world, boris)

    assert accepted is not None
    assert (accepted.created, accepted.state) == (False, JoinState.FULL)
    assert world.shalas.membership(shala, boris.id) is None


async def test_the_staff_preview_names_the_inviter_and_role_only(world: World) -> None:
    anna, boris = world.person("1", "Anna"), world.person("2", "Boris")
    shala = world.shala(anna, name="Ashtanga Almaty")
    world.shalas.add_staff(shala, world.person("7", "Secret Staff").id, TEACHER)
    world.shalas.add_student(shala, world.person("8", "Secret Student").id)
    world.shalas.add_invite(shala, STAFF_CODE, OFFICE)

    preview = await PreviewShalaInvite(world.shalas).execute(
        world.me(boris), ShalaInvite(STAFF_CODE, True)
    )

    assert preview is not None
    assert (preview.state, preview.name, preview.role, preview.inviter_name) == (
        JoinState.OPEN,
        "Ashtanga Almaty",
        OFFICE,
        "Anna",
    )
    assert "Secret" not in repr(preview)


# Roles, removal and leaving: silent, hard deletes


async def test_set_roles_per_policy(world: World) -> None:
    anna, dana, tom = world.person("1", "Anna"), world.person("4", "Dana"), world.person("5")
    shala = world.shala(anna)
    world.shalas.add_staff(shala, dana.id, ADMIN)
    world.shalas.add_staff(shala, tom.id, TEACHER)
    set_roles = SetStaffRoles(world.shalas)

    card = await set_roles.execute(world.me(dana), shala, tom.id, frozenset({TEACHER, OFFICE}))
    with pytest.raises(NotAllowed):
        await set_roles.execute(world.me(dana), shala, tom.id, frozenset({ADMIN}))
    with pytest.raises(NotAllowed):
        await set_roles.execute(world.me(tom), shala, dana.id, frozenset())
    with pytest.raises(NotAllowed):
        await set_roles.execute(world.me(dana), shala, anna.id, frozenset({TEACHER}))

    assert {s.id: s.roles for s in card.staff}[tom.id] == frozenset({TEACHER, OFFICE})
    assert world.shalas.membership(shala, dana.id).roles == frozenset({ADMIN})  # type: ignore[union-attr]


async def test_remove_and_leave_staff(world: World) -> None:
    anna, dana, tom = world.person("1", "Anna"), world.person("4", "Dana"), world.person("5")
    shala = world.shala(anna)
    world.shalas.add_staff(shala, dana.id, ADMIN)
    world.shalas.add_staff(shala, tom.id, TEACHER)
    remove = RemoveStaff(world.shalas)

    await remove.execute(world.me(dana), shala, tom.id)  # an admin removes a teacher
    await remove.execute(world.me(dana), shala, tom.id)  # idempotent
    await remove.execute(world.me(dana), shala, dana.id)  # leaves

    assert world.shalas.staff_of(shala) == [anna.id]
    assert world.notifier.staff_joined == []


async def test_the_owner_cannot_leave(world: World) -> None:
    anna = world.person("1", "Anna")
    shala = world.shala(anna)

    with pytest.raises(NotAllowed):
        await RemoveStaff(world.shalas).execute(world.me(anna), shala, anna.id)
    assert world.shalas.staff_of(shala) == [anna.id]


async def test_an_admin_cannot_remove_another_admin(world: World) -> None:
    anna, dana, eva = world.person("1", "Anna"), world.person("4"), world.person("5")
    shala = world.shala(anna)
    world.shalas.add_staff(shala, dana.id, ADMIN)
    world.shalas.add_staff(shala, eva.id, ADMIN)

    with pytest.raises(NotAllowed):
        await RemoveStaff(world.shalas).execute(world.me(dana), shala, eva.id)
    await RemoveStaff(world.shalas).execute(world.me(anna), shala, eva.id)

    assert world.shalas.staff_of(shala) == [anna.id, dana.id]


async def test_remove_and_leave_as_a_student(world: World) -> None:
    anna, office, ash, bea = (
        world.person("1", "Anna"),
        world.person("4"),
        world.person("2"),
        world.person("3"),
    )
    shala = world.shala(anna)
    world.shalas.add_staff(shala, office.id, OFFICE)
    world.shalas.add_student(shala, ash.id)
    world.shalas.add_student(shala, bea.id)
    remove = RemoveShalaStudent(world.shalas)

    with pytest.raises(NotAllowed):
        await remove.execute(world.me(ash), shala, bea.id)  # students can't remove students
    await remove.execute(world.me(office), shala, bea.id)
    await remove.execute(world.me(ash), shala, ash.id)  # leaves

    assert world.shalas.students_of(shala) == []
    assert world.notifier.staff_joined == []


async def test_leaving_a_shala_never_touches_teacher_links(world: World) -> None:
    anna, ash = world.person("1", "Anna"), world.person("2")
    shala = world.shala(anna)
    world.shalas.add_student(shala, ash.id)
    world.links.add(ash.id, anna.id)

    await RemoveShalaStudent(world.shalas).execute(world.me(ash), shala, ash.id)

    assert world.links.teachers_of(ash.id) == [anna.id]


# Privacy: a shala grants no log access


async def test_can_view_activity_stays_false_for_shala_co_members(world: World) -> None:
    anna, dana, ash = world.person("1", "Anna"), world.person("4"), world.person("2")
    shala = world.shala(anna)
    world.shalas.add_staff(shala, dana.id, TEACHER)
    world.shalas.add_student(shala, ash.id)
    # No teacher_link exists: a staff member holding a forged link object for someone else's
    # teacher still isn't its teacher.
    forged = StudentLink(anna.id, ash.id, "Ash", "Asia/Almaty", "en", date(2026, 11, 1))

    for viewer in (dana, anna, ash):
        if viewer.id == forged.teacher_id:
            continue
        assert can_view_activity(world.me(viewer).account, forged) is False
        assert can_view_last_asana(world.me(viewer).account, forged) is False


def test_no_shala_use_case_reads_a_log() -> None:
    """`application/shalas.py` imports no day, practice, progression, check-in or diary port."""
    import tristhana.application.shalas as module

    tree = ast.parse(Path(module.__file__).read_text())
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    banned = {
        "tristhana.application.ports.days",
        "tristhana.application.ports.practice",
        "tristhana.application.ports.progression",
        "tristhana.application.ports.check_in",
        "tristhana.application.ports.diary",
        "tristhana.application.ports.teacher_view",
        "tristhana.application.days",
        "tristhana.application.practice",
        "tristhana.application.progression",
    }
    assert imported & banned == set()


async def test_no_shala_use_case_touches_a_log(world: World) -> None:
    """The fakes count calls: a whole join/accept/card/leave round reads only `shalas`."""
    anna, ash = world.person("1", "Anna"), world.person("2")
    shala = world.shala(anna, code=JOIN)
    world.shalas.add_invite(shala, STAFF_CODE)

    await JoinShala(world.shalas, world.clock, cities()).execute(world.me(ash), JOIN)
    await GetShala(world.shalas).execute(world.me(ash), shala)
    await _accept(world, world.person("3"))
    await RemoveShalaStudent(world.shalas).execute(world.me(ash), shala, ash.id)

    assert set(world.shalas.reads) <= {
        "join",
        "card",
        "accept_staff",
        "remove_student",
        "preview",
        "preview_staff",
    }


# Moon (MD-02 with the shala step)


async def test_set_moon_location_follow_shala_stores_the_sentinel(world: World) -> None:
    ash = world.person("2", "Ash")

    saved = await SetMoonLocation(cities(), world.accounts).execute(
        world.me(ash), None, follow="shala"
    )

    assert saved.moon_location == FOLLOW_SHALA


async def test_set_moon_location_follow_defaults_to_the_teacher(world: World) -> None:
    ash = world.person("2", "Ash")

    saved = await SetMoonLocation(cities(), world.accounts).execute(world.me(ash), None)

    assert saved.moon_location == FOLLOW_TEACHER


async def test_set_moon_location_with_a_slug_ignores_follow(world: World) -> None:
    ash = world.person("2", "Ash")

    saved = await SetMoonLocation(cities(), world.accounts).execute(
        world.me(ash), "moscow", follow="shala"
    )

    assert saved.moon_location == "moscow"


async def test_the_account_load_carries_the_main_shala(world: World) -> None:
    anna, ash = world.person("1", "Anna", moon="almaty"), world.person("2", "Ash")
    shala = world.shala(anna, "moscow", name="Moscow Shala")
    world.shalas.add_student(shala, ash.id)
    world.links.add(ash.id, anna.id)  # the main teacher staffs the shala: Q108

    me = world.me(ash).account

    assert me.shala is not None
    assert (me.shala.id, me.shala.name, me.shala.moon_city) == (shala, "Moscow Shala", "moscow")
    assert (me.shala.staff, me.shala.teacher_on_staff) == (False, True)


async def test_joining_reports_a_moved_moon_city(world: World) -> None:
    anna, ash = world.person("1", "Anna"), world.person("2", "Ash")
    world.shala(anna, "moscow", code=JOIN)

    joined = await JoinShala(world.shalas, world.clock, cities()).execute(world.me(ash), JOIN)

    assert joined is not None
    assert joined.moon is not None
    assert (joined.moon.city.slug, joined.moon.source) == ("moscow", MoonSource.SHALA)


async def test_joining_with_a_chosen_city_moves_nothing(world: World) -> None:
    anna, ash = world.person("1", "Anna"), world.person("2", "Ash", moon="minsk")
    world.shala(anna, "moscow", code=JOIN)

    joined = await JoinShala(world.shalas, world.clock, cities()).execute(world.me(ash), JOIN)

    assert joined is not None
    assert joined.moon is None


async def test_remove_teacher_reports_the_shala_city_it_falls_back_to(world: World) -> None:
    """`_moved` passes the shala input: without the teacher, the student's shala, not Mysuru."""
    anna = world.person("1", "Anna", moon="almaty")
    ash = world.person("2", "Ash")
    other = world.person("3", "Owner")
    shala = world.shala(other, "moscow")
    world.shalas.add_student(shala, ash.id)
    world.links.add(ash.id, anna.id)
    assert world.me(ash).account.shala is not None

    moved = await RemoveTeacher(world.links, cities()).execute(world.me(ash), anna.id)

    assert moved is not None
    assert (moved.city.slug, moved.source) == ("moscow", MoonSource.SHALA)


async def test_a_staff_teachers_first_student_gets_no_keep_offer(world: World) -> None:
    """A never-chose teacher on staff already follows the shala; a student changes nothing,
    so `_keep_offer` (with the shala input) offers nothing."""
    from tests.moon_follow_fakes import KeepNotifier

    lena = world.person("1001", "Лена")
    owner = world.person("9", "Owner")
    shala = world.shala(owner, "moscow")
    world.shalas.add_staff(shala, lena.id, TEACHER)
    # Without the shala, Lena's first student would end her inheriting Guru's Almaty: Keep.
    world.links.add(lena.id, world.person("5", "Guru", moon="almaty").id)
    world.links.codes[lena.id] = "aB3dE6gH9jK2mN5p"
    notifier = KeepNotifier()
    ash = world.person("2", "Ash")

    await AcceptInvite(world.links, notifier, world.clock, cities()).execute(
        world.me(ash), "aB3dE6gH9jK2mN5p"
    )

    assert notifier.offers == [None]


async def test_staff_accept_offers_keep_to_a_never_chose_teacher(world: World) -> None:
    """Q98: a never-chose person with students accepts; their students won't inherit the
    shala city (one hop), so the screen offers to keep it as their own (`m1:k:<slug>`)."""
    anna = world.person("1", "Anna")
    boris = world.person("2", "Boris")
    shala = world.shala(anna, "moscow")
    world.links.add(world.person("3", "Student").id, boris.id)  # Boris teaches
    world.shalas.add_invite(shala, STAFF_CODE, TEACHER)

    accepted = await _accept(world, boris)

    assert accepted is not None
    assert accepted.keep is not None
    assert accepted.keep.slug == "moscow"


async def test_accepting_a_second_staff_link_keeps_the_older_staff_shala(world: World) -> None:
    """Review fix: staff at A (older); accepting B, where the main teacher is staff, moves
    nothing: staff rows rank by age only, so no moon line and no Keep offer."""
    guru = world.person("5", "Guru", moon="almaty")
    boris = world.person("2", "Boris")
    owner = world.person("1", "Owner")
    a = world.shala(owner, "kyiv", name="A", code="AAAAAAAAAAAAAAAA")
    b = world.shala(owner, "moscow", name="B", code="BBBBBBBBBBBBBBBB")
    world.shalas.add_staff(a, boris.id, TEACHER)
    world.shalas.add_staff(b, guru.id, TEACHER)
    world.links.add(boris.id, guru.id)
    world.links.add(world.person("3", "Student").id, boris.id)  # Boris teaches
    world.shalas.add_invite(b, STAFF_CODE, TEACHER)

    accepted = await _accept(world, boris)

    assert accepted is not None
    assert (accepted.moon, accepted.keep) == (None, None)
    assert world.shalas.main_of(boris.id).id == a  # type: ignore[union-attr]


@pytest.mark.parametrize(("moon", "teaches"), [(None, False), ("minsk", True)])
async def test_staff_accept_offers_no_keep_otherwise(
    world: World, moon: str | None, teaches: bool
) -> None:
    anna, boris = world.person("1", "Anna"), world.person("2", "Boris", moon=moon)
    shala = world.shala(anna, "moscow")
    if teaches:
        world.links.add(world.person("3", "Student").id, boris.id)
    world.shalas.add_invite(shala, STAFF_CODE, TEACHER)

    accepted = await _accept(world, boris)

    assert accepted is not None
    assert accepted.keep is None


async def test_the_tick_candidates_carry_the_shala_input() -> None:
    from tests.shala_fakes import shala_storage
    from tristhana.domain.accounts import moon_follow_of
    from tristhana.domain.moon import moon_follow
    from tristhana.domain.notifications import DEFAULTS

    storage = shala_storage()
    anna = person(storage, "1", "Anna", moon="almaty")
    ash = person(storage, "2", "Ash")
    shala = storage.shalas.add_shala(anna.id, city="moscow").id
    storage.shalas.add_student(shala, ash.id)
    storage.teacher_links.add(ash.id, anna.id)
    for who in (anna, ash):
        await storage.notifications.save(who.id, DEFAULTS)

    candidates = {
        c.account_id: c
        for c in await storage.notifications.candidates(
            NOW - timedelta(days=12), NOW.date(), DEFAULTS
        )
    }

    for who in (anna, ash):
        c = candidates[who.id]
        rule = moon_follow(c.location, c.teaches, c.teacher, c.shala, cities())
        accounts = storage.accounts
        assert isinstance(accounts, ShalaAccounts)
        loaded = moon_follow_of(accounts.inputs(accounts.accounts[who.id]), cities())
        assert rule.city.slug == loaded.city.slug
    assert candidates[ash.id].shala_teacher_on_staff is True
    assert candidates[anna.id].shala_staff is True
