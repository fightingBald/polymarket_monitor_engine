# adapters（适配器层）🎛️

## 设计思路 🧠

把“外部世界”都塞这里：HTTP、WebSocket、Redis、Discord。核心逻辑只认接口，不碰具体实现。

## 好处 ✨

- 外部依赖换了，改适配器就行。
- 测试简单：用 fake 适配器就能跑。
- 依赖方向清晰，不乱耦合。

## 这里都有啥 🧩

- `gamma_http.py`：Gamma HTTP 拉盘。
- `clob_ws.py`：CLOB WS 订阅。
- `redis_sink.py`：Redis Pub/Sub 输出。
- `stdout_sink.py`：stdout 输出。
- `discord_sink.py`：Discord Webhook（Embed）。
- `multiplex_sink.py`：多 sink 并行 fan‑out。

## 怎么用 🚀

- 新下游：实现 `EventSinkPort`，在 `__main__.py` 组装进 `MultiplexEventSink`。
- 新数据源：实现 `MarketCatalogPort` / `MarketFeedPort`。
- 路由改法：改 `config/config.yaml` 的 `sinks.routes`。
