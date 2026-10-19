#!/usr/bin/env bash
# Renders an HTML/SVG file to PNG with headless Chrome: render.sh SRC OUT WIDTH HEIGHT
set -euo pipefail
src=$(realpath "$1"); out=$(realpath -m "$2")
google-chrome --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=1 \
  --window-size="$3,$4" --default-background-color=00000000 \
  --screenshot="$out" "file://$src" >/dev/null 2>&1
echo "$out"
