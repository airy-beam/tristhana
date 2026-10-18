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
print("ok")
PY

echo "== size"
bytes="$("$engine" image inspect --format '{{.Size}}' "$image")"
mb=$(( bytes / 1024 / 1024 ))
echo "image size: ${mb} MB (budget ${max_mb} MB)"
(( mb <= max_mb )) || fail "image is ${mb} MB > ${max_mb} MB"

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
    "$engine" logs "$name" 2>&1 | head -3
    echo "PASS"
    exit 0
  fi
  sleep 0.05
done
"$engine" logs "$name" >&2 || true
fail "no 200 from /api/v1/health within 5 s"
