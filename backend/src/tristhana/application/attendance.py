"""Class attendance (SC-05, ADR-0039): both adapters use these.

A mark is about presence at one occurrence, never a log entry: no use case here reads or writes
a day, a practice, a rest, a check-in, the diary or progression (an import-linter contract keeps
it so). The occurrence is expanded in the domain from one read, so a forged key can only fail.
Today is the class zone's local date.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from tristhana.application.classes import (
    MyRow,
    Only,
    Teaching,
    class_zone,
    my_rows,
    occurrences_of,
    zone_of,
)
from tristhana.application.policies import (
    NotAllowed,
    NotFound,
    Principal,
    can_claim_attendance,
    can_take_attendance,
)
from tristhana.application.ports.attendance import (
    AttendanceRepository,
    AttendanceTarget,
    RosterPerson,
)
from tristhana.application.ports.classes import ScheduleRepository
from tristhana.application.ports.storage import Clock
from tristhana.domain.attendance import (
    API_PAGE,
    BACK_DAYS,
    MAX_DELTA,
    MY_LIST,
    AttendanceState,
    Counts,
    InvalidAttendance,
    NotAttendable,
    attendable,
    claim_state,
    offers_log_day,
    snapshot,
)
from tristhana.domain.classes import Occurrence
from tristhana.domain.days import local_today
from tristhana.domain.moon import Cities

_REACH = timedelta(days=12)  # a move (±6) then a swap (±6) from the rule date


@dataclass(frozen=True, slots=True)
class Found:
    target: AttendanceTarget
    occurrence: Occurrence
    zone: str  # the class's IANA zone
    city: str  # the class's city slug


def _find(target: AttendanceTarget, cities: Cities, class_id: UUID, key: date) -> Found | None:
    w = target.window
    for o in occurrences_of(w, cities, key - _REACH, key + _REACH):
        if o.class_id == class_id and o.key == key:
            slug = next((c.city for c in w.classes if c.id == class_id and c.city), None)
            return Found(target, o, class_zone(w, cities, class_id), slug or w.city)
    return None


def my_day(o: Occurrence, principal: Principal, zone: str) -> date:
    """My local date of the instant (the day card "Log this day" opens): a Berlin 21:30 online
    class is the next day for an Almaty viewer. No known zone: the class zone's."""
    mine = principal.account.timezone or zone
    return o.starts_at.astimezone(ZoneInfo(mine)).date()


@dataclass(frozen=True, slots=True)
class MyMark:
    class_id: UUID
    key: date
    state: AttendanceState
    occurrence: Occurrence
    zone: str
    shala_name: str
    day: date  # my local date of the instant
    log_day: bool  # offer "🧘 Log this day" (Q196)


class ClaimAttendance:
    def __init__(self, attendance: AttendanceRepository, clock: Clock, cities: Cities) -> None:
        self._attendance, self._clock, self._cities = attendance, clock, cities

    async def execute(self, principal: Principal, class_id: UUID, key: date) -> MyMark:
        """Raises `NotFound` (not a member, unknown class), `NotAttendable`. Two statements."""
        me = principal.account.id
        target = await self._attendance.occurrence(me, class_id, key)
        if target is None or not can_claim_attendance(target.window.me):
            raise NotFound
        found = _find(target, self._cities, class_id, key)
        if found is None or not attendable(found.occurrence, found.zone, self._clock.now()):
            raise NotAttendable
        m = target.window.me
        snap = snapshot(found.occurrence, target.window.shala_id, found.zone)
        written = await self._attendance.claim(me, snap, claim_state(can_take_attendance(m)))
        if written.me is None:
            raise NotFound
        if not written.done or written.value is None:
            raise NotAllowed
        o = found.occurrence
        return MyMark(
            class_id,
            key,
            written.value,
            o,
            found.zone,
            target.window.name,
            my_day(o, principal, found.zone),
            offers_log_day(o.type),
        )


class RemoveMyAttendance:
    def __init__(self, attendance: AttendanceRepository) -> None:
        self._attendance = attendance

    async def execute(self, principal: Principal, class_id: UUID, key: date) -> None:
        """My own row only: no membership check, so a race with a leave can't fail."""
        await self._attendance.remove(principal.account.id, class_id, key)


@dataclass(frozen=True, slots=True)
class Roster:
    shala_id: UUID
    shala_name: str
    occurrence: Occurrence
    zone: str
    city: str
    attendable: bool
    counts: Counts
    people: tuple[RosterPerson, ...]
    more: bool
    offset: int


