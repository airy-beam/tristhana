"""Check-in use cases (PR-06, ADR-0024). Shared by the bot and the API; every call acts on
the caller's own days (`Principal`). Reads go through `GetDays` (`DayLog.check_ins`)."""

from datetime import date

from tristhana.application.check_in_patch import CheckInPatch
from tristhana.application.policies import Principal
from tristhana.application.ports.check_in import CheckInRepository
from tristhana.application.practice import DayNotPracticed
from tristhana.domain.check_in import CheckIn, CheckInTag, check_check_in


class SaveCheckIn:
    def __init__(self, check_ins: CheckInRepository) -> None:
        self._check_ins = check_ins

    async def execute(self, principal: Principal, local_date: date, patch: CheckInPatch) -> CheckIn:
        """Raises `DayNotPracticed`, `InvalidCheckIn`."""
        check_check_in(patch.values)
        saved = await self._check_ins.save(principal.account.id, local_date, patch)
        if saved is None:
            raise DayNotPracticed(local_date.isoformat())
        return saved


class SetCheckInTag:
    def __init__(self, check_ins: CheckInRepository) -> None:
        self._check_ins = check_ins

    async def execute(
        self, principal: Principal, local_date: date, tag: CheckInTag, on: bool
    ) -> CheckIn:
        """Raises `DayNotPracticed`."""
        saved = await self._check_ins.set_tag(principal.account.id, local_date, tag, on)
        if saved is None:
            raise DayNotPracticed(local_date.isoformat())
        return saved


class ClearCheckIn:
    def __init__(self, check_ins: CheckInRepository) -> None:
        self._check_ins = check_ins

    async def execute(self, principal: Principal, local_date: date) -> None:
        await self._check_ins.delete(principal.account.id, local_date)
