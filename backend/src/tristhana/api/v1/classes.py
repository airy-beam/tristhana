"""Shala classes (SC-02, ADR-0034). As SC-01: non-members get 404 `not_found` exactly like an
unknown id; a member without the right gets 403 `not_allowed`; every answer is `no-store`.
Times are "HH:MM" wall clock in the class zone; `starts_at` is the UTC instant (the client
formats "your time"). 1:1 classes reach staff only (Q121).
"""

import datetime as dt
from collections.abc import Awaitable, Mapping
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from tristhana.api.deps import CurrentPrincipal, shalas
from tristhana.api.errors import ApiError, ErrorCode, error_responses
from tristhana.application.classes import (
    MY_DAYS,
    BadWindow,
    ClassUseCases,
    MyRow,
    MySchedule,
    Only,
    Schedule,
    Teaching,
)
from tristhana.application.policies import NotAllowed, NotFound, Principal
from tristhana.application.ports.classes import ClassDraft, StoredClass
from tristhana.application.ports.shalas import CapReached
from tristhana.application.shalas import ShalaUseCases
from tristhana.domain.classes import (
    TITLE_MAX,
    WINDOW_MAX,
    ClassSeries,
    ClassType,
    InvalidClass,
    Occurrence,
    Override,
    OverrideStatus,
    to_rrule,
)
from tristhana.domain.moon import UnknownLocation

router = APIRouter(tags=["classes"], responses=error_responses(401, 503))

_NO_STORE = {"Cache-Control": "no-store"}
type ClassTypeName = Literal[
    "mysore", "led", "private", "conference", "pranayama", "chanting", "workshop"
]
type Weekday = Annotated[int, Field(ge=1, le=7)]
type HourMinute = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]


def _classes(request_shalas: Annotated[ShalaUseCases, Depends(shalas)]) -> ClassUseCases:
    assert request_shalas.classes is not None  # noqa: S101 - always wired by the app
    return request_shalas.classes


UseCases = Annotated[ClassUseCases, Depends(_classes)]


class ClassTeacherOut(BaseModel):
    id: UUID
    name: str | None


class ScheduleDayOut(BaseModel):
    date: dt.date
    moon: bool = Field(description="🌙 shows under every moon policy")
    day_off: bool
    swap_from: dt.date | None = Field(description="This day holds that date's moon-day classes")


class OccurrenceOut(BaseModel):
    class_id: UUID
    key: date = Field(description="The rule's date: the occurrence's id within its class")
    on: date
    start: str = Field(description="HH:MM in the class zone")
    end: str
    starts_at: datetime
    type: ClassTypeName
    title: str | None
    online: bool
    teacher: ClassTeacherOut | None
    substitute: bool
    cancelled: Literal["moon", "closure", "cancelled"] | None
    moved: bool
    swapped_from: date | None
    held: bool = Field(description="Staff chose hold anyway: send `held` with a later change")
    usual_teacher: ClassTeacherOut | None = Field(description="The class's own teacher")


class ScheduleOccurrenceOut(OccurrenceOut):
    moon: bool = Field(description="On a moon date of its shala's calendar, whatever the policy")
    swapped_to: date | None = Field(
        description="Cancelled here, held on this date instead (My schedule only; null on a"
        " shala's schedule, whose day rows name the swap)"
    )


class MyClassOut(OccurrenceOut):
    role: Literal["teaching", "covering", "covered"] = Field(
        description="Mine as planned; I substitute (`usual_teacher` is whose); someone"
        " substitutes for me (`teacher` is who)"
    )


class MyShalaClassesOut(BaseModel):
    shala_id: UUID
    name: str
    zone: str = Field(description="The shala's IANA zone")
    today: date = Field(description="The shala's")
    classes: list[MyClassOut]


class ScheduleOut(BaseModel):
    zone: str = Field(description="The shala's IANA zone")
    city: str
    moon_policy: Literal["closed", "pranayama", "open"]
    days_off: list[int] | None
    days: list[ScheduleDayOut]
    occurrences: list[ScheduleOccurrenceOut]
    closures: list["ClosureOut"] = Field(description="Closures touching the window")


