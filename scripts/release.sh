#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[release] Prepare artifacts for distribution."
echo "Replace with concrete steps such as:"
echo "  - npm version && npm publish"
echo "  - poetry build"
echo "  - goreleaser release --snapshot"
echo "Ensure release steps are idempotent and documented."
