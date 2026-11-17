"""The next step on the Today tab (UI-06 stage 2): the caller's own, derived on every read."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from tristhana.api.deps import CurrentPrincipal, get_next_steps
from tristhana.api.errors import error_responses
from tristhana.application.journey import GetNextSteps
from tristhana.domain.journey import Step

router = APIRouter(prefix="/me/next-steps", tags=["journey"], responses=error_responses(401, 503))


class NextStepOut(BaseModel):
    kind: Literal["add_class", "invite_shala_students", "invite_student", "reminder", "position"]
    shala_id: UUID | None = Field(
        description="The caller's own shala the step is about (`add_class`,"
        " `invite_shala_students`); null for the others"
    )

    @classmethod
    def of(cls, step: Step) -> "NextStepOut":
        return cls(kind=step.kind.value, shala_id=step.shala_id)


class NextStepsOut(BaseModel):
    steps: list[NextStepOut] = Field(
        description="Every step still due, in offer order; the app shows the first one the"
        " person has not put off on this device"
    )


@router.get("")
async def get_my_next_steps(
    principal: CurrentPrincipal, use_case: Annotated[GetNextSteps, Depends(get_next_steps)]
) -> NextStepsOut:
    """What the Today tab may offer next. Derived from the caller's own data on every read:
    nothing is stored, a step is gone once its data exists, and "Not now" never reaches the
    server. Shala steps name only shalas the caller owns."""
    steps = await use_case.execute(principal)
    return NextStepsOut(steps=[NextStepOut.of(s) for s in steps])
