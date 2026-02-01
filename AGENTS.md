# AI CODING ASSISTANT GUIDELINES
---
当我提出需求时， 如果不是一个好主意或者有更优雅的解决方案 ，请说明

## 0) GLOBAL GUARANTEES（输出契约）

**AI 必须遵守的硬约束**

* **MUST 通过**：`build` 与 `test`（语言对应，如 `go build ./... && go test ./...`）。
* 最后完成任务时输出自己解决这个问题的思维链
* 做好logging
* 每次更新扫描更新readme
* **MUST NOT**：
    * (除非明确要求重构) 否则禁止引入无关格式化改动或大面积重排；
    * 修改代码生成产物；
    * 手写拼接 SQL 字符串（必须使用参数化/Builder/ORM）。
* Layout Hygiene（目录卫生）：重构或编码引入/移动/删除目录与模块，必须保持分层职责清晰（单向依赖；并在**同一 PR** 同步更新「§2 LAYOUT & PROJECT OVERRIDES」中的布局说明与目录树；同时更新 README 的目录树

**最低可验证性**

| 变更类型 | 最小验收动作               |
| ---- | -------------------- |
| API  | 发真实 HTTP 请求验证状态码与响应体 |
| 数据   | 执行查询直接验证行数/关键字段值     |
| 逻辑   | 跑到具体业务场景并断言输出        |
| 配置   | 重启/热加载并确认生效日志        |

### ROLE BOUNDARIES（AI 助手硬约束）

| 项     | 必须               | 禁止                  |
| ----- | ---------------- | ------------------- |
| 语言/版本 | 遵循项目声明版本  | 过时 API       |
| 输出    | 统一 diff/完整文件     | 片段化、不可编译拼贴          |
| 变更范围  | 最小必要改动           | 大范围样式化改动            |
| 错误处理  | 语义化 error + 分级日志 | `panic`/吞错/裸打印      |
| 并发    | ctx 取消/超时、无数据竞争  | 忽视 ctx、无界 goroutine |
| 安全    | 强校验输入、参数化查询      | 信任外部输入、拼接 SQL       |
| 文档    | 关键导出符号注释         | 把约定只写在 PR           |

---

## 1) CORE PHILOSOPHY & REALITY CHECK（核心哲学）

* “Should work” ≠ “does work”。未测试的代码只是猜测。
* 我们在解决问题，而不是堆代码。
* 最小改动，最大一致性，优先沿用现有模式。

**30 秒自检（全部回答 YES）**

* 我构建/运行了代码吗？
* 我触发了**恰好**被改动的功能路径吗？
* 我亲眼看到期望结果（含 HTTP 状态/响应体）了吗？
* 我检查了日志与错误分支了吗？

**禁用措辞**：

> “This should work now”“Try it now”“The logic is correct so…”“I’ve fixed it”（二次以后）

---

## 2) LAYOUT & PROJECT OVERRIDES（布局与项目覆写）

> 本节是**唯一**记录仓库目录结构、分层约定与项目差异化覆写的位置。任何引入/移动/删除目录或模块的变更，必须在**同一 PR** 更新本节内容与目录树说明，保持分层职责清晰、文档同步且可审计。

### 2.1 通用不变项

* **分层清晰与单向依赖**：遵循自上而下的层次结构，层间依赖单向流动；避免跨层或横向耦合。层级命名与数量由项目自定，但职责边界必须清晰、可审计、可解释。
* 契约集中在 `api/`，生成物在 `api/gen`（或等价），**禁止手改**。
* 单元测试就近，集成/端到端测试在 `test/`。
* 配置与脚本集中于 `scripts/` 与 `Makefile`；部署工件统一在 `deploy/`（或等价）。




---

## 3) BUILD & DEV COMMANDS（统一命令面）

> 以 make 为统一门面，内层调用语言自带工具。