class MyRowOut(ScheduleOccurrenceOut):
    shala_id: UUID
    zone: str = Field(description="The class's IANA zone (the second label)")
    city: str = Field(description="The class's city slug")
    role: Literal["teaching", "covering", "covered"] | None
    my_teacher: bool = Field(description="One of my linked teachers teaches it, or is covered")
    planned: str | None = Field(description='HH:MM: the rule\'s start, for "moved from …"')


class MyDayOut(BaseModel):
    date: date
    my_moon: bool = Field(description="A moon day of my own moon calendar")


class ScheduleShalaOut(BaseModel):
    id: UUID
    name: str
    city: str
    zone: str
    staff: bool


class ShiftOut(BaseModel):
    zone: str
    city: str
    shala_ids: list[UUID]
    on: date
    minutes: int = Field(description="> 0: the class is that much earlier for me; < 0: later")


class MyScheduleOut(BaseModel):
    zone: str = Field(description="The zone times are shown in: mine, or my first shala's")
    zone_known: bool
    today: date
    moon_city: str
    days: list[MyDayOut]
    shalas: list[ScheduleShalaOut]
    has_teachers: bool
    is_staff: bool
    shifts: list[ShiftOut]
    occurrences: list[MyRowOut]


class ClassIn(BaseModel):
    type: ClassTypeName
    title: Annotated[str, Field(max_length=TITLE_MAX)] | None = None
    online: bool = False
    city: str | None = Field(default=None, description="Online classes only; null = the shala's")
    teacher_id: UUID | None = None
    start: HourMinute
    minutes: Annotated[int, Field(ge=15, le=480)]
    weekdays: list[Weekday] = Field(description="ISO, Monday = 1; empty = one date")
    every: Annotated[int, Field(ge=1, le=4)] = 1
    starts_on: date
    ends_on: date | None = None


class ClassPatchIn(BaseModel):
    """Fields not sent stay. `from`: the change applies from that date (a new series)."""

    model_config = ConfigDict(populate_by_name=True)

    type: ClassTypeName | None = None
    title: Annotated[str, Field(max_length=TITLE_MAX)] | None = None
    online: bool | None = None
    city: str | None = None
    teacher_id: UUID | None = None
    start: HourMinute | None = None
    minutes: Annotated[int, Field(ge=15, le=480)] | None = None
    weekdays: list[Weekday] | None = None
    every: Annotated[int, Field(ge=1, le=4)] | None = None
    starts_on: date | None = None
    ends_on: date | None = None
    from_date: date | None = Field(default=None, alias="from")


class ClassOut(BaseModel):
    id: UUID
    type: ClassTypeName
    title: str | None
    online: bool
    city: str | None
    teacher_id: UUID | None
    start: str
    minutes: int
    weekdays: list[int]
    every: int
    starts_on: date
    ends_on: date | None
    rrule: str | None = Field(description="RFC 5545 RRULE (weekly), null for one date")


class OccurrenceIn(BaseModel):
    status: Literal["cancelled", "held"] | None = None
    on: date | None = Field(default=None, description="Move to this date (±6 days)")
    start: HourMinute | None = None
    minutes: Annotated[int, Field(ge=15, le=480)] | None = None
    teacher_id: UUID | None = Field(default=None, description="A substitute")


class ClosureIn(BaseModel):
    start: date
    end: date


class ClosureOut(ClosureIn):
    id: UUID


class SwapIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_date: date = Field(alias="from")
    to: date


class SwapOut(SwapIn):
    pass


def _fail(status: int, code: ErrorCode) -> ApiError:
    return ApiError(status, code, _NO_STORE)


async def _run[T](work: Awaitable[T]) -> T:
    try:
        return await work
    except NotFound:
        raise _fail(404, "not_found") from None
    except NotAllowed:
        raise _fail(403, "not_allowed") from None
    except CapReached:
        raise _fail(409, "class_caps") from None
    except InvalidClass:
        raise _fail(422, "invalid_class") from None
    except BadWindow:
        raise _fail(422, "invalid_range") from None
    except UnknownLocation:
        raise _fail(422, "unknown_location") from None


def _hm(at: time) -> str:
    return f"{at:%H:%M}"


def _teacher(staff: Mapping[UUID, str | None], id: UUID | None) -> ClassTeacherOut | None:
    return None if id is None else ClassTeacherOut(id=id, name=staff.get(id))


