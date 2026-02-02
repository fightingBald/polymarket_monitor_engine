# Polymarket Monitor Engine ✨

**One‑liner:** watches Polymarket, detects big moves, and blasts alerts to Discord. 🚨

## 0) Defaults (集中配置) ✅

Out of the box (from `config/config.yaml`):

- Redis: **OFF**
- Discord: **ON** (needs `DISCORD_WEBHOOK_URL`)
- Dashboard (TUI): **ON**
- Stdout sink: **OFF** (keeps the dashboard clean)

You can override with `.env` or env vars.

## 1) Quickstart 🚀

```bash
cp config/config.example.yaml config/config.yaml
cp config/.env.example .env  # put DISCORD_WEBHOOK_URL here
make bootstrap
make run
```

## 2) Run Modes 🧭

### Normal (uses config)
```bash
make run
```

### Dashboard + Discord only (explicit)
```bash
make run-dashboard
```

## 3) Config (Single Source of Truth) 🧠

**Primary config:** `config/config.yaml`  
**Secrets:** `.env` (git‑ignored)  
**Temporary override:** `PME__...` env vars

Example:
```bash
PME__DASHBOARD__ENABLED=true \
PME__SINKS__DISCORD__ENABLED=true \
PME__SINKS__REDIS__ENABLED=false \
make run
```

## 4) Dashboard (TUI) 🖥️

- Live view of monitored markets + prices.
- Multi‑outcome markets are grouped into **one row** (marked “多选盘”).
- Markets without orderbook show **gray** as “🚫 无 orderbook”.

Enable (if you turned it off):
```bash
PME__DASHBOARD__ENABLED=true make run
```

## 5) Discord Alerts 🧷

- Uses Incoming Webhook: `DISCORD_WEBHOOK_URL`.
- Multi‑outcome alerts are **aggregated per market** to avoid spam.
- Adjustable:
  - `sinks.discord.aggregate_multi_outcome`
  - `sinks.discord.aggregate_window_sec`
  - `sinks.discord.aggregate_max_items`

## 6) Website “Top” Markets 🏆

```bash
PME__TOP__ENABLED=true make run
```

Optional:
- `PME__TOP__LIMIT`
- `PME__TOP__ORDER` (default `volume24hr`)
- `PME__TOP__FEATURED_ONLY` (closest to website Top)

## 7) Commands 🛠️

```bash
make build
make lint
make test
make run
make run-dashboard
make diagnose
```

## 8) Diagnostics 🔍

```bash
make diagnose
```

Checks DNS + Gamma + WS reachability and config presence.

## 9) Notes 📝

- No API key required for public Gamma/CLOB endpoints.
- `enableOrderBook=false` markets are **displayed** but not subscribed; they still trigger **refresh‑based volume alerts** (`web_volume_spike`).