class GetRoster:
    def __init__(self, attendance: AttendanceRepository, clock: Clock, cities: Cities) -> None:
        self._attendance, self._clock, self._cities = attendance, clock, cities

    async def execute(
        self,
        principal: Principal,
        class_id: UUID,
        key: date,
        q: str | None = None,
        offset: int = 0,
        limit: int = API_PAGE,
        shala: UUID | None = None,
    ) -> Roster:
        """`shala`: the path's (the API), checked against the class's. Raises `NotFound`,
        `NotAllowed` (a student). One read."""
        q = (q or "").strip() or None
        read = await self._attendance.roster(
            principal.account.id, class_id, key, q, max(0, offset), max(1, min(limit, API_PAGE))
        )
        if read is None or (shala is not None and read.target.window.shala_id != shala):
            raise NotFound
        w = read.target.window
        if not can_take_attendance(w.me):
            raise NotAllowed
        found = _find(read.target, self._cities, class_id, key)
        if found is None:
            raise NotFound
        return Roster(
            w.shala_id,
            w.name,
            found.occurrence,
            found.zone,
            found.city,
            attendable(found.occurrence, found.zone, self._clock.now()),
            read.counts,
            read.people,
            read.more,
            max(0, offset),
        )


class MarkAttendance:
    def __init__(self, attendance: AttendanceRepository, clock: Clock, cities: Cities) -> None:
        self._attendance, self._clock, self._cities = attendance, clock, cities

    async def execute(
        self,
        principal: Principal,
        class_id: UUID,
        key: date,
        present: Sequence[UUID] = (),
        removed: Sequence[UUID] = (),
        confirm_claims: bool = False,
        shala: UUID | None = None,
    ) -> Counts:
        """Deltas: `present` → confirmed, `removed` → unmarked. Raises `InvalidAttendance`,
        `NotAttendable`, `NotFound`, `NotAllowed`. Two statements."""
        yes, no = list(dict.fromkeys(present)), list(dict.fromkeys(removed))
        if len(yes) > MAX_DELTA or len(no) > MAX_DELTA or set(yes) & set(no):
            raise InvalidAttendance
        me = principal.account.id
        target = await self._attendance.occurrence(me, class_id, key)
        if target is None or (shala is not None and target.window.shala_id != shala):
            raise NotFound
        if not can_take_attendance(target.window.me):
            raise NotAllowed
        found = _find(target, self._cities, class_id, key)
        if found is None or not attendable(found.occurrence, found.zone, self._clock.now()):
            raise NotAttendable
        snap = snapshot(found.occurrence, target.window.shala_id, found.zone)
        written = await self._attendance.mark(me, snap, yes, no, confirm_claims)
        if written.me is None:
            raise NotFound
        if not written.done or written.value is None:
            raise NotAllowed
        if not written.value.valid:
            raise InvalidAttendance
        return written.value.counts


@dataclass(frozen=True, slots=True)
class AttendRow:
    row: MyRow
    shala_name: str


@dataclass(frozen=True, slots=True)
class AttendList:
    zone: str  # mine (or my first shala's)
    zone_known: bool
    rows: tuple[AttendRow, ...]
    city: str | None  # whose name labels the zone: my home city, or that shala's
    today: date  # in `zone` (the label's offset)


class ListAttendable:
    """The bot's "🙋 I was there…" list (any member) and the staff "📋 Attendance…" picker
    (`staff=True`): the started, attendable occurrences of the last 7 days, at most 10. One
    read (`member_windows`, which carries my marks and the staff counts)."""

    def __init__(self, schedule: ScheduleRepository, clock: Clock, cities: Cities) -> None:
        self._schedule, self._clock, self._cities = schedule, clock, cities

    async def execute(self, principal: Principal, staff: bool = False) -> AttendList:
        account, now = principal.account, self._clock.now()
        me = account.id
        known = account.timezone
        utc = now.date()  # every zone's today is within a day of it
        found = await self._schedule.member_windows(
            me, utc - timedelta(days=BACK_DAYS + 3), utc + timedelta(days=3), staff_only=staff
        )
        windows = found.windows
        zone = known or (zone_of(self._cities, windows[0].city) if windows else "UTC")
        today = local_today(now, zone)
        first, end = today - timedelta(days=BACK_DAYS + 1), today + timedelta(days=1)
        rows, refs, _ = my_rows(found, self._cities, zone, first, end, me, Only.ALL, now)
        names = {r.id: r.name for r in refs}
        picked = [r for r in rows if r.can_claim and (not staff or r.counts is not None)]
        if staff:
            mine = {Teaching.TEACHING, Teaching.COVERING}
            picked.sort(key=lambda r: (r.role not in mine, -r.occurrence.starts_at.timestamp()))
        else:
            picked.sort(key=lambda r: -r.occurrence.starts_at.timestamp())
        return AttendList(
            zone,
            known is not None,
            tuple(AttendRow(r, names[r.shala_id]) for r in picked[:MY_LIST]),
            account.home_city if known else (windows[0].city if windows else None),
            today,
        )


@dataclass(frozen=True, slots=True)
class AttendanceUseCases:
    claim: ClaimAttendance
    remove: RemoveMyAttendance
    roster: GetRoster
    mark: MarkAttendance
    listing: ListAttendable
