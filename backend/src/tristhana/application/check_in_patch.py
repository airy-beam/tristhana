from dataclasses import dataclass, fields

from tristhana.domain.check_in import CheckIn

_ALL = frozenset(f.name for f in fields(CheckIn)) - {"slot"}


@dataclass(frozen=True, slots=True)
class CheckInPatch:
    """New values for some fields of a check-in, like `PracticePatch`: a bot tap sets one
    field, the API's PUT sets them all. `fields` names the ones to write."""

    values: CheckIn
    fields: frozenset[str]

    @classmethod
    def of(cls, **values: object) -> "CheckInPatch":
        unknown = set(values) - _ALL
        if unknown:
            raise ValueError(f"unknown check-in fields: {sorted(unknown)}")
        return cls(CheckIn(**values), frozenset(values))  # type: ignore[arg-type]

    @classmethod
    def full(cls, check_in: CheckIn) -> "CheckInPatch":
        return cls(check_in, _ALL)
