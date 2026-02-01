#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "[error] uv is not installed. Install it first (https://astral.sh/uv)."
  exit 1
fi
