# domain（领域层）🧠

## 设计思路 🧬

领域层只放“稳定的业务概念”：市场、成交、盘口、事件。这里不关心任何 I/O。

## 好处 ✨

- 模型稳定，外部变化不影响核心。
- 事件结构统一，下游很好接。

## 主要内容 🧩

- `models.py`：`Market` / `TradeTick` / `BookSnapshot` 等模型。
- `events.py`：`DomainEvent` 和 `EventType`。
- `schemas/`：事件 payload 的 typed schema（Pydantic）。

## 怎么用 🚀

- 新事件类型：改 `EventType`，然后应用层产出即可。
- 新字段：先改模型，再更新解析与输出。
