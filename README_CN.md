# Polymarket Monitor Engine ✨（东北大白话 + Gen‑Z）

**一句话：**盯盘 + 预警，一有大动静就吼你 Discord。🚨

## 0) 默认配置（集中管理）✅

默认值来自 `config/config.yaml`：

- Redis：**默认关**
- Discord：**默认开**（`.env` 里填 `DISCORD_WEBHOOK_URL`）
- 终端仪表盘：**默认开**
- Stdout sink：**默认关**（不糊仪表盘）
- 日志：**写到 `logs/pme.log`**（控制台静默）
- 启动会**自动加载 `.env`**（`DISCORD_WEBHOOK_URL` 会生效）

覆盖顺序：`config/config.yaml` → `.env` → `PME__...` 环境变量。

## 1) 直接跑起来 🚀

```bash
cp config/config.example.yaml config/config.yaml
cp config/.env.example .env  # 把 DISCORD_WEBHOOK_URL 填上
make bootstrap
make run
```

## 2) 启动方式 🧭

### 默认（走配置）
```bash
make run
```

### 一键“仪表盘 + Discord only”
```bash
make run-dashboard
```

## 3) 配置单一入口 🧠

**主配置：**`config/config.yaml`  
**密钥：**`.env`（不会进 git）  
**临时覆盖：**`PME__...`

列表类环境变量支持逗号分隔（不用 JSON），例如 `PME__APP__CATEGORIES=finance,politics`。
`filters.top_k_per_category=0` 表示**不设上限**（尽量多监控）。
`rolling.enabled=false` 表示**不按话题合并**（保留更多盘口）。

例子：
```bash
PME__DASHBOARD__ENABLED=true \
PME__SINKS__DISCORD__ENABLED=true \
PME__SINKS__REDIS__ENABLED=false \
make run
```

## 4) 仪表盘（TUI）🖥️

- 实时看监控盘口 + 报价
- 多选盘会**合成一行**（标“多选盘”）
- 没 orderbook 的盘会**灰掉**标“🚫 无 orderbook”
- 排序可配：`dashboard.sort_by`（`activity`/`vol_1m`/`last_trade`/`updated`/`category`/`title`）

## 5) Discord 预警 🧷

- 用 Incoming Webhook（`DISCORD_WEBHOOK_URL`）
- 多选盘会**按盘聚合**，不会刷屏
- 可调参数：
  - `sinks.discord.aggregate_multi_outcome`
  - `sinks.discord.aggregate_window_sec`
  - `sinks.discord.aggregate_max_items`
- 启动时会自动发一条“已连接 + 监控盘口列表”的状态消息。
- 健康检查**默认不往 Discord 发**（少打扰）。
- 分类统计按**事件数**统计（更接近网页显示），同时也会显示 markets/tokens。

## 6) 网页 Top 盘子 🏆

```bash
PME__TOP__ENABLED=true make run
```

可调：
- `PME__TOP__LIMIT`
- `PME__TOP__ORDER`（默认 `volume24hr`）
- `PME__TOP__FEATURED_ONLY`（更贴近网页 Top）

## 7) 日志 🧾

默认日志写到 `logs/pme.log`，控制台安静。  
想看日志：

```bash
PME__LOGGING__CONSOLE=true make run
```

## 8) 常用命令 🛠️

```bash
make build
make lint
make test
make run
make run-dashboard
make diagnose
```

## 9) 一键自检 🔍

```bash
make diagnose
```

## 10) 说明 📝

- 不用 API Key。
- `enableOrderBook=false` 的盘子会显示但不订阅；仍会用刷新间隔的成交量变化触发预警（`web_volume_spike`）。
