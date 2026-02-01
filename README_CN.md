# Polymarket Monitor Engine

这是个用 **Python 3.14** 写的监控组件，专门盯着 Polymarket 的 finance/geopolitics 盘子，发现大单/放量就吼一嗓子，把规范化的 DomainEvent 往外发（Redis + stdout）。

## 目标（把活整明白）

- 分类 → tags → markets → token_ids 这条链必须通。
- 盘子到期/换盘了，订阅得跟着滚，不然就掉线儿了。
- 事件格式固定，能一锅多发（fan-out）给下游。

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
3) 一键整环境：

```bash
make bootstrap
```

4) 启动：

```bash
make run
```

## 运行手册（一步步）

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
- DNS/网络错误：确认能访问 `gamma-api.polymarket.com` 和 `clob.polymarket.com`。

## 配置

- 配置文件改 `config/config.yaml`。
- 环境变量覆盖用 `PME__` 前缀，`__` 表示层级。

例子：

```bash
export PME__SINKS__REDIS__URL=redis://localhost:6379/0
```

## Docker

```bash
docker compose -f deploy/docker-compose.yml up --build
```

## 常用命令

```bash
make build
make lint
make test
make run
```

## 说明

- DomainEvent 默认 JSON 编码，发到 Redis 的 `polymarket.events` 频道。
- MVP 只接 Redis；stdout 主要方便本地看日志。
