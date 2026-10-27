"""Diary note use cases (PR-07, ADR-0025). Shared by the bot and the API; every call acts on
the caller's own days (`Principal`). Screens read notes through `GetDays` (`DaysView.notes`)."""

from datetime import date

from tristhana.application.policies import Principal
from tristhana.application.ports.diary import DiaryRepository
from tristhana.application.ports.storage import Clock
from tristhana.domain.days import check_loggable
from tristhana.domain.diary import DiaryNote, normalize_note


class SaveDiaryNote:
    def __init__(self, diary: DiaryRepository, clock: Clock) -> None:
        self._diary = diary
        self._clock = clock

    async def execute(self, principal: Principal, local_date: date, text: str) -> str | None:
        """The stored text; None = blank, so the note was removed. Raises `NoteTooLong`,
        `DateInFuture`, `DateTooEarly`."""
        account = principal.account
        check_loggable(local_date, self._clock.now(), account.timezone)
        note = normalize_note(text)
        if note is None:
            await self._diary.delete(account.id, local_date)
        else:
            await self._diary.save(account.id, local_date, note)
        return note


class GetDiaryNote:
    def __init__(self, diary: DiaryRepository, clock: Clock) -> None:
        self._diary = diary
        self._clock = clock

    async def execute(self, principal: Principal, local_date: date) -> DiaryNote | None:
        """Raises `DateInFuture` / `DateTooEarly` (dates follow the logging rules)."""
        check_loggable(local_date, self._clock.now(), principal.account.timezone)
        return await self._diary.get(principal.account.id, local_date)


class ClearDiaryNote:
    def __init__(self, diary: DiaryRepository) -> None:
        self._diary = diary

    async def execute(self, principal: Principal, local_date: date) -> None:
        await self._diary.delete(principal.account.id, local_date)
