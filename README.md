# Polymarket Monitor Engine ✨

**TL;DR:** It watches Polymarket markets and yells when stuff moves. Big trades, volume spikes, order-book walls, fast price jumps — all normalized into DomainEvents and pushed to stdout / Redis / Discord. 🚨

## Vibe Check (What it does) 👀

- Gamma discovery + rolling selection (liquidity/volume/keywords).
- CLOB WebSocket feed with snapshot, ping, resubscribe on seq gaps.
- Signals: big trade, 1‑min volume spike, big wall, major change.
- Multiplex sinks with routes; Discord embeds with retries for 429/5xx.
- Built‑in DNS/API diagnostics.

## Architecture (clean + modular) 🧩

- `domain/`: models + `DomainEvent` contract
- `application/`: orchestration + signal detection
- `ports/`: interfaces (catalog/feed/sink/clock)
- `adapters/`: Gamma HTTP, CLOB WS, Redis, stdout, Discord
- `util/`: logging, IDs, HTTP client setup

## Quickstart (local) 🚀

**You need:** Python 3.14, `uv`, Redis (or disable Redis sink).

1) Copy config:

```bash
cp config/config.example.yaml config/config.yaml
```

2) Keep secrets local via `.env` (recommended for Discord):

```bash
cp config/.env.example .env
# edit .env and set DISCORD_WEBHOOK_URL
```

3) Bootstrap venv + deps:

```bash
make bootstrap
```

4) Start Redis (optional if disabled in config):

```bash
docker compose -f deploy/docker-compose.yml up -d redis
```

5) Run:

```bash
make run
```

### One‑line run (quick & dirty) 😎

```bash
DISCORD_WEBHOOK_URL=... PME__SINKS__DISCORD__ENABLED=true make run
```

### Discord‑only alerts (no Redis) 🔥

```bash
DISCORD_WEBHOOK_URL=... \
  PME__SINKS__DISCORD__ENABLED=true \
  PME__SINKS__REDIS__ENABLED=false \
  PME__SINKS__STDOUT__ENABLED=false \
  make run
```

Tip: keep stdout on if you still want local logs.

## Docker (all‑in‑one) 🐳

```bash
docker compose -f deploy/docker-compose.yml up --build
```

## Config Cheatsheet 🧠

- Main file: `config/config.yaml`
- Env overrides: `PME__` prefix + `__` nesting (loaded from `.env`)

Key knobs:

- `filters.*`: selection rules
- `signals.*`: thresholds + major change rules
- `clob.*`: WS snapshot/ping/resync
- `sinks.*`: enable/disable + routing

Routes example (only send TradeSignal/HealthEvent to Discord):

```yaml
sinks:
  routes:
    TradeSignal: [stdout, redis, discord]
    HealthEvent: [stdout, redis, discord]
```

## Discord Webhook 🧷

- Set `DISCORD_WEBHOOK_URL` in `.env` or environment.
- Keep it local; `.env` is git‑ignored.
- Embed includes market title, summary, direction color (YES green / NO red), price in cents, and a link.

## Logging Style (Gen‑Z by default) 😤✨

- Default logs are Gen‑Z style with emoji/kaomoji.
- Want boring logs? set:

```bash
PME__LOGGING__STYLE=plain
```

## Commands 🛠️

```bash
make build
make lint
make test
make run
make diagnose
```

## Diagnostics 🔍

```bash
make diagnose
```

Checks DNS resolution, Gamma API reachability, WS TCP connectivity, and config presence.

## Notes 📝

- No API key required for public Gamma/CLOB endpoints.
- Markets without `enableOrderBook=true` are skipped.
- Chinese module docs: `src/polymarket_monitor_engine/*/README_CN.md`.
