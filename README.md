# Polymarket Monitor Engine

A Python 3.14 service that watches Polymarket finance/geopolitics markets, detects large trades and volume spikes, and emits normalized DomainEvents to stdout and Redis.

## What It Does

- Discovers markets via Gamma tags -> events/markets.
- Builds token_ids (CLOB asset IDs) and keeps subscriptions fresh.
- Detects signals: big trade, 1-minute volume spike, optional big wall.
- Publishes structured DomainEvents to stdout and Redis.

## Architecture

Hexagonal layout with clear boundaries:

- `domain/`: models, events, selection logic
- `application/`: orchestration and monitoring
- `ports/`: interfaces for catalog/feed/sink/clock
- `adapters/`: Gamma HTTP, CLOB WebSocket, Redis, stdout
- `__main__`: composition root

## Quickstart (local, uv + venv)

1) Install `uv` (e.g. `brew install uv` or `pipx install uv`). `make bootstrap` will auto-install it in CI if missing.
2) Copy config:

```bash
cp config/config.example.yaml config/config.yaml
```

3) Bootstrap venv + deps:

```bash
make bootstrap
```

4) Start Redis:

```bash
docker compose -f deploy/docker-compose.yml up -d redis
```

5) Run:

```bash
make run
```

## Docker (all-in-one)

```bash
docker compose -f deploy/docker-compose.yml up --build
```

## Configuration

- Edit `config/config.yaml`.
- Env overrides use `PME__` and `__` for nesting.

Example:

```bash
export PME__SINKS__REDIS__URL=redis://localhost:6379/0
```

Key knobs:

- `gamma.use_events_endpoint`: use `/events` discovery (recommended).
- `gamma.request_interval_ms`: spacing between page requests.
- `clob.custom_feature_enabled`: enable extended events.
- `clob.initial_dump`: snapshot on subscribe.
- `clob.ping_interval_sec`: app-level heartbeat (set null to disable).

## Commands

```bash
make build
make lint
make test
make run
make diagnose
```

## Diagnostics

```bash
make diagnose
```

Checks DNS + Gamma + WebSocket reachability and config presence.

## Troubleshooting

- Redis connection fails: ensure Redis is running or set `sinks.redis.enabled=false`.
- DNS/network errors: verify access to `gamma-api.polymarket.com` and `ws-subscriptions-clob.polymarket.com`.

## Notes

- DomainEvents are JSON and published to Redis channel `polymarket.events` by default.
- No API key is required for the Gamma/CLOB public endpoints.
