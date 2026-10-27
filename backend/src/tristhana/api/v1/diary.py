"""The caller's diary note per day (PR-07, ADR-0025). The text travels only in bodies, is
never echoed in an error, and responses carrying it are never cached."""

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field

from tristhana.api.deps import CurrentPrincipal, clear_diary_note, save_diary_note
from tristhana.api.errors import ApiError, error_responses
from tristhana.application.diary import ClearDiaryNote, SaveDiaryNote
from tristhana.domain.days import DateInFuture, DateTooEarly
from tristhana.domain.diary import DiaryNote, NoteTooLong

router = APIRouter(prefix="/me/days", tags=["diary"], responses=error_responses(401, 503))

NO_STORE = {"Cache-Control": "no-store"}


class DayNoteOut(BaseModel):
    date: dt.date
    text: str | None = Field(description="null: removed (blank text), or unreadable")
    unreadable: bool = Field(default=False, description="Stored, but can't be read right now")

    @classmethod
    def all(cls, notes: dict[dt.date, DiaryNote]) -> "list[DayNoteOut]":
        return [
            cls(date=d, text=n.text, unreadable=n.text is None) for d, n in sorted(notes.items())
        ]


class DayNoteBody(BaseModel):
    # No max_length here: the length is checked in the domain, so a 422 never echoes it.
    text: str = Field(description="Plain text, up to 2000 characters; blank removes the note")


@router.put(
    "/{date}/note",
    responses=error_responses(413, 422),  # 413: over 16 KiB (`api/body_limit`)
)
async def put_note(
    date: dt.date,
    body: DayNoteBody,
    principal: CurrentPrincipal,
    use_case: Annotated[SaveDiaryNote, Depends(save_diary_note)],
    response: Response,
) -> DayNoteOut:
    """Replaces the day's note (any status, or none). Blank text removes it."""
    try:
        saved = await use_case.execute(principal, date, body.text)
    except NoteTooLong:
        raise ApiError(422, "note_too_long") from None
    except DateInFuture:
        raise ApiError(422, "date_in_future") from None
    except DateTooEarly:
        raise ApiError(422, "date_too_early") from None
    response.headers.update(NO_STORE)
    return DayNoteOut(date=date, text=saved)


@router.delete("/{date}/note", status_code=204)
async def delete_note(
    date: dt.date,
    principal: CurrentPrincipal,
    use_case: Annotated[ClearDiaryNote, Depends(clear_diary_note)],
) -> Response:
    """Idempotent. The day's status is untouched."""
    await use_case.execute(principal, date)
    return Response(status_code=204)
