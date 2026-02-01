#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"${ROOT_DIR}/scripts/_ensure_uv.sh"

if [ ! -d "${ROOT_DIR}/.venv" ]; then
  echo "[run] Missing .venv. Run: make bootstrap"
  exit 1
fi

source "${ROOT_DIR}/.venv/bin/activate"

CONFIG_ARG=""
if [ -f "${ROOT_DIR}/config/config.yaml" ]; then
  CONFIG_ARG="--config ${ROOT_DIR}/config/config.yaml"
fi

python -m polymarket_monitor_engine ${CONFIG_ARG}
