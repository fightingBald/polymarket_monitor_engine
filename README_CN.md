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
# 直接改 config/config.yaml
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
`gamma.events_limit_per_category=100` 表示**先全量拉取 + 过滤 active 再按成交量→流动性排**，再限流每分类事件数（请求更重但 WS 订阅更小更稳）。🧯
`filters.focus_keywords=trump,iran,strike` 表示只监控匹配关键词的盘口（不区分大小写）。🎯
`gamma.events_sort_primary/secondary` 控制事件排序字段（默认 `volume24hr` → `liquidity`）。⚡
`signals.major_change_low_price_max=0.05` 低价区上限（比如 5¢）。🧊
`signals.major_change_low_price_abs=0.01` 低价区绝对变动阈值（比如 1¢）。🪓
`signals.major_change_spread_gate_k=1.5` 价差门控：小于 `k * spread` 的跳动直接过滤。🛑
`signals.high_confidence_threshold=0.90` 过滤“高置信度吃低保”大单（max(price,1-price) >= 阈值）。🧯
`signals.reverse_allow_threshold=0.25` 反向低价大单放行（price <= 阈值）。🛡️
`signals.drop_expired_markets=true` 过期盘（`end_ts` 已过）直接踢出监控 + 不响。🧹
`signals.merge_window_sec=60` 60 秒内合并交易信号（拆单噪声克星）。🧷

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
  - `sinks.discord.log_payloads` + `sinks.discord.log_payloads_path`（把所有 Discord 出站消息落盘）。🧷📄
- 启动时会自动发一条“已连接 + 监控盘口列表”的状态消息。
- 生命周期/新盘口/移出监控 **不再发 Discord**（只记日志）。🧹
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

默认日志写到 `logs/pme-{ts}.log`（每次启动单独一份），控制台安静。  
想看日志：

```bash
PME__LOGGING__CONSOLE=true make run
```

小贴士：`logging.file_path` 支持 `{ts}`（格式 `YYYYMMDD-HHMMSS`）。✨
退出时会打 `component_exit`，带 `exit_at`（本地时间 HH:MM:SS）。🧾

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
- WS 发包会按 `clob.max_frame_bytes` 自动分包；如果还爆 `1009 message too big`，把 `clob.max_message_bytes` 调大或关 `clob.initial_dump`。🧱
- 有 `uvloop` 就自动启用（更快）。
- Gamma 限流由 `aiolimiter` 管。
- 配置合并用 `deepmerge`（list 直接覆盖，不拼接）。
- 标签缓存用 `cachetools` TTL。
- Discord 分类统计用 `pandas` 分组更干净。

## 11) 目录结构 🧱

```text
src/
  polymarket_monitor_engine/
    application/
      component.py
      monitor.py
      signals/
        detector.py
        STRATEGY_LOG.md
    domain/
      events.py
      models.py
      schemas/
        event_payloads.py
```
