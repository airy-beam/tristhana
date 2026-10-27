"""Practice details use cases (PR-02, PR-03, PR-05). Shared by the bot and the API; every
call acts on the caller's own days (`Principal`)."""

from dataclasses import replace
from datetime import date

from tristhana.application.policies import Principal
from tristhana.application.ports.practice import PracticeRepository, SavedPractice
from tristhana.application.practice_patch import PracticePatch
from tristhana.domain.practice import (
    RECENT_LIMIT,
    PracticeCatalog,
    PracticeContext,
    Presets,
    check_practice,
    derive_presets,
)
from tristhana.domain.progression import Track, my_presets, past_last


class DayNotPracticed(Exception):
    """Details only exist on a Practiced day (a stale keyboard, or the status changed)."""


class NoPreviousPractice(Exception):
    pass


class SavePractice:
    def __init__(
        self, practices: PracticeRepository, catalog: PracticeCatalog, track: Track | None = None
    ) -> None:
        self._practices = practices
        self._catalog = catalog
        self._track = track or Track(catalog)

    async def execute(
        self, principal: Principal, local_date: date, patch: PracticePatch
    ) -> SavedPractice:
        """Raises `DayNotPracticed`, `InvalidLength`, `InvalidPractice`, `TimezoneUnknown`."""
        account = principal.account
        values, names = patch.values, set(patch.fields)
        if "start_time" in names:
            # The zone travels with the start time only: a later duration tap at home must
            # not re-label a time saved in Mysuru (ADR-0005).
            values, names = replace(values, timezone=account.timezone), names | {"timezone"}
        if values.context is PracticeContext.SELF and "context" in names:
            values, names = replace(values, online=False), names | {"online"}
        values = check_practice(self._catalog, values)
        saved = await self._practices.save(
            account.id, local_date, PracticePatch(values, frozenset(names))
        )
        if saved is None:
            raise DayNotPracticed(local_date.isoformat())
        if not saved.length_changed:
            return saved  # "New asana?" only answers a length tap (PR-08)
        p = saved.practice
        hint = past_last(self._track, saved.progression, p.length, p.context)
        return replace(saved, new_asana_hint=hint)


class CopyLastPractice:
    def __init__(self, practices: PracticeRepository) -> None:
        self._practices = practices

    async def execute(self, principal: Principal, local_date: date) -> SavedPractice:
        """Raises `DayNotPracticed` or `NoPreviousPractice`."""
        account = principal.account
        copied = await self._practices.copy_latest(account.id, local_date, account.timezone)
        if copied is not None:
            return copied
        if not await self._practices.recent(account.id, local_date, 1):
            raise NoPreviousPractice(local_date.isoformat())
        raise DayNotPracticed(local_date.isoformat())


class ClearPractice:
    def __init__(self, practices: PracticeRepository) -> None:
        self._practices = practices

    async def execute(self, principal: Principal, local_date: date) -> None:
        await self._practices.delete(principal.account.id, local_date)


class GetPracticePresets:
    def __init__(
        self, practices: PracticeRepository, catalog: PracticeCatalog, track: Track | None = None
    ) -> None:
        self._practices = practices
        self._catalog = catalog
        self._track = track or Track(catalog)

    async def execute(self, principal: Principal, local_date: date) -> Presets:
        """One statement: the recent practices with the progression ("🧘 My practice")."""
        recent, progression = await self._practices.recent_with_progression(
            principal.account.id, local_date, RECENT_LIMIT
        )
        mine = my_presets(self._track, progression, recent)
        return derive_presets(self._catalog, recent, mine)
