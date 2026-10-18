"""`/start` (UI-01). Phase 1 adds the user upsert (ID-01) behind the same signature."""

from dataclasses import dataclass

from tristhana.domain.locale import Locale, negotiate_locale


@dataclass(frozen=True, slots=True)
class StartCommand:
    telegram_user_id: int
    language_code: str | None


@dataclass(frozen=True, slots=True)
class StartResult:
    locale: Locale


class StartUseCase:
    async def execute(self, command: StartCommand) -> StartResult:
        return StartResult(locale=negotiate_locale(command.language_code))
