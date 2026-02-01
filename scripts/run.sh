#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[run] Start your application or service locally."
echo "Replace this script with the command that launches your project."
echo "Examples:"
echo "  - uvicorn app.main:app --reload"
echo "  - npm run dev"
echo "  - go run ./cmd/server"
echo "Document any prerequisites in README.md and docs/operations.md."
