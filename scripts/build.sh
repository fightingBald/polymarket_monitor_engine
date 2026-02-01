#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"${ROOT_DIR}/scripts/_ensure_uv.sh"

if [ ! -d "${ROOT_DIR}/.venv" ]; then
  echo "[build] Missing .venv. Run: make bootstrap"
  exit 1
fi

source "${ROOT_DIR}/.venv/bin/activate"
python -m compileall "${ROOT_DIR}/src"
