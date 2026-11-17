"""The next step on the Today tab (UI-06 stage 2). The caller's own, derived on every read:
nothing is written, and a step is gone once the data it ends in exists. The bot can call the
same use case."""

from datetime import UTC

from tristhana.application.policies import Principal
from tristhana.application.ports.accounts import AccountRepository
from tristhana.application.ports.storage import Clock
from tristhana.domain.journey import Step, next_steps


class GetNextSteps:
    def __init__(self, accounts: AccountRepository, clock: Clock) -> None:
        self._accounts, self._clock = accounts, clock

    async def execute(self, principal: Principal) -> tuple[Step, ...]:
        """Every step still due, in offer order. One statement, then the rule in memory.

        The read takes the caller's id and nothing else, so it holds only their own facts,
        and shala facts only for shalas they own: every step offered is one they may take.
        """
        account = principal.account
        # `today` only measures the invite link's age, and the link's date is UTC's
        # (`invite_made_on`): two UTC dates, so the 30 days end at one moment for everyone.
        today = self._clock.now().astimezone(UTC).date()
        facts = await self._accounts.journey_facts(account.id)
        return next_steps(account, facts, today)
