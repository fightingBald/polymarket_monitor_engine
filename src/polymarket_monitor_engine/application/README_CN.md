# application（应用层）🧠

## 设计思路 💡

应用层负责“把事情串起来”：市场发现、订阅管理、信号检测、事件输出。这里只做编排，不直连外部系统。

## 好处 ✨

- 流程清晰：谁干啥一眼明白。
- 扩展方便：加新规则不动适配器。
- 易测试：端口替身一换就能测。

## 主要模块 🧩

- `component.py`：主流程编排。
- `discovery.py`：市场发现/筛选。
- `monitor.py`：监控编排（把信号引擎串起来）。
- `signals/`：信号识别策略与状态（大单/放量/重大变动）。
- `orderbook.py`：盘口缓存与订阅维护。
- `types.py`：应用层数据结构。

## 怎么用 🚀

- 改“重大变动”规则：看 `signals/detector.py` 的 `SignalEngine`。
- 改筛选逻辑：看 `discovery.py`。
- 改运行流程：看 `component.py`。
