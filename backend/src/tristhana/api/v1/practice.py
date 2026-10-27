"""Practice details of a practiced day (PR-02, PR-03, PR-05) and the catalog the Mini App's
length picker needs (ADR-0017)."""

import datetime as dt
import hashlib
from collections.abc import Iterable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Path, Response
from pydantic import BaseModel, Field

from tristhana.api.deps import (
    CurrentPrincipal,
    clear_practice,
    practice_catalog,
    practice_presets,
    save_practice,
)
from tristhana.api.errors import ApiError, error_responses
from tristhana.application.practice import (
    ClearPractice,
    DayNotPracticed,
    GetPracticePresets,
    SavePractice,
)
from tristhana.application.practice_patch import PracticePatch
from tristhana.domain.check_in import TAG_GROUPS, CheckInTag
from tristhana.domain.practice import (
    SERIES_HALVES,
    InvalidLength,
    InvalidPractice,
    Practice,
    PracticeCatalog,
    PracticeContext,
    PracticeLength,
    TimezoneUnknown,
)

router = APIRouter(tags=["practice"])

Slot = Annotated[int, Path(ge=1, le=1, description="One practice per day for now")]


class Length(BaseModel):
    series: list[str] = Field(description="Series slugs in practice order; [] = short practice")
    end: str | None = Field(default=None, description="Stop point in the last series; null = full")
    first_part: Literal["first_half", "second_half"] | None = None

    def to_domain(self) -> PracticeLength:
        return PracticeLength(tuple(self.series), self.end, self.first_part)

    @classmethod
    def of(cls, length: PracticeLength) -> "Length":
        return cls(series=list(length.series), end=length.end, first_part=length.first_part)


class PracticeBody(BaseModel):
    context: PracticeContext | None = None
    online: bool = False
    length: Length | None = None
    duration_min: int | None = Field(default=None, ge=1, le=600)
    start_time: dt.time | None = Field(default=None, description="Local wall clock, HH:MM")


class PracticeOut(PracticeBody):
    slot: int
    timezone: str | None = Field(description="IANA zone of start_time")

    @classmethod
    def of(cls, p: Practice) -> "PracticeOut":
        return cls(
            slot=p.slot,
            context=p.context,
            online=p.online,
            length=Length.of(p.length) if p.length else None,
            duration_min=p.duration_min,
            start_time=p.start_time,
            timezone=p.timezone,
        )


class Preset(BaseModel):
    kind: Literal["short", "half_primary", "full_primary", "recent"]
    length: Length


class PracticePresets(BaseModel):
    last: PracticeOut | None = Field(description="For 'same as last time'")
    presets: list[Preset]


class StopOut(BaseModel):
    key: str
    latin: str
    ru: str


class SeriesOut(BaseModel):
    slug: str
    number: int
    name_en: str
    name_ru: str
    halves_split: str | None = Field(description="First half ends here (Primary: navasana)")
    stops: list[StopOut]


class CheckInTagOut(BaseModel):
    key: CheckInTag
    group: Literal["body", "mind"]


class CatalogOut(BaseModel):
    version: str
    series: list[SeriesOut] = Field(description="Confirmed series only, in practice order")
    check_in_tags: list[CheckInTagOut] = Field(
        default=[], description="Check-in tags in display order (PR-06)"
    )


def catalog_etag(version: str, tag_keys: Iterable[str]) -> str:
    """The catalog's quoted ETag: the seed version plus the check-in tags with their
    groups (moving a tag between body and mind changes it too)."""
    tagged = ",".join(f"{k}:{_GROUPS.get(k, '')}" for k in tag_keys)
    return f'"{version}-{hashlib.sha256(tagged.encode()).hexdigest()[:8]}"'


_GROUPS: dict[str, str] = {t.value: g for t, g in TAG_GROUPS.items()}
_ETAG_TAGS = tuple(t.value for t in CheckInTag)


def _catalog_out(catalog: PracticeCatalog, version: str) -> CatalogOut:
    return CatalogOut(
        version=version,
        check_in_tags=[CheckInTagOut(key=t, group=TAG_GROUPS[t]) for t in CheckInTag],
        series=[
            SeriesOut(
                slug=s.slug,
                number=s.number,
                name_en=s.name_en,
                name_ru=s.name_ru,
                halves_split=SERIES_HALVES.get(s.slug),
                stops=[StopOut(key=p.key, latin=p.label("en"), ru=p.label("ru")) for p in s.stops],
            )
            for s in catalog.series
        ],
    )


@router.get("/catalog", response_model=CatalogOut, responses={304: {"description": "Not modified"}})
async def get_catalog(
    response: Response,
    loaded: Annotated[tuple[PracticeCatalog, str], Depends(practice_catalog)],
    if_none_match: Annotated[str | None, Header()] = None,
) -> CatalogOut | Response:
    """Public and cacheable: the series and their stop points for the length picker."""
    catalog, version = loaded
    etag = catalog_etag(version, _ETAG_TAGS)
    headers = {"ETag": etag, "Cache-Control": "public, max-age=3600"}
    if headers["ETag"] in {t.strip().removeprefix("W/") for t in (if_none_match or "").split(",")}:
        return Response(status_code=304, headers=headers)
    response.headers.update(headers)
    return _catalog_out(catalog, version)


@router.get("/me/days/{date}/practice-presets", responses=error_responses(401, 503))
async def get_presets(
    date: dt.date,
    principal: CurrentPrincipal,
    use_case: Annotated[GetPracticePresets, Depends(practice_presets)],
) -> PracticePresets:
    presets = await use_case.execute(principal, date)
    return PracticePresets(
        last=PracticeOut.of(presets.last) if presets.last else None,
        presets=[Preset(kind=k, length=Length.of(length)) for k, length in presets.presets],  # type: ignore[arg-type]
    )


@router.put("/me/days/{date}/practices/{slot}", responses=error_responses(401, 409, 422, 503))
async def put_practice(
    date: dt.date,
    slot: Slot,
    body: PracticeBody,
    principal: CurrentPrincipal,
    use_case: Annotated[SavePractice, Depends(save_practice)],
) -> PracticeOut:
    """Replaces the practice's details (all fields). The day must be Practiced."""
    if body.start_time is not None and body.start_time.tzinfo is not None:
        raise ApiError(422, "invalid_practice")  # local wall clock only; the zone is the account's
    practice = Practice(
        context=body.context,
        online=body.online,
        length=body.length.to_domain() if body.length else None,
        duration_min=body.duration_min,
        start_time=body.start_time.replace(second=0, microsecond=0) if body.start_time else None,
        slot=slot,
    )
    try:
        saved = await use_case.execute(principal, date, PracticePatch.full(practice))
    except DayNotPracticed:
        raise ApiError(409, "day_not_practiced") from None
    except InvalidLength:
        raise ApiError(422, "invalid_length") from None
    except InvalidPractice:
        raise ApiError(422, "invalid_practice") from None
    except TimezoneUnknown:
        raise ApiError(422, "timezone_unknown") from None
    return PracticeOut.of(saved.practice)


@router.delete(
    "/me/days/{date}/practices/{slot}", status_code=204, responses=error_responses(401, 503)
)
async def delete_practice(
    date: dt.date,
    slot: Slot,
    principal: CurrentPrincipal,
    use_case: Annotated[ClearPractice, Depends(clear_practice)],
) -> Response:
    await use_case.execute(principal, date)
    return Response(status_code=204)
