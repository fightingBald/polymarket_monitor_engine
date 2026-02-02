# Polymarket Monitor Engine

A Python 3.14 service that watches Polymarket markets, detects major moves (big trades, volume spikes, order-book walls, rapid price changes), and emits normalized DomainEvents to stdout/Redis/Discord.

## Highlights

- Gamma discovery + rolling selection with filters (liquidity, volume, keywords).
- CLOB WebSocket feed with optional snapshot, ping, and resubscribe on sequence gaps.
- Signals: big trade, 1-minute volume spike, big wall, major change (pct within window).
- Multiplex sinks with routes; Discord embeds with retries for 429/5xx.
- Built-in diagnostics for DNS and API reachability.

## Architecture

Hexagonal layout with clear boundaries:

- `domain/`: models and `DomainEvent` contract
- `application/`: orchestration and signal detection
- `ports/`: interfaces for catalog/feed/sink/clock
- `adapters/`: Gamma HTTP, CLOB WS, Redis, stdout, Discord
- `util/`: logging, IDs, HTTP client setup

## Quickstart (local)

Prereqs: Python 3.14, `uv`, Redis (or disable the Redis sink).

1) Copy config:

```bash
cp config/config.example.yaml config/config.yaml
```

2) Optional: keep secrets local via `.env` (recommended for Discord):

```bash
cp config/.env.example .env
# edit .env and set DISCORD_WEBHOOK_URL
```

3) Bootstrap venv + deps:

```bash
make bootstrap
```

4) Start Redis (optional if you disable it in config):

```bash
docker compose -f deploy/docker-compose.yml up -d redis
```

5) Run:

```bash
make run
```

### One-line run

```bash
DISCORD_WEBHOOK_URL=... PME__SINKS__DISCORD__ENABLED=true make run
```

### Discord-only alerts (no Redis)

If you only want alerts pushed to Discord, disable Redis (and optionally stdout):

```bash
DISCORD_WEBHOOK_URL=... \
  PME__SINKS__DISCORD__ENABLED=true \
  PME__SINKS__REDIS__ENABLED=false \
  PME__SINKS__STDOUT__ENABLED=false \
  make run
```

Tip: keep stdout enabled if you still want local logs while Discord is the only alert channel.

## Docker (all-in-one)

```bash
docker compose -f deploy/docker-compose.yml up --build
```

## Configuration

- Main file: `config/config.yaml`
- Env overrides: `PME__` prefix and `__` nesting (loaded from `.env` by default)

Key knobs:

- `filters.*`: selection rules (top K, liquidity/volume priority, keywords)
- `signals.*`: thresholds and major change rules
- `clob.*`: WS settings, snapshot, ping, resync on gap
- `sinks.*`: enable/disable sinks and route event types

Routes example (only send TradeSignal/HealthEvent to Discord):

```yaml
sinks:
  routes:
    TradeSignal: [stdout, redis, discord]
    HealthEvent: [stdout, redis, discord]
```

## Discord Webhook

- Set `DISCORD_WEBHOOK_URL` (Incoming Webhook) in `.env` or environment.
- Keep it local; `.env` is git-ignored.
- Messages are sent as embeds with market title, summary, direction color (YES green / NO red), price in cents, and a link to the market page.

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

Checks DNS resolution, Gamma API reachability, WebSocket host TCP connectivity, and config presence.

## Notes

- No API key is required for public Gamma/CLOB endpoints.
- Markets without `enableOrderBook=true` are skipped from subscriptions.
- Chinese module docs live in `src/polymarket_monitor_engine/*/README_CN.md`.
