# Polymarket Monitor Engine（东北大白话版）

一句话：这是个盯盘的，盯 Polymarket 的金融/地缘盘子，有大单和放量就吼一嗓子，往 stdout 和 Redis 里发。

## 这玩意儿能干啥

- 先去 Gamma 把标签和盘子拉一遍
- 把 token_id（CLOB 资产 ID）整出来订阅
- 监控大单、1 分钟放量、可选盘口墙
- 统一格式发 DomainEvent

## 傻瓜式一键起跑（照抄就行）

1) 先装 `uv`（CI 里没装会自动拉）：

```bash
brew install uv
# 或
pipx install uv
```

2) 把配置抄一份：

```bash
cp config/config.example.yaml config/config.yaml
```

3) 一键整环境：

```bash
make bootstrap
```

4) 起 Redis（下游得用）：

```bash
docker compose -f deploy/docker-compose.yml up -d redis
```

5) 开跑：

```bash
make run
```

看到 stdout 有 JSON 日志，Redis 频道默认是 `polymarket.events`，就说明跑起来了。

## Docker 懒人包（想省事就它）

```bash
docker compose -f deploy/docker-compose.yml up --build
```

## 配置咋改

- 文件：`config/config.yaml`
- 环境变量：前缀 `PME__`，层级用 `__`

例子：

```bash
export PME__SINKS__REDIS__URL=redis://localhost:6379/0
```

常用几个重点：

- `gamma.use_events_endpoint=true`（推荐）
- `gamma.request_interval_ms`（别请求太猛）
- `clob.custom_feature_enabled=true`（多点事件）
- `clob.initial_dump=true`（订阅先来快照）
- `clob.ping_interval_sec`（心跳，不要就设 null）

## 常用命令（记这几个就行）

```bash
make build
make lint
make test
make run
make diagnose
```

## 一键自检

```bash
make diagnose
```

会检查 DNS、Gamma、WS 和配置文件。

## 常见翻车原因

- Redis 连不上：要么 Redis 没起，要么把 `sinks.redis.enabled=false`。
- DNS/网络问题：确认能访问 `gamma-api.polymarket.com` 和 `ws-subscriptions-clob.polymarket.com`。

## 要不要 API Key？

不用。这俩接口（Gamma + CLOB 公共 WS）目前都是公开的。
