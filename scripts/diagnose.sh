#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

hosts=(
  "gamma-api.polymarket.com"
  "ws-subscriptions-clob.polymarket.com"
)

print_header() {
  echo "[diagnose] $1"
}

print_header "DNS resolution"
for host in "${hosts[@]}"; do
  if python3 - <<PY
import socket
try:
    print(socket.gethostbyname("$host"))
except Exception as e:
    raise SystemExit(str(e))
PY
  then
    :
  else
    echo "[diagnose] $host: DNS lookup failed" >&2
    exit 1
  fi
  echo "[diagnose] $host: OK"
done

print_header "Gamma API reachability"
if command -v curl >/dev/null 2>&1; then
  curl -sS -o /dev/null -w "[diagnose] gamma /tags: HTTP %{http_code}\n" "https://gamma-api.polymarket.com/tags"
else
  echo "[diagnose] curl not found" >&2
  exit 1
fi

print_header "WebSocket host reachability"
if command -v nc >/dev/null 2>&1; then
  nc -z -w 3 ws-subscriptions-clob.polymarket.com 443 && echo "[diagnose] ws host: TCP 443 OK"
else
  echo "[diagnose] nc not found, skipping TCP check"
fi

print_header "Config presence"
if [ -f "${ROOT_DIR}/config/config.yaml" ]; then
  echo "[diagnose] config/config.yaml: OK"
else
  echo "[diagnose] config/config.yaml: missing" >&2
  exit 1
fi

print_header "Done"
