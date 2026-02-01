# ✅ 需求说明：Polymarket Finance/Geopolitics 监控组件（可插拔多下游）

## 0) 组件定位

实现一个独立组件：**PolymarketComponent**

* **上游固定**：只对接 Polymarket（Gamma/目录 API + CLOB WebSocket）
* **下游可配置**：输出可以按需切换，或同时发送给多个下游（fan-out）

组件目标：持续扫描 `finance` 与 `geopolitics` 板块的热门事件/盘口，并实时监控是否出现“大单/放量/（可选：盘口墙）”，生成标准化事件流输出给下游。

---

## 1) 核心功能范围

### 1.1 板块扫描（Discovery）

* 目标板块：

    * `https://polymarket.com/finance`
    * `https://polymarket.com/geopolitics`
* 注意：网页“板块”不是 API 直接可用对象，必须映射为 **Gamma tags/events/markets**。
* 实现方式：

    1. 调用 Gamma `/tags` 获取 tag 列表，动态定位 finance/geopolitics 对应 `tag_id`（不能硬编码）
    2. 用 `tag_id` 调用 `/events` 或 `/markets` 拉取活跃市场（active=true, closed=false，需分页）
    3. 解析得到每个 market 的 YES/NO outcomes 对应的 **token_ids（CLOB assets_ids）**，供 WebSocket 订阅

### 1.2 热门筛选（Hot Filter）

* 对每个板块输出 Top K 热门市场候选（可配置 `top_k_per_category`）
* 热门排序/过滤依据（至少包含一种，推荐组合）：

    * liquidity（优先）
    * volume_24h（次之）
    * 其他可选指标（价格变化/成交频率）
* 输出：每个 category 的候选 market 列表（market_id、question/title、token_ids、liquidity、volume_24h、end_ts 等）

### 1.3 到期滚动/换盘（Rolling）

* 问题：盘子会到期/结算/关闭，可能会出现“同主题下一期新盘”
* 要求：组件不能死盯单个 `market_id`，必须支持“主题连续性”
* 机制：

    * 每次目录刷新时检测 market 状态：active/closed/resolved/end_ts
    * 对同一 topic（主题）可能存在多个活盘时，选择一个 **primary market** 作为当前监控对象
* primary 选择策略（可配置优先级）：

    1. liquidity 最大
    2. volume_24h 最大
    3. end_ts 最近但仍 active
* 一旦 primary market 变更：

    * 更新订阅 token 集合（支持热更新或重连重订阅）
    * 产生 `SubscriptionChanged` / `MarketLifecycle` 标准事件通知下游

> MVP 可不实现复杂 topic 聚类，也可以先按“热门 TopK”集合滚动更新订阅；但必须处理 market 关闭导致 token 无效的情况。

### 1.4 实时监控（Realtime Monitor）

* 使用 Polymarket CLOB WebSocket market channel 订阅多个 token_ids（YES/NO）
* 解析实时消息，至少需要覆盖：

    * 成交类（trade/last_trade）
    * 盘口类（best bid/ask, book depth）
      -（可选）市场状态类事件（new_market / market_resolved 等，如果可获得）
* 监控信号（可配置阈值）：

    1. **Big Trade**：单笔成交额 ≥ `big_trade_usd`
    2. **Volume Spike**：滚动 1 分钟累计成交额 ≥ `big_volume_1m_usd`
       3)（可选）**Big Wall**：盘口前 N 档挂单量 ≥ `big_wall_size`
* 计算规则：

    * 成交额（usd notional） = price * size（或按 feed 字段直接提供的 notional）
    * 维护每个 token 的 1min 滑动窗口（deque）
* 防刷屏：

    * 同一个 (topic/market/token/signal_type) 在 `cooldown_sec` 内最多报警一次

### 1.5 稳定性与容错

* WebSocket 断线自动重连
* 重连后自动重新订阅当前 token 集合
* Gamma 目录接口轮询频率可控（`refresh_interval_sec`），避免限流
* 记录 health/metrics：重连次数、刷新耗时、订阅 token 数量、丢消息/异常计数

---

