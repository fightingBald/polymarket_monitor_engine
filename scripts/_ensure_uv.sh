#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "[bootstrap] uv not found. Installing..."
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  else
    echo "[error] curl is required to install uv. Install uv manually: https://astral.sh/uv"
    exit 1
  fi
  export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "[error] uv is not installed. Install it first (https://astral.sh/uv)."
  exit 1
fi