def _occurrence(s: Schedule, o: Occurrence) -> ScheduleOccurrenceOut:
    return ScheduleOccurrenceOut(
        **_occurrence_fields(s.staff, o), moon=o.moon, swapped_to=o.swapped_to
    )


def _my_class(staff: Mapping[UUID, str | None], r: MyRow, role: Teaching) -> MyClassOut:
    return MyClassOut(**_occurrence_fields(staff, r.occurrence), role=role.value)


def _my_row(s: MySchedule, r: MyRow) -> MyRowOut:
    o = r.occurrence
    return MyRowOut(
        **_occurrence_fields(s.staff.get(r.shala_id, {}), o),
        moon=o.moon,
        swapped_to=o.swapped_to,
        shala_id=r.shala_id,
        zone=r.zone,
        city=r.city,
        role=None if r.role is None else r.role.value,
        my_teacher=r.my_teacher,
        planned=None if o.planned is None else _hm(o.planned),
    )


def _shifts(s: MySchedule) -> list[ShiftOut]:
    out: list[ShiftOut] = []
    for shift in s.shifts:
        rows = [r for r in s.rows if r.zone == shift.zone]
        ids = list(dict.fromkeys(r.shala_id for r in rows))
        city = rows[0].city if rows else ""
        out.append(
            ShiftOut(zone=shift.zone, city=city, shala_ids=ids, on=shift.on, minutes=shift.minutes)
        )
    return out


def _occurrence_fields(staff: Mapping[UUID, str | None], o: Occurrence) -> dict[str, Any]:
    return dict(
        class_id=o.class_id,
        key=o.key,
        on=o.on,
        start=_hm(o.start),
        end=_hm(o.end),
        starts_at=o.starts_at,
        type=o.type.value,
        title=o.title,
        online=o.online,
        teacher=_teacher(staff, o.teacher_id),
        substitute=o.substitute,
        cancelled=None if o.cancelled is None else o.cancelled.value,
        moved=o.moved,
        swapped_from=o.swapped_from,
        held=o.held,
        usual_teacher=_teacher(staff, o.planned_teacher),
    )


def _class(c: StoredClass) -> ClassOut:
    return ClassOut(
        id=c.id,
        type=c.type.value,
        title=c.title,
        online=c.online,
        city=c.city,
        teacher_id=c.teacher_id,
        start=_hm(c.start),
        minutes=c.minutes,
        weekdays=sorted(c.weekdays),
        every=c.every,
        starts_on=c.starts_on,
        ends_on=c.ends_on,
        rrule=to_rrule(_as_series(c)),
    )


def _as_series(c: StoredClass) -> ClassSeries:
    return ClassSeries(
        id=c.id,
        type=c.type,
        title=c.title,
        online=c.online,
        zone="UTC",
        teacher_id=c.teacher_id,
        start=c.start,
        minutes=c.minutes,
        weekdays=frozenset(c.weekdays),
        every=c.every,
        starts_on=c.starts_on,
        ends_on=c.ends_on,
    )


def _draft(body: ClassIn) -> ClassDraft:
    return ClassDraft(
        type=ClassType(body.type),
        title=body.title,
        online=body.online,
        city=body.city,
        teacher_id=body.teacher_id,
        start=time.fromisoformat(body.start),
        minutes=body.minutes,
        weekdays=frozenset(body.weekdays),
        every=body.every,
        starts_on=body.starts_on,
        ends_on=body.ends_on,
    )


@router.get("/shalas/{id}/schedule", responses=error_responses(404, 422))
async def get_schedule(
    id: UUID,
    principal: CurrentPrincipal,
    use_cases: UseCases,
    response: Response,
    from_date: Annotated[date, Query(alias="from", description="Shala-local date")],
    days: Annotated[int, Query(ge=1, le=WINDOW_MAX)] = 7,
) -> ScheduleOut:
    response.headers.update(_NO_STORE)
    s = await _run(use_cases.schedule.execute(principal, id, from_date, days))
    return ScheduleOut(
        zone=s.zone,
        city=s.city,
        moon_policy=s.moon_policy.value,
        days_off=None if s.days_off is None else sorted(s.days_off),
        days=[
            ScheduleDayOut(date=d.date, moon=d.moon, day_off=d.day_off, swap_from=d.swap_from)
            for d in s.days
        ],
        occurrences=[_occurrence(s, o) for o in s.occurrences],
        closures=[ClosureOut(id=c.id, start=c.start, end=c.end) for c in s.closures],
    )


