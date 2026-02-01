#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

"${ROOT_DIR}/scripts/_ensure_uv.sh"

make -C "${ROOT_DIR}" lint
make -C "${ROOT_DIR}" test
