# Polymarket Monitor Engine（东北大白话版）

一句话：这是个盯盘的，Polymarket 有大动静就喊一嗓子，往 stdout / Redis / Discord 发。

## 这玩意儿能干啥

- 去 Gamma 把盘子拉一遍，按流动性/成交量筛选。
- 订阅 CLOB WS，序号断档就自动重订。
- 盯：大单、1 分钟放量、盘口大墙、短时间大幅波动。
- 统一成 DomainEvent 往下游扔。

## 你得准备啥

- Python 3.14
- `uv`
- Redis（不用就关掉 Redis sink）

## 傻瓜式跑起来（照抄就行）

1) 先抄配置：

```bash
cp config/config.example.yaml config/config.yaml
```

2) Discord 想用就整个 `.env`（本地留着，别往 Git 提交）：

```bash
cp config/.env.example .env
# 打开 .env，把 DISCORD_WEBHOOK_URL 填上
```

3) 一键整环境：

```bash
make bootstrap
```

4) 起 Redis（不用就把 `sinks.redis.enabled=false`）：

```bash
docker compose -f deploy/docker-compose.yml up -d redis
```

5) 开跑：

```bash
make run
```

### 一行命令临时跑

```bash
DISCORD_WEBHOOK_URL=... PME__SINKS__DISCORD__ENABLED=true make run
```

### 只要 Discord 预警（不启 Redis）

```bash
DISCORD_WEBHOOK_URL=... \
  PME__SINKS__DISCORD__ENABLED=true \
  PME__SINKS__REDIS__ENABLED=false \
  PME__SINKS__STDOUT__ENABLED=false \
  make run
```

提示：如果你还想本地看日志，就别关 stdout。

## Docker 懒人包（全家桶）

```bash
docker compose -f deploy/docker-compose.yml up --build
```

## 重大变动规则咋配

主要看 `signals.*`：

- `major_change_pct`：涨跌幅阈值（百分比）
- `major_change_window_sec`：多久内算变动
- `major_change_min_notional`：只看成交额够大的变动
- `major_change_source`：`trade` / `book` / `any`

## Discord 通知长啥样

- Embed 里写清楚市场名、摘要、方向、价格（统一成美分）、链接。
- 方向颜色：YES 绿 / NO 红。

## 常用命令（记这几个就够）

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

## 要不要 API Key？

不用。Gamma + CLOB 公共接口目前都是公开的。

## 目录里的中文说明

`src/polymarket_monitor_engine/*/README_CN.md` 都是中文设计说明。
