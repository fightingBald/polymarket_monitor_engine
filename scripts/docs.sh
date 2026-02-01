#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -d "${ROOT_DIR}/docs" ]; then
  echo "[docs] No docs directory found."
  exit 0
fi

echo "[docs] No build step configured. Verify docs content manually."
