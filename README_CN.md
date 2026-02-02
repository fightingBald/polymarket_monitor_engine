# Polymarket Monitor Engine

这是个用 **Python 3.14** 写的监控件儿，专门盯着 Polymarket 的 finance/geopolitics 盘子，发现大单/放量就吼一嗓子，把规范化的 DomainEvent 往外一甩（Redis + stdout）。

## 目标（把活整明白）

- 分类 → tags → markets → token_ids 这条链必须通。
- 盘子到期/换盘了，订阅得跟着滚，不然就掉线儿了。
- 事件格式固定，能一锅多发（fan-out）给下游。

## 现在能干啥

- Gamma tags → events/markets，把 finance/geopolitics 的热门盘子挑出来（TopK）。
- 组装 token_ids（CLOB 资产 ID）订阅 market 通道。
- 监控大单、1 分钟放量、可选盘口墙。
- 规范化 DomainEvent，stdout + Redis 一锅端。

## 架构（六边形，层次清楚）

- `domain/`：核心模型/事件/筛选逻辑。
- `application/`：编排（刷新、滚动、监控）。
- `ports/`：接口（catalog/feed/sink/clock）。
- `adapters/`：Polymarket Gamma/WS、Redis、stdout。
- `cmd`/`__main__`：组合根，把依赖一把插上。

## 目录树

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

## 快速上手（uv + venv）

1) 先把 `uv` 装上（比如 `brew install uv` 或 `pipx install uv`）。
2) 把 `config/config.example.yaml` 复制成 `config/config.yaml`。
3) 一键整环境（嘎嘎快）：

```bash
make bootstrap
```

4) 启动：

```bash
make run
```

## 运行手册（一步步唠明白）

### 本机方式（推荐）

1) 先装 `uv`：

```bash
brew install uv
# 或
pipx install uv
```

2) 准备配置：

```bash
cp config/config.example.yaml config/config.yaml
```

3) 初始化虚拟环境和依赖：

```bash
make bootstrap
```

4) 先起 Redis（给下游用）：

```bash
docker compose -f deploy/docker-compose.yml up -d redis
```

5) 启动服务：

```bash
make run
```

6) 看输出：

- stdout 会打结构化 JSON 日志
- Redis 默认发到 `polymarket.events` 频道

### Docker 一键方式

```bash
docker compose -f deploy/docker-compose.yml up --build
```

### 常见问题

- Redis 连接失败：确认 Redis 起了，或者把 `config/config.yaml` 里 `sinks.redis.enabled` 设成 `false`。
- DNS/网络错误：确认能访问 `gamma-api.polymarket.com` 和 `ws-subscriptions-clob.polymarket.com`。

## Polymarket API 对齐说明（关键，别整岔了）

- Gamma 默认走 `/events`（更适合全量/分类发现），用 `limit + offset` 分页；想退回 `/markets` 就把 `gamma.use_events_endpoint=false`。
- CLOB WebSocket 默认 `wss://ws-subscriptions-clob.polymarket.com/ws/market`；如果只给 host，会自动补 `/ws/{channel}`。
- 订阅协议：
  - 初始订阅：`{"type":"market","assets_ids":[...],"custom_feature_enabled":true,"initial_dump":true}`
  - 增量订阅/退订：`{"assets_ids":[...],"operation":"subscribe|unsubscribe"}`
- `custom_feature_enabled=true` 能拿到 `best_bid_ask` 等扩展事件；`price_change` 在 2025‑09‑15 23:00 UTC 后用新结构（有 `price_changes` 数组）。

## Rate Limit / 频控建议（别一口吃太猛）

Polymarket 走 Cloudflare 节流，超了会排队不一定直接拒。建议：

- `app.refresh_interval_sec` 别太小（默认 60s）。
- `gamma.request_interval_ms` 给分页请求留点间隔。
- 一轮别扫太多标签/分页。

## 配置重点（重点搁这儿）

- `gamma.use_events_endpoint`: 推荐 true，走 events→markets。
- `gamma.related_tags`: true 会包含关联标签。
- `gamma.request_interval_ms`: 分页请求之间的最小间隔，防止节流。
- `clob.custom_feature_enabled`: 拿 `best_bid_ask` 等扩展事件。
- `clob.initial_dump`: 初始订阅是否回快照。
- `clob.ping_interval_sec`: 应用层心跳（默认 10s，设成 null 可关）。
- `signals.*`: 大单/放量/盘口墙阈值。

## 配置（咋改）

- 配置文件改 `config/config.yaml`。
- 环境变量覆盖用 `PME__` 前缀，`__` 表示层级。

例子：

```bash
export PME__SINKS__REDIS__URL=redis://localhost:6379/0
```

## Docker（想省事就它）

```bash
docker compose -f deploy/docker-compose.yml up --build
```

## 常用命令（常用就这几条）

```bash
make build
make lint
make test
make run
make diagnose
```

## 说明（小结）

- DomainEvent 默认 JSON 编码，发到 Redis 的 `polymarket.events` 频道。
- MVP 只接 Redis；stdout 主要方便本地看日志。
