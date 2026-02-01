#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[docs] Build or lint documentation artifacts."
echo "Suggested commands:"
echo "  - mkdocs build"
echo "  - sphinx-build docs docs/_build"
echo "  - npm run docs"
echo "Update docs/operations.md when you settle on a workflow."
