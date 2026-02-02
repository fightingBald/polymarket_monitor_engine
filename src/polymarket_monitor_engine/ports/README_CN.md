# ports（端口层）🔌

## 设计思路 🧠

端口层定义“能力接口”，让上层只依赖接口，不依赖具体实现。

## 好处 ✨

- 依赖倒置：应用层不绑死某个服务。
- 易测试：用 fake/mock 实现端口就能测。

## 主要接口 🧩

- `catalog.py`：市场目录拉取接口。
- `feed.py`：行情/交易流接口。
- `sink.py`：事件输出接口。
- `clock.py`：时间接口（可测）。

## 怎么用 🚀

- 新数据源：实现 `MarketCatalogPort` / `MarketFeedPort`。
- 新下游：实现 `EventSinkPort`。
- 新时钟：实现 `ClockPort`。
