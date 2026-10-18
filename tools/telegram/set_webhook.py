"""Register (or inspect) the prod bot's webhook. Run once after a deploy that has the secrets.

    python3 tools/telegram/set_webhook.py          # setWebhook
    python3 tools/telegram/set_webhook.py --info   # getWebhookInfo

Reads the bot token and webhook secret from Secret Manager with your gcloud login and
never prints them; the webhook URL never contains the token. Stdlib only.
Rotation: add a new secret version → redeploy → run this again.
"""

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any

PROJECT = "braided-trees-444417-u6"
REGION = "europe-west3"
SERVICE = "tristhana-api"
WEBHOOK_PATH = "/telegram/webhook"
ALLOWED_UPDATES = ["message", "callback_query"]


def gcloud(*args: str) -> str:
    out = subprocess.run(  # noqa: S603 - fixed command (gcloud on PATH), our own arguments
        ["gcloud", *args, "--project", PROJECT],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    )
    return out.stdout.strip()


def secret(name: str) -> str:
    return gcloud("secrets", "versions", "access", "latest", "--secret", name)


def webhook_payload(service_url: str, webhook_secret: str) -> dict[str, Any]:
    return {
        "url": service_url.rstrip("/") + WEBHOOK_PATH,
        "secret_token": webhook_secret,
        "allowed_updates": ALLOWED_UPDATES,
        "drop_pending_updates": True,
        "max_connections": 10,
    }


def call(token: str, method: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload or {}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            return json.loads(response.read())
    except urllib.error.HTTPError as e:  # the error URL contains the token: never print it
        try:
            return json.loads(e.read())
        except ValueError:
            return {"ok": False, "description": f"HTTP {e.code}"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--info", action="store_true", help="only print getWebhookInfo")
    args = parser.parse_args()

    token = secret("telegram-bot-token")
    if not args.info:
        url = gcloud(
            "run", "services", "describe", SERVICE, "--region", REGION,
            "--format", "value(status.url)",
        )  # fmt: skip
        result = call(token, "setWebhook", webhook_payload(url, secret("telegram-webhook-secret")))
        print("setWebhook:", "ok" if result.get("ok") else result.get("description", "failed"))
        if not result.get("ok"):
            return 1

    info = call(token, "getWebhookInfo").get("result", {})
    for key in ("url", "pending_update_count", "last_error_date", "last_error_message"):
        if key in info:
            print(f"{key}: {info[key]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
