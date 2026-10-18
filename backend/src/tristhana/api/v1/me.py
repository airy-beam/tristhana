"""The caller's own account (ID-01). Opening the Mini App creates it on first contact."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from tristhana.api.deps import CurrentPrincipal, record_device_timezone
from tristhana.api.errors import ApiError, error_responses
from tristhana.application.accounts import RecordDeviceTimezone
from tristhana.domain.accounts import Account, InvalidTimezone
from tristhana.domain.locale import Locale

router = APIRouter(prefix="/me", tags=["me"], responses=error_responses(401, 503))


class Me(BaseModel):
    id: UUID
    display_name: str | None
    locale: Locale
    timezone: str | None = Field(description="IANA zone, e.g. Asia/Almaty; null until set")

    @classmethod
    def of(cls, account: Account) -> "Me":
        return cls(
            id=account.id,
            display_name=account.display_name,
            locale=account.locale,
            timezone=account.timezone,
        )


class DeviceTimezone(BaseModel):
    timezone: str = Field(max_length=64, description="Intl.DateTimeFormat().resolvedOptions()")


@router.get("")
async def get_me(principal: CurrentPrincipal) -> Me:
    return Me.of(principal.account)


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
