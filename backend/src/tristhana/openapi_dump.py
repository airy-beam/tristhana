"""`tristhana-openapi`: write the API contract for the Mini App's generated client (ADR-0013).

uv run tristhana-openapi           # write miniapp/src/api/openapi.json
uv run tristhana-openapi --check   # CI: fail if the committed file is stale
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path(__file__).resolve().parents[3] / "miniapp" / "src" / "api" / "openapi.json"


def render() -> str:
    from tristhana.main import create_app
    from tristhana.settings import Settings

    # No Telegram secrets: the webhook isn't mounted (it's hidden from OpenAPI anyway).
    settings = Settings(app_env="test", _env_file=None)  # pyright: ignore[reportCallIssue]
    schema: dict[str, Any] = create_app(settings).openapi()
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(), encoding="utf-8")


def is_fresh(path: Path) -> bool:
    return path.exists() and path.read_text(encoding="utf-8") == render()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the file is stale")
    parser.add_argument("--out", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    if args.check:
        if not is_fresh(args.out):
            print(f"{args.out} is stale: run `uv run tristhana-openapi`", file=sys.stderr)
            sys.exit(1)
        print(f"{args.out} is up to date")
        return
    write(args.out)
    print(f"wrote {args.out}")
