# Polymarket Monitor Engine

A Python 3.14 component that monitors Polymarket finance/geopolitics markets, detects large trades/volume spikes, and emits normalized DomainEvents to pluggable sinks (Redis + stdout).

## Goals

- Resolve categories → tags → markets → token_ids dynamically.
- Keep subscriptions fresh as markets roll or close.
- Emit stable DomainEvents and fan-out to sinks.

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
- DNS/网络错误：确认本机能访问 `gamma-api.polymarket.com` 和 `clob.polymarket.com`。

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
```

## Notes

- DomainEvents are JSON-encoded and published to Redis channel `polymarket.events` by default.
- Redis is the only external sink in MVP; stdout logging is kept for local inspection.