## 2) 输出设计（最关键：下游可插拔 + 可多播）

### 2.1 组件对外只暴露一个输出 Port

* `EventSinkPort.publish(event)`
  组件内部只调用这个 port，不知道下游是谁。

### 2.2 下游支持多播（Fan-out）

* 提供 `MultiplexEventSink`（聚合 sink adapter）：

    * 支持把同一事件发给多个 sinks
    * 支持按事件类型/标签路由到不同 sinks
    * 支持 transform（字段裁剪：compact/full/raw）

### 2.3 标准化事件契约（DomainEvent）

组件输出必须是稳定结构，不能直接把 Polymarket 原始 JSON 当输出（可选附带 raw 字段给审计）。

所有事件必须包含最少字段：

* `event_id`（全局唯一，用于幂等去重）
* `ts_ms`
* `source = "polymarket"`
* `category`（finance/geopolitics）
* `event_type`（枚举）
* `market_id`
* `token_id`
* `side`（YES/NO，如果可映射）
* `title/question`（可选但推荐）
* `metrics`（价格、成交量、notional、vol_1m 等）
  -（可选）`topic_key`（用于 rolling 连续性）

事件类型至少包括：

* `CandidateSelected`（每次刷新输出 TopK 结果）
* `SubscriptionChanged`（订阅 token 集合变化）
* `TradeSignal`（大单/放量触发）
* `BookSignal`（盘口墙/流动性异常）
* `MarketLifecycle`（market closed/resolved/new）
* `HealthEvent`（断线、重连、限流、异常）

### 2.4 交付语义（明确策略）

默认推荐：

* **At-least-once**：可能重复投递，下游用 `event_id` 去重
* 多播失败策略可配置：

    * `best_effort`：某个 sink 失败不影响其他 sink
    * `required_sinks`：指定关键 sink（如 Kafka）必须成功，否则进入重试/DLQ

---

## 3) 配置要求（必须可配置）

提供统一配置对象（YAML/JSON + schema 校验）：

### 3.1 扫描与筛选

* `categories = ["finance","geopolitics"]`
* `refresh_interval_sec`
* `top_k_per_category`
* `hot_sort = ["liquidity","volume_24h"]`
* `filters`（如最小流动性门槛、关键词过滤等，可选）

### 3.2 信号阈值

* `big_trade_usd`
* `big_volume_1m_usd`
* `big_wall_size`（可选）
* `cooldown_sec`

### 3.3 Rolling 策略

* `rolling_enabled`
* `primary_selection_priority = ["liquidity","volume_24h","end_ts"]`
* `max_markets_per_topic`（可选）

### 3.4 输出路由

* `sinks` 列表（redis/kafka/http/stdout…）
* `routes`（event_type -> sinks）
* `transform`（compact/full/raw）
* `required_sinks`（可选）

---

## 4) 架构与工程约束（六边形）

* PolymarketComponent 内部应分层：

    * domain（模型、事件、策略）
    * application（调度：refresh/subscribe/detect/emit）
    * ports（catalog/feed/sink/store/clock）
    * adapters（polymarket gamma、clob ws、redis/kafka/webhook…）
* Composition Root（main）负责把 adapters 注入 ports（依赖倒置）
* 核心逻辑不得 import 具体 adapter（比如 requests/websockets/redis/kafka）

---

## 5) MVP 交付清单

1. Gamma：动态解析 finance/geopolitics tag_id，拉取 active markets，TopK
2. 提取 token_ids，WebSocket 订阅
3. BigTrade + 1min VolumeSpike 检测 + cooldown
4. Rolling：发现 market closed/resolved 时自动从刷新结果更新订阅集合（允许简单实现：订阅集合完全重建并重连）
5. 输出 DomainEvent
6. Fan-out 输出：至少支持 `StdoutSink + RedisPubSubSink`，并可配置同时发送

---

## 6) 非目标（明确不做）

* 不做主观预测（不输出“会不会开战”）
* 不做下单交易（只监控）
* 不做识别下单者身份（拿不到）
* 不做全站全盘订阅（只盯两板块热门集合）

---
