# Minimal stub for the parts of pyswisseph used by tristhana.moon (the package ships no types).

SUN: int
MOON: int
CALC_RISE: int
GREG_CAL: int
FLG_SWIEPH: int

class Error(Exception): ...

def set_ephe_path(path: str | None = ..., /) -> None: ...
def julday(year: int, month: int, day: int, hour: float = ..., cal: int = ..., /) -> float: ...
def revjul(jd: float, cal: int = ..., /) -> tuple[int, int, int, float]: ...
def calc_ut(
    tjdut: float, planet: int, flags: int = ..., /
) -> tuple[tuple[float, float, float, float, float, float], int]: ...
def rise_trans(
    tjdut: float,
    body: int,
    rsmi: int,
    geopos: tuple[float, float, float],
    atpress: float = ...,
    attemp: float = ...,
    flags: int = ...,
) -> tuple[int, tuple[float, ...]]: ...
