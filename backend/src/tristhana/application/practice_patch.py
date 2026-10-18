from dataclasses import dataclass, fields

from tristhana.domain.practice import Practice

_ALL = frozenset(f.name for f in fields(Practice)) - {"slot"}


@dataclass(frozen=True, slots=True)
class PracticePatch:
    """New values for some fields of a practice: a bot tap sets one field, the API's PUT
    sets them all. `fields` names the ones to write; the rest of `values` is ignored."""

    values: Practice
    fields: frozenset[str]

    @classmethod
    def of(cls, **values: object) -> "PracticePatch":
        unknown = set(values) - _ALL
        if unknown:
            raise ValueError(f"unknown practice fields: {sorted(unknown)}")
        return cls(Practice(**values), frozenset(values))  # type: ignore[arg-type]

    @classmethod
    def full(cls, practice: Practice) -> "PracticePatch":
        return cls(practice, _ALL)
