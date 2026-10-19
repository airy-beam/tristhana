"""The caller's own account (ID-01). Opening the Mini App creates it on first contact."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from tristhana.api.deps import (
    CurrentPrincipal,
    client_profile,
    record_device_timezone,
    update_profile,
)
from tristhana.api.errors import ApiError, error_responses
from tristhana.application.accounts import RecordDeviceTimezone
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

router = APIRouter(prefix="/me", tags=["me"], responses=error_responses(401, 503))


class Me(BaseModel):
    id: UUID
    display_name: str | None
    locale: Locale
    timezone: str | None = Field(description="IANA zone, e.g. Asia/Almaty; null until set")
    name_from_telegram: bool = Field(description="False once a name was chosen in settings")
    locale_from_telegram: bool = Field(description="False once a language was chosen")

    @classmethod
    def of(cls, account: Account) -> "Me":
        return cls(
            id=account.id,
            display_name=account.display_name,
            locale=account.locale,
            timezone=account.timezone,
            name_from_telegram=not account.name_custom,
            locale_from_telegram=not account.locale_custom,
        )


class MePatch(BaseModel):
    """Omitted = unchanged; null = back to Telegram's (name, language) (ADR-0021)."""

    display_name: str | None = Field(default=None, max_length=200)
    locale: Locale | None = None
    timezone: str | None = Field(default=None, max_length=64, description="IANA zone or UTC")


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
