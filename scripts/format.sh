#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[format] Apply automated code formatting..."
echo "Populate this script with the formatters relevant to your stack:"
echo "  - prettier --write \"src/**/*.{ts,tsx,js,jsx,json,css,md}\""
echo "  - black ${ROOT_DIR}/src ${ROOT_DIR}/tests"
echo "  - gofmt -w ."
