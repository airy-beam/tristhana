"""The caller's own account (ID-01). Opening the Mini App creates it on first contact."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field, StrictInt

from tristhana.api.deps import (
    CurrentPrincipal,
    client_profile,
    dismiss_day_off,
    record_device_timezone,
    set_day_off,
    update_profile,
)
from tristhana.api.errors import ApiError, error_responses
from tristhana.application.accounts import RecordDeviceTimezone
from tristhana.application.rest_days import DismissDayOffQuestion, SetDayOff
from tristhana.application.settings import UpdateProfile
from tristhana.domain.accounts import (
    KEEP,
    Account,
    ExternalProfile,
    InvalidDisplayName,
    InvalidTimezone,
    ProfilePatch,
)
from tristhana.domain.locale import Locale
from tristhana.domain.rest_days import InvalidDayOff, Weekdays

router = APIRouter(prefix="/me", tags=["me"], responses=error_responses(401, 503))


class Me(BaseModel):
    id: UUID
    display_name: str | None
    locale: Locale
    timezone: str | None = Field(description="IANA zone, e.g. Asia/Almaty; null until set")
    name_from_telegram: bool = Field(description="False once a name was chosen in settings")
    locale_from_telegram: bool = Field(description="False once a language was chosen")
    day_off: list[int] | None = Field(
        default=None,
        description="Weekly day off, ISO weekdays (1 = Monday); [] = no fixed day off; "
        "null = never chosen",
    )

    @classmethod
    def of(cls, account: Account) -> "Me":
        return cls(
            id=account.id,
            display_name=account.display_name,
            locale=account.locale,
            timezone=account.timezone,
            name_from_telegram=not account.name_custom,
            locale_from_telegram=not account.locale_custom,
            day_off=_weekdays(account.day_off.days),
        )


def _weekdays(days: Weekdays | None) -> list[int] | None:
    return None if days is None else sorted(days)


class MePatch(BaseModel):
    """Omitted = unchanged; null = back to Telegram's (name, language) (ADR-0021)."""

    display_name: str | None = Field(default=None, max_length=200)
    locale: Locale | None = None
    timezone: str | None = Field(default=None, max_length=64, description="IANA zone or UTC")


class DayOffBody(BaseModel):
    day_off: list[StrictInt] = Field(
        description="ISO weekdays (1 = Monday); [] = no fixed day off; at most two"
    )


class DayOffOut(BaseModel):
    day_off: list[int]
    practice_days: list[int] = Field(description="The other days: practice reminders come then")


class DeviceTimezone(BaseModel):
    timezone: str = Field(max_length=64, description="Intl.DateTimeFormat().resolvedOptions()")


@router.get("")
async def get_me(principal: CurrentPrincipal) -> Me:
    return Me.of(principal.account)


@router.patch("", responses=error_responses(422))
async def patch_me(
    body: MePatch,
    principal: CurrentPrincipal,
    use_case: Annotated[UpdateProfile, Depends(update_profile)],
    client: Annotated[ExternalProfile, Depends(client_profile)],
) -> Me:
    sent = body.model_fields_set
    patch = ProfilePatch(
        display_name=body.display_name if "display_name" in sent else KEEP,
        locale=body.locale if "locale" in sent else KEEP,
        timezone=body.timezone if "timezone" in sent and body.timezone is not None else KEEP,
    )
    if "timezone" in sent and body.timezone is None:
        raise ApiError(422, "invalid_timezone")  # a zone can be changed, not removed
    try:
        account = await use_case.execute(principal, patch, client)
    except InvalidTimezone:
        raise ApiError(422, "invalid_timezone") from None
    except InvalidDisplayName:
        raise ApiError(422, "invalid_display_name") from None
    return Me.of(account)


@router.post("/device-timezone", responses=error_responses(422))
async def post_device_timezone(
    body: DeviceTimezone,
    principal: CurrentPrincipal,
    record: Annotated[RecordDeviceTimezone, Depends(record_device_timezone)],
) -> Me:
    """Stores the device zone only if none is set yet; returns the account either way."""
    try:
        account = await record.execute(principal, body.timezone)
    except InvalidTimezone:
        raise ApiError(422, "invalid_timezone") from None
    return Me.of(account)


@router.put("/day-off", responses=error_responses(422))
async def put_day_off(
    body: DayOffBody,
    principal: CurrentPrincipal,
    use_case: Annotated[SetDayOff, Depends(set_day_off)],
) -> DayOffOut:
    """The first choice also shows on past weeks; a change applies from today (PR-09)."""
    try:
        saved = await use_case.execute(principal, body.day_off)
    except InvalidDayOff:
        raise ApiError(422, "invalid_day_off") from None
    return DayOffOut(
        day_off=sorted(saved.account.day_off.days or ()),
        practice_days=sorted(saved.practice_days),
    )


@router.delete("/day-off-question", status_code=204)
async def delete_day_off_question(
    principal: CurrentPrincipal,
    use_case: Annotated[DismissDayOffQuestion, Depends(dismiss_day_off)],
) -> Response:
    """ "Not now" on the one-time day-off question. Idempotent."""
    await use_case.execute(principal)
    return Response(status_code=204)