| Command                 | Description                             |
| ----------------------- | --------------------------------------- |
| `make build`            | 编译/打包可执行或产物。                            |
| `make run`              | 本地启动服务做冒烟验证。                            |
| `make test`             | 运行单测与快速集成测试。                            |
| `make test-integration` | 以容器/沙箱跑集成套件（Testcontainers/Compose）。    |
| `make gen`              | 从 `api/` 重生代码绑定（OpenAPI/Proto/GraphQL）。 |
| `make migrate-up`       | 执行数据库迁移；`make migrate-down` 回滚。         |
| `make lint`             | 强制静态检查与风格校验；与 CI 保持一致。                  |
| `make format`           | 自动格式化所有源代码文件；与 CI 行为保持一致。               |

> 要求：命令在本地与 CI 行为一致；所有目标可幂等重试。

---

## 4) DEPENDENCIES & VERSIONS（依赖与版本）

| Policy    | Details                      |
| --------- | ---------------------------- |
| Pinning   | 锁到公开 tag；升级通过显式命令并整理锁文件。     |
| Review    | PR 审查传递依赖差异；谨慎大版本升级，附回归计划。   |
| Security  | 优先修复网络/序列化/SQL/模板/认证相关 CVE。  |
| Artifacts | 锁文件随代码提交；默认不 vendor，除非环境强约束。 |
| Adoption  | 鼓励使用成熟、优雅的解决方案，合理引入依赖提升表达力与效率。 |

---

## 5) API SCHEMA & CODEGEN（契约即真相）

* **单一事实源**：HTTP 用 OpenAPI，gRPC 用 Protobuf，GraphQL 用 SDL。集中于 `api/`。
* **代码生成**：固定版本与配置，生成到 `api/gen`，**禁止手改**。
* **严格路由**：开启“严格服务器/严格校验”（如 oapi-codegen `-strict-server`）。
* **变更流程**：改 Schema → 重生绑定 → 补测试 → 提交 `api` 与 `api/gen`。

---

## 6) CODING & NAMING（通用编码规范）

| Rule | Details                                                                     |
| ---- | --------------------------------------------------------------------------- |
| 格式化  | 强制格式化与静态检查（fmt/vet/linter/ruff/prettier 等）。                                 |
| 命名   | 语义化、可读，避免 `data/tmp/info` 等空词。错误用 `ErrXxx`。                                 |
| 结构   | 小函数小类型，单一职责；参数过多用配置 struct/Options。                                         |
| 错误   | 只包装一次，保留根因与操作前缀；公共层统一错误映射。                                                  |
| 上下文  | I/O 必带上下文/超时；禁止将上下文存入结构体。                                                   |
| 日志   | 结构化字段，分级打印，严禁 `print` 系调试遗留。                                                |
| SQL  | 必须参数化/Builder/ORM；禁止字符串拼接；必写事务与隔离意图。                                        |
| 语言特性 | 善用语言的最新特性（如 Go 泛型、Java 结构化并发、Python 3.12 模式匹配、TS 装饰器等），在保证可读性的前提下提升安全性与表达力。 |
| 高级库 | 若能显著减少代码行数并提升可读性/可维护性，应优先采用成熟的高级库（如 pandas、numpy 等），同时做好依赖说明。 |

---

## 7) TESTING（强制风格）

* **表驱动 + 子测试**：统一可读命名，覆盖成功/边界/错误。
* **断言库**：按语言统一（Go: `testify/require`；Java: AssertJ；Python: `pytest` 内置等）。
* **外部依赖**：优先 Testcontainers/Embedded 可重复环境；禁用对生产资源的直连。
* **稳定性**：禁用 `sleep` 伪同步；可注入时钟与重试策略。

---

## 8) CONCURRENCY / RESOURCES / SECURITY / OBSERVABILITY

