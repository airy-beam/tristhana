"""The frozen list of pre-UI-06 callback data (UI-06 §5): every entry still decodes."""

import importlib
import pkgutil
from collections.abc import Callable

import pytest

import tristhana.bots.telegram as bot
from tests.bots.fixtures.pre_ui06_callbacks import PRE_UI06_CALLBACKS
from tristhana.bots.telegram import callbacks, start


def _decoders() -> dict[str, Callable[[str | None], object]]:
    """Prefix → decoder: `callbacks.py`, every `*_callbacks.py`, and /start's `o1:`."""
    modules = [callbacks, start]
    for info in pkgutil.iter_modules(bot.__path__):
        if info.name.endswith("_callbacks"):
            modules.append(importlib.import_module(f"{bot.__name__}.{info.name}"))
    return {m.PREFIX: m.decode for m in modules}


# The prefixes that existed when the list was frozen. A prefix added later (UI-06's `w1:`)
# is not in the list and needs no entry.
FROZEN_PREFIXES = frozenset(
    {"d1", "o1", "q1", "p1", "k1", "n1", "g1", "r1", "a1", "s1", "m1", "x1", "t1", "h1"}
    | {"c1", "v1", "b1", "l1"}
)


@pytest.mark.parametrize("data", PRE_UI06_CALLBACKS)
def test_every_frozen_entry_still_decodes(data: str) -> None:
    decode = _decoders()[data.split(":", 1)[0]]

    assert decode(data) is not None
    assert len(data.encode()) <= 64


def test_the_list_covers_every_prefix_shipped_before_ui06() -> None:
    listed = {data.split(":", 1)[0] for data in PRE_UI06_CALLBACKS}

    assert listed == FROZEN_PREFIXES
    assert set(_decoders()) >= FROZEN_PREFIXES  # no decoder module was removed


def test_the_list_has_no_duplicates() -> None:
    assert len(set(PRE_UI06_CALLBACKS)) == len(PRE_UI06_CALLBACKS)


def test_one_entry_per_letter_of_every_prefix() -> None:
    """The prefix-and-letter pairs, pinned: dropping an entry from the list fails here."""
    pairs = {":".join(data.split(":")[:2]) for data in PRE_UI06_CALLBACKS}
    letters = {
        "d1": "t o s x w",
        "o1": "l",
        "q1": "1 2 3 4 5 6 d",
        "p1": "o v s x m a d c n t r g l",
        "k1": "o v g x m e f t",
        "n1": "o w r y x b",
        "g1": "o c g s i a p u n",
        "r1": "v o t w y n s p r q d dp dt dn",
        "a1": "p m b o k e er",
        "s1": "v l cp zp c z u n o h k",
        "m1": "v r c s f h k z o t q",
        "x1": "o e d y",
        "t1": "a y n l o s c p u x v r z i q w wy g gp gy",
        "h1": "a b n l c m v i q w wy e u x k ky",
        "c1": "w p o x r h d m f",
        "v1": "l p i u r a y n",
        "b1": "l m u",
        "l1": "o w wy a k c y n ny",
    }
    expected = {f"{prefix}:{letter}" for prefix, row in letters.items() for letter in row.split()}

    assert pairs == expected