@router.get("/me/schedule", responses=error_responses(422))
async def get_my_schedule(
    principal: CurrentPrincipal,
    use_cases: UseCases,
    response: Response,
    from_date: Annotated[
        date | None, Query(alias="from", description="My date; default my today")
    ] = None,
    days: Annotated[int, Query(ge=1, le=MY_DAYS)] = MY_DAYS,
    only: Only = Only.ALL,
) -> MyScheduleOut:
    """SC-03: every shala where I am a member, in my zone (ADR-0035)."""
    response.headers.update(_NO_STORE)
    s = await _run(use_cases.mine.execute(principal, from_date, days, only=only))
    return MyScheduleOut(
        zone=s.zone,
        zone_known=s.zone_known,
        today=s.today,
        moon_city=s.moon_city,
        days=[MyDayOut(date=d.date, my_moon=d.my_moon) for d in s.days],
        shalas=[
            ScheduleShalaOut(id=x.id, name=x.name, city=x.city, zone=x.zone, staff=x.staff)
            for x in s.shalas
        ],
        has_teachers=s.has_teachers,
        is_staff=s.is_staff,
        shifts=_shifts(s),
        occurrences=[_my_row(s, r) for r in s.rows],
    )


@router.get("/me/classes", deprecated=True)
async def get_my_classes(
    principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> list[MyShalaClassesOut]:
    """Deprecated (Q137): use `/me/schedule?only=mine`. The next 7 days of the classes I teach,
    cover, or have covered, grouped per shala (shalas with none left out), from my today."""
    response.headers.update(_NO_STORE)
    s = await _run(use_cases.mine.execute(principal, None, only=Only.MINE))
    return [
        MyShalaClassesOut(
            shala_id=x.id,
            name=x.name,
            zone=x.zone,
            today=s.today,
            classes=[_my_class(s.staff[x.id], r, r.role) for r in rows if r.role is not None],
        )
        for x in s.shalas
        # SC-02's shape: no kept original of a swapped class (that is My schedule's mark)
        if (rows := [r for r in s.rows if r.shala_id == x.id and r.occurrence.swapped_to is None])
    ]


@router.get("/shalas/{id}/classes", responses=error_responses(403, 404))
async def get_classes(
    id: UUID, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> list[ClassOut]:
    response.headers.update(_NO_STORE)
    return [_class(c) for c in await _run(use_cases.classes.execute(principal, id))]


@router.post("/shalas/{id}/classes", status_code=201, responses=error_responses(403, 404, 409, 422))
async def post_class(
    id: UUID, body: ClassIn, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> ClassOut:
    response.headers.update(_NO_STORE)
    return _class(await _run(use_cases.create.execute(principal, id, _draft(body))))


async def _current(
    use_cases: ClassUseCases, principal: Principal, shala: UUID, class_id: UUID
) -> StoredClass:
    found = next(
        (c for c in await use_cases.classes.execute(principal, shala) if c.id == class_id), None
    )
    if found is None:
        raise NotFound
    return found


@router.patch("/shalas/{id}/classes/{class_id}", responses=error_responses(403, 404, 422))
async def patch_class(
    id: UUID,
    class_id: UUID,
    body: ClassPatchIn,
    principal: CurrentPrincipal,
    use_cases: UseCases,
    response: Response,
) -> ClassOut:
    """A new id after a split with `from`."""
    response.headers.update(_NO_STORE)
    current = await _run(_current(use_cases, principal, id, class_id))
    sent = body.model_fields_set - {"from_date"}
    changes: dict[str, object] = {name: getattr(body, name) for name in sent}
    if "type" in changes and changes["type"] is not None:
        changes["type"] = ClassType(str(changes["type"]))
    if "start" in changes and changes["start"] is not None:
        changes["start"] = time.fromisoformat(str(changes["start"]))
    if "weekdays" in changes and changes["weekdays"] is not None:
        changes["weekdays"] = frozenset(body.weekdays or ())
    for required in ("type", "online", "start", "minutes", "weekdays", "every", "starts_on"):
        if changes.get(required, ...) is None:
            raise _fail(422, "invalid_class")
    fields = {f: getattr(current, f) for f in ClassDraft.__dataclass_fields__}
    draft = ClassDraft(**(fields | changes))  # type: ignore[arg-type]
    updated = await _run(
        use_cases.update.execute(principal, id, class_id, draft, from_date=body.from_date)
    )
    return _class(updated)


@router.delete(
    "/shalas/{id}/classes/{class_id}", status_code=204, responses=error_responses(403, 404)
)
async def delete_class(
    id: UUID, class_id: UUID, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> None:
    """Idempotent; hard. Its exceptions go with it."""
    await _run(use_cases.delete.execute(principal, id, class_id))
    response.headers.update(_NO_STORE)


@router.put(
    "/shalas/{id}/classes/{class_id}/occurrences/{key}", responses=error_responses(403, 404, 422)
)
async def put_occurrence(
    id: UUID,
    class_id: UUID,
    key: date,
    body: OccurrenceIn,
    principal: CurrentPrincipal,
    use_cases: UseCases,
    response: Response,
) -> ScheduleOccurrenceOut:
    """`key` is the rule's date. Cancel, hold anyway (Q126), move (±6 days), change the time,
    or name a substitute; silent (Q122)."""
    response.headers.update(_NO_STORE)
    override = Override(
        on_date=key,
        status=None if body.status is None else OverrideStatus(body.status),
        moved_to=body.on,
        start=None if body.start is None else time.fromisoformat(body.start),
        minutes=body.minutes,
        teacher_id=body.teacher_id,
    )
    await _run(use_cases.override.execute(principal, id, class_id, key, override))
    s = await _run(use_cases.schedule.execute(principal, id, key - timedelta(days=6), 13))
    found = next((o for o in s.occurrences if o.class_id == class_id and o.key == key), None)
    if found is None:  # moved outside what the caller may read (a 1:1 for a student can't be)
        raise _fail(404, "not_found")
    return _occurrence(s, found)


@router.delete(
    "/shalas/{id}/classes/{class_id}/occurrences/{key}",
    status_code=204,
    responses=error_responses(403, 404),
)
async def delete_occurrence(
    id: UUID,
    class_id: UUID,
    key: date,
    principal: CurrentPrincipal,
    use_cases: UseCases,
    response: Response,
) -> None:
    """Restore: the occurrence follows its rule again. Idempotent."""
    await _run(use_cases.clear.execute(principal, id, class_id, key))
    response.headers.update(_NO_STORE)


@router.post(
    "/shalas/{id}/closures", status_code=201, responses=error_responses(403, 404, 409, 422)
)
async def post_closure(
    id: UUID, body: ClosureIn, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> ClosureOut:
    response.headers.update(_NO_STORE)
    closure = await _run(use_cases.add_closure.execute(principal, id, body.start, body.end))
    return ClosureOut(id=closure.id, start=closure.start, end=closure.end)


@router.delete(
    "/shalas/{id}/closures/{closure_id}", status_code=204, responses=error_responses(403, 404)
)
async def delete_closure(
    id: UUID, closure_id: UUID, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> None:
    await _run(use_cases.remove_closure.execute(principal, id, closure_id))
    response.headers.update(_NO_STORE)


@router.post("/shalas/{id}/swaps", status_code=201, responses=error_responses(403, 404, 409, 422))
async def post_swap(
    id: UUID, body: SwapIn, principal: CurrentPrincipal, use_cases: UseCases, response: Response
) -> SwapOut:
    """Q125: hold the auto-cancelled classes of `from` on `to` (the day off, or a day without
    a class of the same type; not a moon day, not closed; ±6 days)."""
    response.headers.update(_NO_STORE)
    swap = await _run(use_cases.add_swap.execute(principal, id, body.from_date, body.to))
    return SwapOut.model_validate({"from": swap.from_date, "to": swap.to_date})


@router.delete("/shalas/{id}/swaps/{from}", status_code=204, responses=error_responses(403, 404))
async def delete_swap(
    id: UUID,
    from_date: Annotated[date, Path(alias="from")],
    principal: CurrentPrincipal,
    use_cases: UseCases,
    response: Response,
) -> None:
    await _run(use_cases.remove_swap.execute(principal, id, from_date))
    response.headers.update(_NO_STORE)


ScheduleOut.model_rebuild()
