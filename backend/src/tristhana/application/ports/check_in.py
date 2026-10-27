from datetime import date
from typing import Protocol
from uuid import UUID

from tristhana.application.check_in_patch import CheckInPatch
from tristhana.domain.check_in import CheckIn, CheckInTag


class CheckInRepository(Protocol):
    """One statement per method. Writes only land on a day whose status is Practiced; the
    check-in goes when the day stops being Practiced (`DayLogRepository.upsert`)."""

    async def save(self, account_id: UUID, local_date: date, patch: CheckInPatch) -> CheckIn | None:
        """Upsert the patched fields of slot 1; None when the day isn't Practiced."""
        ...

    async def set_tag(
        self, account_id: UUID, local_date: date, tag: CheckInTag, on: bool
    ) -> CheckIn | None:
        """Absolute and idempotent: `on` twice is the same as once. None as for `save`."""
        ...

    async def delete(self, account_id: UUID, local_date: date) -> None:
        """Idempotent."""
        ...