* **并发**：生命周期可控（errgroup/协程池/线程池），可取消可超时，避免共享可变状态。
* **资源**：文件/连接/游标必须关闭；限制缓存与队列大小，防止 OOM。
* **安全**：输入校验与逃逸；Secrets 不入库，运行时注入；遵循最小权限。
* **可观测性**：

    * 指标：QPS、P95/P99、error_rate、依赖外呼延迟；
    * 追踪：传播 W3C traceparent 或等价；
    * 日志：关键路径与失败点留证据，避免重复打印同一 error chain。

---


---

## 10) REFACTOR POLICY（重构策略）

**Allowed**

* `EXTRACT_FUNC`、`MOVE_FILE`、`RENAME_SYMBOL`、`SPLIT_FILE`（> ~300 行或关注点混杂时触发）。
* `UPDATE_LAYOUT_DOC`：结构性变更必须同步更新 §2 的布局约定与目录树；PR 需附迁移说明。

**Prohibited**

* 修改 `api/gen` 生成物；
* 跨层互相引用导致循环；
* 在 handler/adapter 内塞业务决策。

**触发信号**

* handler 出现业务决策或多步编排；
* domain 与 infra 互相引用；
* 文件超大且混层。

---

## 10.A) HOW TO REFACTOR（重构操作指引）
* **设计原则**：高内聚，低耦合 ，善用接口， 面向可扩展
* **对齐动机**：使目录和代码更加模块化；必要时将单一巨型文件拆解成职责明确的多个模块，或新建文件夹归类，保持文件目录结构职责清晰。
* **设计快照**：先产出最小设计与依赖图，识别跨层影响；必要时约定迁移阶段，确保单向依赖不被破坏。
* **渐进式递交**：拆分为可验证的小步提交，保持主干随时可 build/test；优先 `MOVE`→`ADAPT`→`CLEAN` 顺序减少 diff。
* **验证闭环**：每步完成后跑 `make build && make test`，并针对受影响路径补/调测试，确保行为未变。
* **文档同步**：涉及目录/职责调整时同步更新 §2 与 README 目录树，输出迁移说明与回滚方案。

---

## 11) COMMIT / PR / CI GATES（提交流水线）

| Gate | 要求                                              |
| ---- | ----------------------------------------------- |
| 构建   | `make build` 通过                                 |
| 格式   | 语言对应的 fmt/vet/lint 全过                           |
| 安全   | 漏洞扫描通过（如 `govulncheck`/`npm audit`/`pip-audit`） |
| 测试   | `make test` 与 `make test-integration` 通过        |
| 生成   | 改契约时必须重生并提交 `api/gen`                           |
| 文档   | 对外行为变化需更新本文或 README                             |

**Conventional Commits**：`type(scope): short summary`，描述里写明背景/改动/风险/验证/回滚方案。

**PR Checklist**

*

---

# LANGUAGE STYLE PACKS（语言风格包）

## A) Go（1.24.x）

* **Formatting/Lint**：`go fmt ./...`、`go vet ./...`、`staticcheck ./...`。
* **命名**：mixedCaps；接口按能力命名，不加 `I` 前缀；导出最小化。
* **上下文**：所有外部 I/O 函数首参 `context.Context`，禁止存入结构体。
* **错误**：包级 sentinel；`fmt.Errorf("op: %w", err)` 包装；HTTP 层统一映射。
* **接收者**：稳定单字母，如 `(s *Server)`；值/指针接收者遵循可变性与逃逸分析。
* **并发**：`errgroup`/`context` 控制生命周期；避免无界缓冲；`select` 监听 `ctx.Done()`。
* **依赖**：路由 `github.com/go-chi/chi/v5`；PG 驱动 `github.com/jackc/pgx/v5`；SQL Builder `github.com/Masterminds/squirrel`；OpenAPI 校验 `github.com/getkin/kin-openapi`；Testcontainers。
* **API & 生成**：oapi-codegen 开启 `-strict-server`；生成到 `api/gen`；禁止手改。
* **测试风格（强制）**：

    * 表驱动：`cases := []struct{ name string; in ...; exp ... }{...}`
    * 子测试：`t.Run(c.name, func(t *testing.T) { c := c; ... })`
    * 断言：`github.com/stretchr/testify/require`
    * 集成优先 Testcontainers，HTTP/PG 走真连与隔离资源。

