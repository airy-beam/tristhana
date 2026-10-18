#!/usr/bin/env bash
# Smoke-test a built backend image: ./infra/ci/container-smoke.sh IMAGE
# ENGINE=podman to use Podman locally (default: docker). Spec NF-02 §7.
set -euo pipefail

image="${1:?usage: container-smoke.sh IMAGE}"
engine="${ENGINE:-docker}"
max_mb="${MAX_IMAGE_MB:-250}" # approximate: docker and podman report .Size differently
name="tristhana-smoke-$$"

run() { "$engine" run --rm -i --entrypoint "$1" "$image" "${@:2}"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

echo "== user"
uid="$(run id -u)"
[[ "$uid" != "0" ]] || fail "container runs as root"

echo "== no build tools or dev deps"
run sh -c 'command -v gcc' >/dev/null 2>&1 && fail "gcc present in runtime image"
run python -c 'import pytest' >/dev/null 2>&1 && fail "pytest present in runtime image"

echo "== moon module, ephemeris, seed data, time zones (installed package)"
run python - <<'PY'
import os
from datetime import date
from importlib.resources import files
from pathlib import Path
from zoneinfo import ZoneInfo

from tristhana.domain.moon import MoonDay, MoonDayKind, MoonLocation
from tristhana.infrastructure.seed.catalog_yaml import load_catalog
from tristhana.moon import compute_moon_days

ephe = files("tristhana.moon") / "ephe"
assert (ephe / "sepl_18.se1").is_file() and (ephe / "semo_18.se1").is_file(), "ephemeris missing"
mysuru = MoonLocation(12.2958, 76.6394, "Asia/Kolkata")
day = date(2025, 1, 13)
assert compute_moon_days(mysuru, day, day) == [MoonDay(day, MoonDayKind.PURNIMA)], "moon"
seed = Path(os.environ["SEED_DIR"])
load_catalog(seed / "asanas.yaml", seed / "sequences.yaml")
ZoneInfo("Asia/Almaty")
locales = files("tristhana.infrastructure.i18n") / "locales"
assert all((locales / loc / "bot.ftl").is_file() for loc in ("en", "ru")), ".ftl missing"
from tristhana.infrastructure.i18n.fluent import FluentTranslator
assert FluentTranslator().t("ru", "start-greeting").startswith("Намасте"), "fluent"
import aiogram  # noqa: F401  (imports in the slim image)
print("ok")
PY

echo "== size"
bytes="$("$engine" image inspect --format '{{.Size}}' "$image")"
mb=$(( bytes / 1024 / 1024 ))
echo "image size: ${mb} MB (budget ${max_mb} MB)"
(( mb <= max_mb )) || fail "image is ${mb} MB > ${max_mb} MB"

# Telegram webhook with fake credentials: /start must come back as a webhook reply.
webhook_check() {
  echo "== telegram webhook (fake token; aiogram preloaded at startup)"
  local bot="${name}-bot" port started body ms
  "$engine" run -d --rm --name "$bot" -p 127.0.0.1::8080 \
    -e TELEGRAM_BOT_TOKEN=123456:smoke-token-not-real_xxxxxxxxxxxxxxx \
    -e TELEGRAM_WEBHOOK_SECRET=smoke-secret "$image" >/dev/null
  port="$("$engine" port "$bot" 8080 | head -1 | sed 's/.*://')"
  started=$(date +%s%N)
  for _ in $(seq 1 300); do
    curl -fsS "http://127.0.0.1:${port}/api/v1/health" >/dev/null 2>&1 && break
    sleep 0.05
  done
  echo "ready (incl. aiogram preload) after $(( ($(date +%s%N) - started) / 1000000 )) ms"
  local update='{"update_id":1,"message":{"message_id":1,"date":1760000000,
    "chat":{"id":42,"type":"private"},"from":{"id":42,"is_bot":false,"first_name":"A",
    "language_code":"ru"},"text":"/start","entities":[{"type":"bot_command","offset":0,"length":6}]}}'
  for i in 1 2; do
    started=$(date +%s%N)
    body="$(curl -fsS "http://127.0.0.1:${port}/telegram/webhook" \
      -H 'Content-Type: application/json' -H 'X-Telegram-Bot-Api-Secret-Token: smoke-secret' \
      -d "${update/\"update_id\":1/\"update_id\":$i}")"
    ms=$(( ($(date +%s%N) - started) / 1000000 ))
    echo "/start #$i answered in ${ms} ms"
  done
  "$engine" rm -f "$bot" >/dev/null
  [[ "$body" == *'"method":"sendMessage"'* && "$body" == *'Намасте'* ]] || fail "webhook reply: $body"
}

echo "== start and /api/v1/health"
"$engine" run -d --rm --name "$name" -p 127.0.0.1::8080 -e GIT_SHA=smoke "$image" >/dev/null
trap '"$engine" rm -f "$name" >/dev/null 2>&1 || true' EXIT
hostport="$("$engine" port "$name" 8080 | head -1 | sed 's/.*://')"
start=$(date +%s%N)
for _ in $(seq 1 100); do
  if body="$(curl -fsS "http://127.0.0.1:${hostport}/api/v1/health" 2>/dev/null)"; then
    ms=$(( ($(date +%s%N) - start) / 1000000 ))
    echo "first 200 after ${ms} ms: $body"
    [[ "$body" == *'"commit":"smoke"'* ]] || fail "health does not report GIT_SHA"
    "$engine" logs "$name" 2>&1 | sed -n 1,3p # sed reads everything: no SIGPIPE under pipefail
    webhook_check
    echo "PASS"
    exit 0
  fi
  sleep 0.05
done
"$engine" logs "$name" >&2 || true
fail "no 200 from /api/v1/health within 5 s"
