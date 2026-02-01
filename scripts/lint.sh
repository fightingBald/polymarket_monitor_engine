#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[lint] Running static analysis placeholders..."
echo "Replace this script with language-aware linters, for example:"
echo "  - npm run lint"
echo "  - ruff check ${ROOT_DIR}/src"
echo "  - golangci-lint run ./..."
echo "Ensure the same commands run in CI."
