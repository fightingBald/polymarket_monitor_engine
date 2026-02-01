# Polymarket Monitor Engine

A Python 3.14 component that monitors Polymarket finance/geopolitics markets, detects large trades/volume spikes, and emits normalized DomainEvents to pluggable sinks (Redis + stdout).

## Goals

- Resolve categories → tags → markets → token_ids dynamically.
- Keep subscriptions fresh as markets roll or close.
- Emit stable DomainEvents and fan-out to sinks.

## What It Does Today

- Pulls Gamma tags → events/markets to discover finance/geopolitics markets and select TopK hot markets.
- Builds token_ids (CLOB asset IDs) and subscribes via the CLOB market channel.
- Detects Big Trade, 1‑minute Volume Spike, and optional Big Wall signals.
- Emits normalized DomainEvents to stdout + Redis (fan‑out).

## Architecture

Hexagonal layout with clear boundaries:

- `domain/`: core models/events/selection logic.
- `application/`: orchestration (refresh, rolling, monitoring).
- `ports/`: interfaces for catalog/feed/sink/clock.
- `adapters/`: Polymarket Gamma/WS, Redis, stdout.
- `cmd`/`__main__`: composition root.

## Directory tree

```
.
├── .gitignore
├── .dockerignore
├── .python-version
├── Dockerfile
├── config/
│   └── config.example.yaml
├── deploy/
│   └── docker-compose.yml
├── docs/
│   ├── ci-setup.md
│   └── operations.md
├── scripts/
├── src/
│   └── polymarket_monitor_engine/
│       ├── adapters/
│       ├── application/
│       ├── domain/
│       ├── ports/
│       ├── util/
│       ├── __init__.py
│       └── __main__.py
├── tests/
├── Makefile
├── pyproject.toml
└── roadmap.md
```

## Quickstart (uv + venv)

1) Install `uv` (e.g. `brew install uv` or `pipx install uv`).
2) Copy `config/config.example.yaml` to `config/config.yaml`.
3) Bootstrap the venv + deps:

```bash
make bootstrap
```

4) Run:

```bash
make run
```

## 运行手册（一步步）

### 本机方式（推荐）

1) 安装 `uv`：

```bash
brew install uv
# 或
pipx install uv
```

2) 准备配置：

```bash
cp config/config.example.yaml config/config.yaml
```

3) 初始化虚拟环境与依赖：

```bash
make bootstrap
```

4) 启动 Redis（用于事件下游）：

```bash
docker compose -f deploy/docker-compose.yml up -d redis
```

5) 启动服务：

```bash
make run
```

6) 查看输出：

- stdout 会打印结构化 JSON 日志
- Redis 默认发布到 `polymarket.events` 频道

### Docker 一键方式

```bash
docker compose -f deploy/docker-compose.yml up --build
```

### 常见问题

- Redis 连接失败：确认 Redis 已启动，或在 `config/config.yaml` 中将 `sinks.redis.enabled` 设为 `false`。
- DNS/网络错误：确认本机能访问 `gamma-api.polymarket.com` 和 `ws-subscriptions-clob.polymarket.com`。

## Polymarket API 对齐说明（关键）

- Gamma 侧默认走 `/events`（更适合全量/分类发现），用 `limit + offset` 分页；如需退回 `/markets`，将 `gamma.use_events_endpoint=false`。
- CLOB WebSocket 默认使用 `wss://ws-subscriptions-clob.polymarket.com/ws/market`；若传入的是裸 host，会自动补 `/ws/{channel}`。
- 订阅协议：
  - 初始订阅：`{"type":"market","assets_ids":[...],"custom_feature_enabled":true,"initial_dump":true}`
  - 增量订阅/退订：`{"assets_ids":[...],"operation":"subscribe|unsubscribe"}`
- `custom_feature_enabled=true` 时会收到 `best_bid_ask` 等扩展事件；`price_change` 在 2025‑09‑15 23:00 UTC 之后使用新结构（含 `price_changes` 数组）。

## Rate Limit / 频控建议

Polymarket API 由 Cloudflare 节流，超限会排队而不是立刻拒绝。建议：

- `app.refresh_interval_sec` 不要太小（默认 60s）。
- `gamma.request_interval_ms` 用来给分页请求加间隔。
- 避免在一轮刷新里打太多标签/分页。

## Configuration Highlights

- `gamma.use_events_endpoint`: 推荐 true，走 events→markets 方式。
- `gamma.related_tags`: true 时会包含关联标签的市场。
- `gamma.request_interval_ms`: 分页请求之间的最小间隔，避免触发节流。
- `clob.custom_feature_enabled`: 获取 `best_bid_ask` 等扩展事件。
- `clob.initial_dump`: 初始订阅时是否发快照。
- `clob.ping_interval_sec`: 应用层心跳（默认 10s，可设为 null 关闭）。
- `signals.*`: 大单/放量/盘口墙阈值。

## Configuration

- Copy `config/config.example.yaml` and edit values.
- Environment overrides use the prefix `PME__` with `__` for nesting.

Example:

```bash
export PME__SINKS__REDIS__URL=redis://localhost:6379/0
```

## Docker

```bash
docker compose -f deploy/docker-compose.yml up --build
```

## Commands

```bash
make build
make lint
make test
make run
make diagnose
```

## Notes

- DomainEvents are JSON-encoded and published to Redis channel `polymarket.events` by default.
- Redis is the only external sink in MVP; stdout logging is kept for local inspection.
