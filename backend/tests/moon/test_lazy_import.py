import subprocess
import sys


def test_importing_moon_or_the_app_does_not_load_swisseph() -> None:
    code = "import sys, tristhana.moon, tristhana.main; print('swisseph' in sys.modules)"

    out = subprocess.run(  # noqa: S603 - fixed interpreter and code
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )

    assert out.stdout.strip().splitlines()[-1] == "False"
