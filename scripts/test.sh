#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"${ROOT_DIR}/scripts/_ensure_uv.sh"

if [ ! -d "${ROOT_DIR}/.venv" ]; then
  echo "[test] Missing .venv. Run: make bootstrap"
  exit 1
fi

source "${ROOT_DIR}/.venv/bin/activate"
pytest "${ROOT_DIR}/tests"
