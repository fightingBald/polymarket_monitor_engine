# domain（领域层）

## 设计思路

领域层只放“稳定的业务概念”：市场、成交、盘口、事件。这里不关心任何 I/O。

## 好处

- 领域模型稳定，外部系统变化不影响核心。
- 事件结构统一，方便下游消费和测试。

## 主要内容

- `models.py`：`Market` / `TradeTick` / `BookSnapshot` 等模型。
- `events.py`：`DomainEvent` 和 `EventType`。

## 怎么用

- 新事件类型：在 `EventType` 里加枚举，并在应用层生成。
- 新字段：先改模型，再更新解析与输出。
