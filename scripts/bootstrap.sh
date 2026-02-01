#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[bootstrap] Preparing development environment..."
echo "1. Install language runtimes and package managers required by your project."
echo "2. Install dependencies (npm/pip/go mod/etc.) within ${ROOT_DIR}."
echo "3. Update docs/operations.md after customising this script."

echo "Tip: replace the placeholder instructions in scripts/bootstrap.sh with actual commands (e.g., npm install, pip install -r requirements.txt)."
