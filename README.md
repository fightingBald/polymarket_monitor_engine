# Polymarket Monitor Engine ✨

**One‑liner:** watches Polymarket, detects big moves, and blasts alerts to Discord. 🚨
<img width="728" height="234" alt="image" src="https://github.com/user-attachments/assets/c411d586-9725-4924-b1f3-d701f5c68c08" />

## 0) Defaults  ✅

From `config/config.yaml` (single source of truth):

- Redis: **OFF**
- Discord: **ON** (needs `DISCORD_WEBHOOK_URL` in `.env`)
- Dashboard (TUI): **ON**
- Stdout sink: **OFF** (keeps the TUI clean)
- Logs: **write to `logs/pme.log`** (console quiet)
- `.env` is auto‑loaded on startup (so `DISCORD_WEBHOOK_URL` works)

Override order: `config/config.yaml` → `.env` → `PME__...` env vars.

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

## 3) Config Cheatsheet 🧠

**Primary config:** `config/config.yaml`  
**Secrets:** `.env` (git‑ignored)  
**Temporary override:** `PME__...` env vars

List‑type envs accept CSV (no JSON needed), e.g. `PME__APP__CATEGORIES=finance,politics`.
`filters.top_k_per_category=0` means **no limit** (monitor as many as possible).
`rolling.enabled=false` means **don’t collapse by topic** (keeps more markets).
`gamma.events_limit_per_category=100` caps events per category **after full fetch + active filter + ranking** (volume → liquidity). More API calls, smaller WS payload. 🧯
`filters.focus_keywords=trump,iran,strike` focuses monitoring to matching keywords (case‑insensitive). 🎯
`gamma.events_sort_primary/secondary` control event ranking (default: `volume24hr` → `liquidity`). ⚡
`signals.major_change_low_price_max=0.05` sets low‑price zone upper bound (e.g. 5¢). 🧊
`signals.major_change_low_price_abs=0.01` sets absolute move required in low‑price zone (e.g. 1¢). 🪓
`signals.major_change_spread_gate_k=1.5` gates moves smaller than `k * spread` (kills bounce noise). 🛑

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
- Sort is configurable via `dashboard.sort_by` (`activity`/`vol_1m`/`last_trade`/`updated`/`category`/`title`).

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
  - `sinks.discord.log_payloads` + `sinks.discord.log_payloads_path` (logs all outgoing payloads). 🧷📄
- On startup, Discord receives a **“connected + monitored markets”** status message.
- Lifecycle alerts are **only for monitored markets**; `removed` means **removed from monitoring**, not delisted. 🧹
- Health checks are **not** sent to Discord by default (noise‑free).
- Category counts are **event-based** (closer to website numbers) and stats include events/markets/tokens.

## 6) Website “Top” Markets 🏆

```bash
PME__TOP__ENABLED=true make run
```

Optional:
- `PME__TOP__LIMIT`
- `PME__TOP__ORDER` (default `volume24hr`)
- `PME__TOP__FEATURED_ONLY` (closest to website Top)

## 7) Logging 🧾

Default: logs go to `logs/pme.log` and the console stays quiet.  
Want console logs back?

```bash
PME__LOGGING__CONSOLE=true make run
```

## 8) Commands 🛠️

```bash
make build
make lint
make test
make run
make run-dashboard
make diagnose
```

## 9) Diagnostics 🔍

```bash
make diagnose
```

## 10) Notes 📝

- No API key required for public Gamma/CLOB endpoints.
- `enableOrderBook=false` markets are **displayed** but not subscribed; they still trigger **refresh‑based volume alerts** (`web_volume_spike`).
- WS 发包会按 `clob.max_frame_bytes` 自动分包；如果还爆 `1009 message too big`，把 `clob.max_message_bytes` 调大或关 `clob.initial_dump`。🧱
- Uses `uvloop` when available for faster async.
- Gamma rate limiting is handled by `aiolimiter`.
- Config merge uses `deepmerge` (lists override instead of append).
- Tag cache uses `cachetools` TTL cache.
- Discord category stats use `pandas` for concise grouping.

## 11) Repo Layout 🧱

```text
src/
  polymarket_monitor_engine/
    application/
      component.py
      monitor.py
      signals/
        detector.py
        STRATEGY_LOG.md
```
