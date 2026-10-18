import pytest

from tristhana.domain.moon import MoonDayKind, MoonLocation, MoonPhase


@pytest.mark.parametrize(
    ("kind", "phase", "is_kshaya"),
    [
        (MoonDayKind.PURNIMA, MoonPhase.PURNIMA, False),
        (MoonDayKind.AMAVASYA, MoonPhase.AMAVASYA, False),
        (MoonDayKind.KSHAYA_PURNIMA, MoonPhase.PURNIMA, True),
        (MoonDayKind.KSHAYA_AMAVASYA, MoonPhase.AMAVASYA, True),
    ],
)
def test_kind_phase_and_kshaya(kind: MoonDayKind, phase: MoonPhase, is_kshaya: bool) -> None:
    assert kind.phase is phase
    assert kind.is_kshaya is is_kshaya


def test_location_accepts_valid_values() -> None:
    loc = MoonLocation(lat=12.2958, lon=76.6394, tz="Asia/Kolkata")

    assert loc.tz == "Asia/Kolkata"


@pytest.mark.parametrize(
    ("lat", "lon", "tz"),
    [
        (91.0, 0.0, "UTC"),
        (-91.0, 0.0, "UTC"),
        (0.0, 180.5, "UTC"),
        (0.0, -181.0, "UTC"),
        (0.0, 0.0, "Mars/Olympus_Mons"),
        (0.0, 0.0, "+05:00"),
    ],
)
def test_location_rejects_invalid_values(lat: float, lon: float, tz: str) -> None:
    with pytest.raises(ValueError, match=r"range|IANA"):
        MoonLocation(lat=lat, lon=lon, tz=tz)


@pytest.mark.parametrize("tz", ["Etc/GMT-5", "Etc/GMT+3"])
def test_location_rejects_fixed_offset_zones(tz: str) -> None:
    with pytest.raises(ValueError, match="fixed offset"):
        MoonLocation(lat=0.0, lon=0.0, tz=tz)


@pytest.mark.parametrize("tz", ["UTC", "Etc/UTC"])
def test_location_accepts_utc(tz: str) -> None:
    assert MoonLocation(lat=0.0, lon=0.0, tz=tz).tz == tz
