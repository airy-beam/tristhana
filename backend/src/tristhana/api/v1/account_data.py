"""My data (ST-09, ADR-0027): export everything (the bot sends the file to the caller's own
chat, never over HTTP) and delete the account. Any call after the 204 creates a new, empty
account (initData auth runs `EnsureAccount`), so the Mini App stops calling."""

import math
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from tristhana.api.deps import CurrentPrincipal, delete_my_account, send_my_export
from tristhana.api.errors import ApiError, error_responses
from tristhana.application.export import (
    BotUnreachable,
    DeleteMyAccount,
    ExportFailed,
    ExportTooLarge,
    ExportTooSoon,
    SendMyExport,
)

router = APIRouter(prefix="/me", tags=["me"], responses=error_responses(401, 503))


class ExportSentOut(BaseModel):
    file_name: str
    bytes: int
    sent_at: datetime


class DeleteBody(BaseModel):
    confirm: Literal["delete-everything"] | None = None


@router.post("/exports", response_model=ExportSentOut, responses=error_responses(409, 413, 429))
async def post_export(
    principal: CurrentPrincipal,
    use_case: Annotated[SendMyExport, Depends(send_my_export)],
) -> ExportSentOut | JSONResponse:
    """Sends the ZIP to the caller's chat with the bot. 429 `export_too_soon` (+ `Retry-After`)
    within 10 minutes of the last one; 409 `bot_unreachable` when the bot can't write to them
    (blocked or never started); 413 `export_too_large`."""
    try:
        sent = await use_case.execute(principal)
    except ExportTooSoon as e:
        wait = max(1, math.ceil(e.wait.total_seconds()))
        return JSONResponse(
            {"code": "export_too_soon", "retry_after_s": wait},
            status_code=429,
            headers={"Retry-After": str(wait)},
        )
    except BotUnreachable:
        raise ApiError(409, "bot_unreachable") from None
    except ExportTooLarge:
        raise ApiError(413, "export_too_large") from None
    except ExportFailed:
        raise ApiError(503, "unavailable") from None
    return ExportSentOut(file_name=sent.file_name, bytes=sent.bytes, sent_at=sent.sent_at)


@router.delete("", status_code=204, responses=error_responses(422))
async def delete_me(
    principal: CurrentPrincipal,
    use_case: Annotated[DeleteMyAccount, Depends(delete_my_account)],
    body: DeleteBody | None = None,
) -> Response:
    """Deletes the account and everything in it, at once (no undo). The body must say
    `{"confirm": "delete-everything"}`, so a stray DELETE can't do it."""
    if body is None or body.confirm != "delete-everything":
        raise ApiError(422, "confirmation_required")
    await use_case.execute(principal)
    return Response(status_code=204)
