# util（通用工具）

## 设计思路

把跨模块的通用能力集中在这里，避免到处复制粘贴。

## 好处

- 统一日志与 HTTP 客户端设置。
- 复用 ID、时钟等小工具，减少重复。

## 主要工具

- `logging_setup.py`：结构化日志配置。
- `httpx_setup.py`：屏蔽 httpx 低价值日志。
- `ids.py`：事件 ID 生成。
- `clock.py`：系统时钟封装。

## 怎么用

- 启动时调用 `configure_logging`。
- 需要安静的 HTTP 日志就调用 `silence_httpx_logs`。
