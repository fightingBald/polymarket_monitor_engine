# adapters（适配器层）

## 设计思路

把所有“外部世界”的东西都放这层：HTTP、WebSocket、Redis、Discord。核心逻辑只认接口，不认具体实现。

## 好处

- 外部依赖变了，只改适配器，不动核心逻辑。
- 方便测试：可以用假的 adapter 替换真服务。
- 依赖方向清晰，避免业务逻辑污染 I/O 细节。

## 都有啥

- `gamma_http.py`：Gamma HTTP 目录/市场拉取。
- `clob_ws.py`：CLOB WebSocket 订阅与消息解码。
- `redis_sink.py`：Redis Pub/Sub 下游输出。
- `stdout_sink.py`：标准输出下游输出。
- `discord_sink.py`：Discord Webhook Embed 通知。
- `multiplex_sink.py`：多 sink 并行 fan-out（带路由）。

## 怎么用

- 新加下游：实现 `EventSinkPort`，在 `__main__.py` 组装进 `MultiplexEventSink`。
- 新数据源：实现 `MarketCatalogPort` / `MarketFeedPort`，替换注入即可。
- 调整路由：改 `config/config.yaml` 的 `sinks.routes`。
