#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"${ROOT_DIR}/scripts/_ensure_uv.sh"

echo "[bootstrap] Creating venv and installing dependencies..."
uv venv "${ROOT_DIR}/.venv" --python 3.14
source "${ROOT_DIR}/.venv/bin/activate"
uv pip install -e "${ROOT_DIR}[dev]"
