#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[test] Executing fast test suite..."
echo "Swap the placeholder output with real commands, e.g.:"
echo "  - pytest"
echo "  - npm test -- --watch=false"
echo "  - go test ./..."
echo "Keep tests deterministic and fast; move slow scenarios into ci-test."
