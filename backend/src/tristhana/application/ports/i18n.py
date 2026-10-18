from typing import Protocol

from tristhana.domain.locale import Locale


class Translator(Protocol):
    def t(self, locale: Locale, key: str, **args: str | int) -> str:
        """The message `key` in `locale`; raises KeyError for an unknown key."""
        ...