**常见陷阱**

* 在 handler 里起后台 goroutine 且不关联 `ctx`；
* 拼接 SQL；
* 把可选参数摊平为长函数签名，优先 Options 模式；
* 以 `sleep` 凑同步；请用通道/条件或可注入时钟。

---

## B) Java（JDK 21）

* **Build**：Gradle 或 Maven，启用 `Werror` 类似的严格模式。
* **格式**：Google Java Format 或 Spotless；Checkstyle + Error Prone。
* **命名/结构**：包小写分层清晰；类职责单一；记录类（record）优先装 DTO。
* **错误**：受检异常仅在边界；业务异常携带语义码；统一 ControllerAdvice 映射。
* **并发**：虚拟线程/结构化并发优先；CompletableFuture 限定在边界层。
* **测试**：JUnit 5 + AssertJ + Testcontainers；分层测试夹具；`@Testcontainers`/`@Container` 管理生命周期。
* **API**：OpenAPI→`springdoc-openapi` 或 Micronaut；生成客户端/服务端 stub。

---

## C) Python（3.12）

* **格式**：`black` + `ruff` + `isort`；类型：`mypy --strict`（合理放宽）。
* **结构**：包内 `__init__.py` 明确导出；避免巨型模块；`dataclasses`/`pydantic` 管理 DTO。
* **异步**：`asyncio` + `anyio`；超时/取消必须；HTTP 用 `httpx`；并发限速与重试回退。
* **测试**：`pytest` + `pytest-asyncio`；`hypothesis` 可选；Testcontainers for DB/MQ。
* **配置**：`pydantic-settings`；Secrets 走环境/密管；禁用 `.env` 入库。

---

## D) TypeScript / Node（TS 5.x / Node 20）

* **格式**：ESLint（strict）+ Prettier；`tsconfig` 开启 `strict: true`。
* **运行**：`pnpm` 优先；模块路径别名经 `tsconfig-paths`；生产构建 `tsc` 输出 ESM/CJS 统一约定。
* **API**：Fastify/Express；输入用 `zod` 或 `valibot` 校验；OpenAPI 生成路由绑定。
* **测试**：Vitest/Jest；Supertest for HTTP；Testcontainers。
* **安全**：Helmet/CSP；参数化查询；序列化白名单；避免原型链污染。

---

## E) SQL & DATABASE

* **迁移**：严格顺序迁移；禁用手改历史脚本；DDL 与 DML 分离；向前兼容与可回滚脚本成对。
* **查询**：参数化或 Builder；必须说明隔离级别、锁策略与索引使用意图。
* **索引**：命名规范（`tbl_col_idx`）；避免重复索引；压测前后对比计划与延迟。
* **测试**：Testcontainers 启库；基线数据与清理；时间字段截断或固定化比较。

---

## F) Frontend（Vue/Nuxt 或 React）

* **状态**：最小全局状态；优先组合式/自定义 hooks；副作用集中管理。
* **路由与数据**：SWR/Query 缓存；请求层统一拦截器与错误边界。
* **类型**：严格 TS；组件 props/emit 明确；API 类型来自单一契约生成。
* **测试**：Vitest + Testing Library；端到端用 Playwright。

---

# CHECKLISTS

* **开发自检**

    * 结构遵循分层与单向依赖
    * 新增类型/字段向前兼容
    * 错误只包装一次并含语义前缀
    * 成功/失败/边界最小测试覆盖
    * 无敏感信息泄漏
    * 无循环依赖与隐藏耦合
    * 未以 `sleep` 伪同步
    * 本地编译/运行/日志与错误均验证
