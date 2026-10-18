from importlib.metadata import version

from tristhana import __version__


def test_version_matches_package_metadata() -> None:
    assert __version__ == version("tristhana")
