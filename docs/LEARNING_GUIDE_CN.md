# DocMind-Agent 源码学习手册：从会运行命令到会设计、调试和面试讲解

> **定位**：给“已经运行过 M0–M9 验收脚本，但几乎没有深入理解架构和运行逻辑”的学习者。  
> **内容依据**：直接阅读本仓库 2026-10-15 版本的 FastAPI / LangGraph / RAG / MCP / Memory / HITL / Eval / Trace 源码及已记录的本机验收。  
> **目标**：独立画架构图、逐函数追踪 4 类请求、解释关键技术取舍、定位故障，并在 Agent/RAG 开发面试中用自己的语言清晰回答。

推荐先浏览 [中文 README](../README_CN.md)。学习时不需要重复运行耗时的 BGE/Qwen 完整测试：大部分章节可静态阅读源码及单元测试。

**真实性说明**：M0–M9 核心功能已通过合成任务的本地验收；Grafana 看板未独立验收，最新修复版 Docker 镜像因 Docker Hub 代理问题未完成干净重建，M9 LIVE 是从现有容器中的更新源码通过的。**这是求职学习用工程原型，不是生产法律服务。**

## 目录

- [01｜学习路线与达标标准](#ch01)
- [02｜整体系统架构和真实请求流](#ch02)
- [03｜源码地图与基础知识](#ch03)
- [04｜FastAPI、运行环境和 API](#ch04)
- [05｜M1 文档解析、分块与索引](#ch05)
- [06｜M2 混合 RAG、重排与引用](#ch06)
- [07｜M3 LangGraph Agent 的运行机制](#ch07)
- [08｜Pydantic 工具系统与 MCP](#ch08)
- [09｜M4 工作、会话、长期与检查点记忆](#ch09)
- [10｜M6 可靠性、HITL 和幂等写入](#ch10)
- [11｜M7 检索、Agent、系统评测](#ch11)
- [12｜M8 Trace、Metrics 和性能诊断](#ch12)
- [13｜M9 Demo 与真实验收结果](#ch13)
- [14｜四条逐步代码跟踪任务](#ch14)
- [15｜分层动手练习和学习任务](#ch15)
- [16｜Agent/RAG 高频面试问题与答案](#ch16)
- [17｜常见问题与排障手册](#ch17)
- [18｜综合自测题和参考答案](#ch18)
- [19｜术语速查表](#ch19)
- [20｜真实局限和优化思路](#ch20)
- [21｜源码与证据索引](#ch21)

**阅读约定**：标记“已实现”表示源代码存在；“已验收”表示本地有对应结果；“原理”介绍通用知识，不代表所有方案均已实现。所有示例 UUID 和合同数据仅为教学示意。

<a id="ch01"></a>
## 01｜两周学习路线：每天读什么，产出什么

| 天 | 阅读主题 | 源码 | 应能回答 |
|---|---|---|---|
| D1 | 三层架构与组件分工 | `app/main.py`、`compose.yaml` | PostgreSQL、Redis、Qdrant 分别为什么存在？ |
| D2 | HTTP、JSON、Pydantic、异步 | `app/api/chat.py` | 一条请求如何进入 Agent？ |
| D3 | 文档解析和 Chunk | `app/rag/parser.py`、`chunker.py` | 如何保留准确页码、Offset？ |
| D4 | Embedding、Qdrant | `embedder.py`、`storage/qdrant.py` | 文本、向量与来源 Metadata 在哪里？ |
| D5 | Dense/BM25/RRF | `retriever.py`、`sparse.py`、`fusion.py` | 为什么两路召回并融合排名？ |
| D6 | Reranker、Qwen、Citation | `pipeline.py`、`citation.py` | `[S1]` 谁分配、谁验证？ |
| D7 | LangGraph State、节点循环 | `agent/state.py`、`graph.py`、`nodes.py` | Agent 和单条 RAG 管道有什么区别？ |
| D8 | Router、Tools、有限规划 | `agent/router.py`、`tools/registry.py` | 模型是否可以自由决定工具？ |
| D9 | MCP 标准调用 | `mcp_client/adapter.py`、`mcp_server/server.py` | stdio MCP 与直接函数调用有什么不同？ |
| D10 | Redis、长期偏好、Checkpoint | `memory/` | Memory 和 Checkpoint 不能混为一谈的原因？ |
| D11 | Retry、超时、HITL | `reliability.py`、`approvals/` | 为什么写入不能随意重试？ |
| D12 | Metrics、Trace、事故定位 | `observability/` | HTTP 200 为什么仍可能业务失败？ |
| D13 | 评测及 Demo | `eval/`、`scripts/check_m9.py` | 100% Task Success 说明了什么？ |
| D14 | 完整复述与技术面试 | 本手册 14–20 章 | 能否独立讲 5–10 分钟项目？ |

建议每天花 20 分钟整理：**输入 → 执行函数 → 输出 → 异常 → 设计理由**。不用从头读完所有文件才算开始。

**能力等级**：

- L1：知道所有组件名称与分工，不只背技术栈。
- L2：能从 `POST /v1/chat` 找到 LangGraph 节点、工具执行和返回值。
- L3：能解释 RRF、Chunk 来源、规则路由、Memory 和 HITL 的取舍。
- L4：能独立查询 Trace，知道什么时候应该改代码、配置或网络。
- L5：能说清实际不足，而不是把 7 个合成样本说成真实法律业务准确率。

<a id="ch02"></a>
## 02｜整体架构与请求执行：先建立心智模型

### 2.1 用户看到的功能，背后有哪些独立模块？

场景 A：“这份合同付款期限是多少？”

~~~text
文件上传 -> parse -> chunk -> embedding -> Qdrant
                                |
HTTP /v1/chat -> 读取 Redis 会话 -> LangGraph
                                   |
                          route/decide（选择工具）
                                   |
                            search_documents
                                   |
                Qdrant Dense + 字符 BM25 -> RRF
                                   |
                          CPU BGE Cross-Encoder
                                   |
                             证据 [S1][S2]
                                   |
                           Qwen/vLLM 生成答案
                                   |
                         Python 校验引用编号
                                   |
                        synthesize -> HTTP 返回
                                   |
                     PG Trace / Redis 新增会话轮次
~~~

场景 B：“通过 MCP 查询文档信息并查找违约责任条款”：走真实 stdio MCP Client/Server、执行两个**只读**工具后聚合结果，不一定调用 Qwen。

场景 C：“保存审核备注：请复核付款期限”：进入审核审批通道，创建 pending 行、LangGraph `interrupt()`、人工批准后 `Command(resume=...)`，最后 PG 事务写入，拒绝则不写。

**设计总思想**：LLM 做有限语义理解或证据驱动生成；确定性 Python 代码负责权限边界、工具类型、状态、引用 ID、超时和数据库事务。

### 2.2 按功能区分三层

- **数据面**：解析、分块、Embedding、检索、重排、证据、生成；解决“依据是什么”。
- **控制面**：LangGraph State、工具路由、Planner、Session/Checkpoint、审批；解决“下一步执行什么、能不能执行”。
- **运维面**：Trace、Prometheus、CI、Docker；解决“哪里慢、为什么失败、能不能复现”。

不要把“有 LangGraph”理解为“模型会自己思考并自由调工具”。本项目优先使用规则，只有符合条件的复杂任务才尝试受约束的模型排序。

### 2.3 四种主要依赖的职责

| 组件 | 源码中的实际作用 | 记忆/事务/检索区别 |
|---|---|---|
| PostgreSQL | `documents`、`memories`、`approvals`、`review_notes`、`agent_traces`，另有 LangGraph 官方 Checkpointer 表 | 结构化持久事实、审批锁、幂等与恢复；非向量语义引擎 |
| Redis | 当前会话最近 6 轮、文档上下文、TTL、互斥锁 | 短期、低延迟、会过期；不是永久对话档案 |
| Qdrant | `documents_v1` 中的 Embedding/Chunk 来源 Payload、`memories_v1` 偏好向量 | 相似度检索和范围过滤；不是审批事实数据库 |
| Qwen/vLLM | 经 OpenAI 兼容 HTTP 生成回答；部分多工具任务排序 | 模型不是数据库事务、来源 ID 或权限系统 |

特别注意：冻结需求文档提过理想化的 PostgreSQL session/message 存储，但当前近期 Session 代码实际在 Redis；不要把设计图中的概念表说成已经实现的 PG 业务表。

### 2.4 一条真实问答的八步调用

1. `app/api/chat.py::chat` 接收并验证 JSON，得到/创建 `session_id`。
2. 读取 Redis 之前的会话、确定 `document_id`，有需要则恢复短追问上下文。
3. `graph.ainvoke(_initial_state(...), config=thread_config(session))`。
4. `route_node` 调用 `plan_tools`，简单付款期限问题按规则选择 `search_documents`。
5. `decide_node` → `call_tool_node` → `execute_read_only_tool` → `invoke_tool`。
6. RAG 内部找到证据并调用 Qwen；`synthesize_node` 统一来源编号与状态。
7. `chat` 把回答与有限近期上下文写入 Redis。
8. `observed_endpoint` 结束 Trace，写入 PostgreSQL，HTTP 响应包含 `answer`、`sources`、`status` 等。

**分清三个事实**：LLM 输出 `answer`；系统维护 `sources` 和来源标识；`status` 表示业务流程结果。来源 ID 合法不等于每句话都语义正确。

<a id="ch03"></a>
## 03｜源码地图与 Python 工程基础

### 3.1 仓库地图

~~~text
app/main.py                应用启动、PG/Redis Checkpointer 初始化
app/api/documents.py       文件上传/索引
app/api/chat.py            Agent、Session、长期偏好、写入审批入口
app/api/approvals.py       人工决策后恢复图
app/agent/state.py         AgentState 字段类型
app/agent/graph.py         route/decide/call_tool/synthesize 图
app/agent/router.py        规则路由与受限模型工具排序
app/agent/nodes.py         节点代码/工具调用/引用合并
app/agent/reliability.py   超时/失败分类/重试/Fallback
app/rag/                   解析、分块、检索、重排、生成与来源引用
app/tools/                 参数 Schema、业务工具与 MCP 适配
app/mcp_client/adapter.py  MCP ClientSession + stdio
mcp_server/server.py       官方 FastMCP server
mcp_server/document_tools.py  服务端读数据、查条款和检索
app/memory/                Redis Session / 长期偏好 / Checkpoint
app/approvals/             审批策略与 PG 受保护写入
app/observability/         请求/节点 Trace、Metrics、持久化
migrations/                PG 表结构
eval/                      M7a/M7b/M7c 指标与合成 Fixture
tests/unit/                大量不依赖 Docker 的模块单测
scripts/                   Windows BAT 与 Python 本机验收脚本
~~~

**阅读顺序**：先从 `app/api/chat.py` 找一次请求的调用点，再进入 `agent/graph.py`、`agent/nodes.py`，之后理解所选工具。不要无目的地从每个目录的第一个文件开始读。

### 3.2 六项必备 Python / Web 知识

1. **HTTP / JSON**：`POST` 接收参数，`GET` 查询状态。HTTP 200 是请求已处理，不等于 Agent `status=answered`。
2. **Pydantic**：`ChatRequest(BaseModel)` 和各工具 `Args` 校验 UUID、字符串长度和禁止额外字段 `extra="forbid"`，避免工具得到模型自由编造的参数。
3. **`async def` / `await`**：适合 DB/HTTP 等 I/O 等待，能让事件循环调度其他请求，**不自动加速 CPU**。
4. **`asyncio.to_thread`**：把 Embedding/ONNX Rerank 的阻塞代码挪到工作线程。请记住：取消协程等待并不一定能终止线程内 C++ 推理。
5. **`TypedDict` / `dataclass`**：前者约定 LangGraph State 字段，后者用于传递稳定结构（如 `RetrievalHit`、`DocumentChunk`）。
6. **依赖注入/生命周期**：FastAPI `lifespan` 统一创建连接池、Redis Client、LangGraph Checkpointer，再把资源存到 `app.state` 供处理请求使用。

### 3.3 用四个问题读一个函数

打开某个函数时始终记录：

- **输入**：参数、类型、默认值、前置校验。
- **输出**：成功返回的字段、失败返回的状态。
- **副作用**：是单纯计算，还是改 PG、Redis、Qdrant？
- **边界**：什么情况会超时、抛异常、拒绝执行或需要审批？

示例：`chunk_document` 输入文本块和 `document_id`，输出稳定 Chunk List，**不访问数据库**。而 `store_document_vectors` 的副作用是删除旧向量并写入 Qdrant Points。

<a id="ch04"></a>
## 04｜FastAPI、环境与 HTTP API

### 4.1 容器端口和主机端口

| 服务 | Windows 主机地址 | 容器间地址 |
|---|---|---|
| DocMind FastAPI | `127.0.0.1:8090` | `api:8000` |
| PostgreSQL | `5432` | `postgres:5432` |
| Redis | `6379` | `redis:6379` |
| Qdrant REST / gRPC | `6333` / `6334` | `qdrant:6333` / `qdrant:6334` |
| 独立 Qwen/vLLM | Windows 8000 | API 用 `host.docker.internal:8000/v1` |
| 可选 Prometheus/Grafana | 9091 / 3091 | 需要 overlay，独立验收未通过 |

在 API 容器内 `127.0.0.1:8000` 指当前 Uvicorn，不是宿主机 Qwen；在 Windows 用 `127.0.0.1:8090` 访问 API。

### 4.2 服务启动会做什么？

源码 `app/main.py::lifespan`：

~~~text
init_documents_schema()
 -> init_memory_schema()
 -> init_approval_schema()
 -> init_trace_schema()
 -> asyncpg.create_pool()
 -> Redis.ping()
 -> open_checkpointer(AsyncPostgresSaver.setup())
 -> build_agent_graph(checkpointer)
 -> LongTermMemory() / SessionStore()
 -> FastAPI 接受请求
~~~

若 PG 或 Redis 不可用，API 可能在启动期失败；若 `/health` 显示依赖 `down`，先查依赖，别直接猜是 Qwen 或 LangGraph 出错。

安全的检查命令（不会触发模型下载或构建）：

~~~cmd
cd /d E:\project\DocMind-Agent
docker compose ps
curl --noproxy "*" http://127.0.0.1:8090/health
docker compose logs --tail 80 api
~~~

### 4.3 哪些 API 真正存在？

| 方法 | 路径 | 功能 |
|---|---|---|
| POST | `/v1/documents` | 验证/保存原文件，HTTP 201 |
| POST | `/v1/documents/{document_id}/index` | 分块、Embedding、Qdrant 索引 |
| POST | `/v1/chat` | 所有用户可见 Agent 任务入口 |
| GET | `/v1/sessions/{session_id}` | 近期会话历史/Checkpoint 标志 |
| POST | `/v1/approvals/{approval_id}` | 人工批准/拒绝，恢复图 |
| GET | `/health` | 检查 PG/Redis/Qdrant |
| GET | `/metrics` | Prometheus 文本 |

**没有**单独对外公开的 `/rag`、`/mcp`、`/admin/trace` 端点。MCP 是进程间 stdio 工具协议，RAG 是工具内部 Python 函数。

### 4.4 看懂一个请求与响应

请求体示意（UUID 需要替换成真实合成文档 ID）：

~~~json
{
  "query": "根据合同，验收后的付款期限是多少？",
  "document_id": "00000000-0000-0000-0000-000000000001",
  "session_id": null,
  "user_id": null
}
~~~

典型返回字段：

- `request_id` / `trace_id`：此次请求/追踪的不同 UUID。
- `session_id`：关联 Redis Session 和 LangGraph Checkpoint 的线程 ID。
- `intent`、`plan_source`、`tools_called`、`mcp_tools_called`：选择了什么工具，是规则还是经验证的模型规划。
- `status`、`retry_count`、`steps`、`tool_events`：流程是否成功，重试几次，哪里耗时。
- `answer`、`sources`、`entities`：最终回答、来源和结构化字段。
- `context_applied`、`memory_applied`：是否使用历史问题/偏好提示。

**HTTP 200 + `status=tool_unavailable` 是业务失败；HTTP 409 可能是同一 Session 正在执行、图暂停审批或已有冲突决策。** 不能只盯着状态码。

### 4.5 Docker 各命令有什么差别？

- `docker compose up -d`：在镜像存在时启动服务，不保证更新镜像中的源码。
- `docker compose up -d --build api`：触发镜像构建；你遇到的 Docker Hub 镜像源 DNS / EOF 属于网络构建环节。
- `docker compose restart api`：仅重启容器，不更新已安装 wheel。
- `docker compose cp ... api:/app/...`：向运行中的容器临时拷贝源码，**镜像本身不会更新**。
- `docker compose exec -T -e PYTHONPATH=/app api python -m scripts.check_m9 live`：按项目源码优先导入 M9 脚本，避免旧 `site-packages` 包与新源码混用。
- **不要随意 `docker compose down -v`**：会删除 PG、Redis、Qdrant、上传文档与模型缓存等持久卷。

<a id="ch05"></a>
## 05｜M1：文件如何成为可引用的 Chunk？

### 5.1 为什么上传和索引是两次 API？

`app/api/documents.py`：

~~~text
POST /v1/documents
  -> safe_filename
  -> 最大 10 MiB / 空文件检查
  -> parse_document 预验证可读文本
  -> 原件写入 documents-data 卷（以 UUID 命名）
  -> INSERT PostgreSQL documents，status=uploaded
  -> 返回 document_id（HTTP 201）

POST /v1/documents/{document_id}/index
  -> PG claim_indexing（status=indexing，避免并发重复）
  -> 从卷读取原件
  -> parse_document / chunk_document
  -> embed_texts（CPU ONNX，512 维）
  -> store_document_vectors（Qdrant）
  -> finish_indexing（indexed / failed）
~~~

索引可能需要较长 CPU 时间。将原件保存与向量索引分开，是为了解耦失败和支持后续重试；201 **不等于**已经可检索。

### 5.2 三种解析格式的差异

源码：`app/rag/parser.py`。

- **PDF**：PyMuPDF 按页提取可选中文本；`page` 从 **1** 开始。纯图片扫描 PDF 没有 OCR，不能被当前解析。
- **DOCX**：按段落和表格读取，标题赋值 `section`；由于无法稳定还原 DOCX 的纸面物理页码，所以 `page=None`。
- **TXT**：尝试 `utf-8-sig`，失败后 `gb18030`；没有物理页码。
- **文本规范化**：换行/空格/NUL 字节整理；**不是**任意格式文档的智能理解。

### 5.3 Chunk 的实现

源码：`app/rag/chunker.py::chunk_document`。默认按**字符**分块：

~~~text
chunk_size = 400
overlap    = 60
~~~

一个长段落被切成相邻、部分重叠的片段，有利于保留跨边界短语；优先按换行或标点附近截断。对 PDF 每个页文本块单独切分，所以不会让一个 Chunk 跨两页。

Chunk ID 使用 `uuid5(NAMESPACE_URL, document_id:block_index:start:end)`，同一文件、相同划分在重复运行时能得到稳定的 Chunk ID。

典型来源字段示例：

~~~json
{
  "document_id": "原文档 UUID",
  "chunk_id": "片段 UUID",
  "filename": "合同.pdf",
  "page": 2,
  "section": null,
  "chunk_index": 3,
  "source_block_index": 1,
  "start_offset": 280,
  "end_offset": 680,
  "text": "本页的合同条款内容...",
  "embedding_model": "BAAI/bge-small-zh-v1.5"
}
~~~

这个 JSON 是**字段示意，不是真实测试记录**。请记住来源引用的关键事实：**页码、文档 UUID、Chunk ID 必须在索引时保留下来，不能让 LLM 事后编造。**

### 5.4 Embedding 与 Qdrant 配合

`app/rag/embedder.py` 把文本映射成 512 维向量；模型为 `BAAI/bge-small-zh-v1.5`，通过 ModelScope 的社区 ONNX 版本缓存，由 FastEmbed/CPU 执行。Qdrant Point = Chunk UUID + 512 维向量 + 文字/位置 Payload。

`app/storage/qdrant.py::store_document_vectors` 对同一个文档先按 `document_id` 删除旧 Point，再 upsert 新 Point，最终核对写入数量。这是在**维持数据一致性**，不是简单地一次次重复累加向量。

**Embedding vs Reranker**：前者对文本分别编码以供快速召回；后者把 Query 和一个候选片段共同输入 Cross-Encoder 得到关联性分数，计算成本更高。

### 5.5 你应该能回答

1. 为什么 `documents.status` 要记录 `uploaded` / `indexing` / `indexed` / `failed`？
2. `chunk_id` 与 `document_id` 有何不同？
3. DOCX 的 `page=None` 是 Bug 还是来源设计选择？
4. 扫描版 PDF 失败属于 Parser 还是 Qwen 出错？
5. 前一次 10 个 Chunk、第二次 8 个 Chunk，如何避免残留旧向量？

先按源码自己回答，答案思路见第 18 章。



<a id="ch06"></a>
## 06｜M2：Dense + BM25 + RRF + Reranker + Qwen + Citation

这一章是 RAG 面试的重点。请首先分清五个动作：**召回、融合、重排、生成、校验**。它们有不同的输入、输出和耗时，不能统称“向量检索”。

### 6.1 RAG 是什么？为什么不用完整合同直接提问？

RAG = Retrieval-Augmented Generation，即“检索增强生成”。做法是先找出与用户问题有关的原文片段，再把这些片段作为条件交给 LLM。可以减少上下文长度、暴露证据位置、便于追溯。但如果召回漏掉了关键条款，后续再强的 LLM 也无法从不存在的证据里可靠恢复答案。

本项目完整流程位于 `app/rag/pipeline.py::answer_document_question`：

~~~text
normalize_question（仅处理空白）
  -> hybrid_search（Dense + BM25 + RRF）
  -> rerank_hits（BGE Cross-Encoder）
  -> build_sources（为有限证据分配 S1/S2）
  -> format_evidence（明确标记为非可信文档内容）
  -> complete_chat（OpenAI-compatible Qwen）
  -> validate_answer_citations
  -> RagAnswer（answered / no_evidence / citation_unverified / insufficient_evidence）
~~~

**代码细节**：`normalize_question` 只是空白规范化，**不包含真正的语义 Query Rewrite 模型**。只有 `app/memory/session.py::resolve_followup` 会在特定短追问场景进行保守的规则上下文扩展。架构需求里写过 Query Rewrite，不代表复杂查询改写已经实现。

### 6.2 Dense Retrieval：语义相似度召回

源码 `app/rag/retriever.py::hybrid_search`：

1. 查询也用同一 BGE Small 模型转成 512 维向量。
2. Qdrant `query_points(query=vector)` 按向量相似度排序。
3. 当请求附带 `document_id` 时，`_document_filter` 构造 Qdrant Filter，让跨文档召回不能混入其他合同。
4. 记录每个候选 Chunk 的 `dense_rank`。

优势：同义表达、语义近似；风险：条款号、主体名称、精确数值可能需要更强的词面约束。

### 6.3 Sparse Retrieval：项目自己的中文双字 BM25

源码 `app/rag/sparse.py::lexical_tokens`、`bm25_rank`。

例如：“违约责任”可能产生 `违约`、`约责`、`责任` 三个重叠字双元组。对汉字部分不依赖额外中文分词词典；英文/数字通常按词处理并转小写。

BM25 的核心原理：

$$
\operatorname{score}(q,d)=\sum_{t\in q}\operatorname{IDF}(t)
\frac{f(t,d)(k_1+1)}
{f(t,d)+k_1(1-b+b|d|/\operatorname{avgdl})}
$$

- `f(t,d)`：term 在某 Chunk 出现几次。
- `IDF(t)`：在整个集合越少见越有区分度；代码使用正向的平滑 IDF。
- `|d| / avgdl`：长度归一化，不让长 Chunk 因为含词多就绝对占优。
- 本项目默认 `k1=1.5`、`b=0.75`。

**本项目的现实局限**：BM25 候选语料来自 `app/rag/retriever.py::_read_corpus` 对 Qdrant Payload 的 `scroll`，默认上限 `max_scan_chunks=5000`；然后对这些文本临时计算 BM25。**不是** Elasticsearch 或 Qdrant Sparse Vector 的生产级倒排索引。超过上限会明确报错，不会暗中只取前 5000 条。

### 6.4 RRF：为什么不直接把两个分数相加？

Dense 的 cosine 距离/相似度和 BM25 词频相关分数**量纲、分布不一致**。RRF 只依赖名次：

$$
\operatorname{RRF}(d)=\sum_{r\in\{\text{Dense,BM25}\}}\frac{1}{60+\operatorname{rank}_{r}(d)}
$$

源码 `app/rag/fusion.py::reciprocal_rank_fusion`，`k=60`。例如：

| Chunk | Dense 名次 | BM25 名次 | RRF 大致计算 |
|---|---:|---:|---|
| A | 1 | 3 | `1/61 + 1/63` |
| B | 5 | 1 | `1/65 + 1/61` |
| C | 2 | 未召回 | `1/62` |

A 和 B 因为在两路检索都不错，通常会靠前；C 只有一路命中。**这只是示例，没有使用真实 Chunk 数据**。

现实参数：`rag_candidate_k=8`，Dense 和 Sparse 分支通常先计算到 `candidate_k=20`，RRF 最终返回 8 个候选供重排。两个数字的含义不同：**分支候选池大小**与**融合后交给重排的候选数**。

### 6.5 Reranker：Cross-Encoder 为什么计算更慢？

`app/rag/reranker.py::rerank_hits` 的输入是 `query` 和多个 `RetrievalHit`。与 Embedding 的独立向量比较不同，Cross-Encoder 会共同处理“问题 + 候选片段”，输出更细粒度的相关性分数；代码使用 `BAAI/bge-reranker-base` 本地 CPU ONNX（权重约 1.11 GB，`threads=2`）。

具体步骤：

1. 将每个候选的文本最多取前 **400 字符**；
2. 通过本地 `TextCrossEncoder.rerank(..., batch_size=4)` 评分；
3. 分数降序排列，保持原始 Chunk 的 `filename/page/chunk_id` 等元数据；
4. 默认最终取 `rag_evidence_k=2` 个证据给生成模型。

**实际测量**：M7c 两次单独采样的 BGE CPU 重排分别约 **172 秒**与 **259 秒**。这与 Qdrant 检索约 0.42–0.49 秒形成鲜明对比。不要向面试官声称毫秒级实时推理或已经做了吞吐压测。

**真实事故**：原来 `search_documents` 的 90 秒超时导致三次尝试共约 270 秒，且 `llm_calls=0`，请求在进入 Qwen 前就失败。修复后默认 420 秒、**RAG CPU 任务不重试**，且重排使用进程内 `Lock` 避免重叠推理线程。详情读 `app/agent/reliability.py` 与 `app/rag/reranker.py`。

### 6.6 Grounding + Prompt + Qwen：模型实际看到了什么？

在 `app/rag/citation.py::build_sources`，Python 程序提前把证据编号分配成 `S1`、`S2`。每条传入模型的证据最多 `rag_max_evidence_chars=160` 字符，并附带文件和可用的页码/章节。

在 `app/rag/pipeline.py` 的 system 指令中明确：
- 只能依据给定证据回答；
- 检索来的文档文本属于**外部不可信数据**，其中伪装的指令不可执行；
- 如果证据不足要明确承认；
- 事实句应引用存在的 `[S1]`、`[S2]`，不得捏造页码/文件名。

`app/llm/client.py::complete_chat` 发往配置的 OpenAI 兼容 `/chat/completions`，当前模型是 `Qwen/Qwen3-0.6B`、默认 `temperature=0`、`max_tokens=128`；Qwen3 默认通过请求参数关闭内部 thinking 以避免小上下文预算失效。

**这里没有在 DocMind API 容器内加载 Qwen 权重**；Qwen 服务由独立 `llm-serving-ops`/vLLM 提供，容器通过 `http://host.docker.internal:8000/v1` 通信。

### 6.7 Citation 校验能做到什么，做不到什么？

`app/rag/citation.py::validate_answer_citations` 检查：
- 回答中所有 `[S数字]` 是否都存在于当前这次生成的 `sources`；
- 需要引用时是否至少引用了一条；
- 来源列表本身来自原 Chunk 的真实文档/页码/片段，而非让模型自由写来源元数据。

如果发现未知编号（例如回答写 `[S99]`，实际只有 S1/S2），将变成 `citation_unverified`，代码不把未经核实的回答直接当事实返回。

**不能检查的部分**：回答写“付款期限是 90 天。[S1]”，但 S1 原文是“30 天”——编号合法但事实是错的。要验证语义蕴含，需要进一步设计事实核查/人工标注/LLM Judge 或结构化断言；本项目没有声称已解决。

### 6.8 本章实战复述题

1. 从 `hybrid_search` 说出 Dense、Sparse、RRF 各个输入和输出。
2. 什么时候需要 `document_id` 过滤？过滤遗漏有什么风险？
3. 如果 BM25 只是在 Qdrant 上遍历文本，最多能处理多少 Chunk？
4. 为什么要 Cross-Encoder 重排而不是直接选第一条 Dense 命中？
5. `[S1]` 是谁分配的？Citation Accuracy=100% 是否代表回答永远正确？
6. M9 的 270 秒故障为什么不是 Qwen 连接错误？

<a id="ch07"></a>
## 07｜M3：LangGraph Agent 如何运行？

### 7.1 Agent 与普通 RAG 的本质区别

普通 RAG 管道通常是固定的“问题 → 检索 → 生成”。本项目的 Agent 在外层增加**显式状态、意图决策、类型化工具、有限步循环、Checkpoint 和安全分支**：

~~~text
START
  ↓
route
  ↓
decide ────────────→ synthesize ─→ END
  │                       ▲
  └→ call_tool ─→ decide ─┘
~~~

真实定义位于 `app/agent/graph.py::build_agent_graph`。源码使用 `StateGraph(AgentState)`、`add_node`、`add_edge`、`add_conditional_edges`，最后 `compile(checkpointer=...)`。

它在“有限工具型工作流 Agent”的工程意义上成立，但**不是**开放式自主 ReAct、Multi-Agent 或无限反思系统。

### 7.2 AgentState：为什么要把状态写得明确？

阅读 `app/agent/state.py::AgentState`。几个核心字段：

| 字段 | 含义与赋值位置 |
|---|---|
| `session_id / user_id / document_id` | 当前会话、演示用户和文档范围；API 初始化 |
| `query / format_hint` | 当前解析后的问题、白名单长期格式偏好 |
| `intent / plan` | `route_node` 的意图和工具名称序列 |
| `plan_source` | `rules` / `llm_validated` / `rule_fallback` |
| `next_tool` | `decide_node` 选择的当前工具 |
| `tool_results / tools_called` | 每一步工具结果和已调用名称 |
| `current_step` | 图已执行的工具步数，不等于内部 Retry 次数 |
| `retry_count / reliability_events` | 可靠性执行器的尝试/错误/耗时 |
| `sources / entities / final_answer / status` | 最终合并后的证据、抽取实体和回答 |
| `approval_id / approval_required` | HITL 相关状态 |

**为什么 State 与 Redis Session 分开？** State 是一次图运行的工作状态，Checkpoint 会保存节点快照；Redis 只存最近的问答轮次与文档上下文，不能替代图恢复所需的完整节点状态。

### 7.3 四个真实图节点的职责

1. **`route_node`**：调用 `plan_tools`，写入必要工具序列、计划来源，并重置当轮的工具结果、步骤、引用等字段。
2. **`decide_node`**：若 `current_step>=8`，令 `next_tool=None` 并标记 `step_limit`；若计划已执行完，则直接到 `synthesize`；否则选择 `plan[current_step]`。
3. **`call_tool_node`**：根据工具名构造参数，普通只读调用 `execute_read_only_tool(name, executor=invoke_tool)`，把结果与 `tool_events` 加入 State；对 `save_review_note` 走 `interrupt()` 特殊分支。
4. **`synthesize_node`**：组合多个工具的回答，**把不同工具局部 `[S1]` 映射成全局唯一来源编号**，统一判断 `answered`、`partial`、`tool_unavailable`、`no_evidence`、`citation_unverified` 等状态。

例如两个工具都各自使用了 `[S1]`，但指的是不同 Chunk：如果简单字符串拼接，读者就无法知道哪个 S1 对应哪条证据。实际代码 `_relabel_tool_result` 通过 `source_map` 做重编号，同时重映射 `entities.source_id`；未知编号改成 `[INVALID_SOURCE]`，不会当成正常结论。

### 7.4 Router：哪些任务规则执行，哪些会调用模型规划？

代码 `app/agent/router.py` 有两个层次：

**第一层** `select_tool_plan(query)`：关键字和正则规则形成保守默认计划。例如：

| 输入 | 典型默认计划 | 特点 |
|---|---|---|
| “查询文档信息” | `["query_document_metadata"]` | PostgreSQL 元数据；无 Qwen |
| “提取甲乙方及付款期限” | `["extract_entities"]` | 规则抽取；无 Qwen |
| “合同付款期限是多少？” | `["search_documents"]` | 工具内部要执行 Qwen RAG |
| “通过 MCP 查找违约责任条款” | `["mcp_find_clause"]` | 标准协议 MCP；通常无 Qwen |
| “提取合同主体并总结主要风险” | `["extract_entities","summarize_document"]` | 可能执行受限 LLM 工具**排序** |

**第二层** `plan_tools`：只有 **默认必要工具至少 2 个，且包含提取或摘要，并提供文档 ID**，才尝试 Qwen 排序。模型必须返回如 `{"tools":["extract_entities","summarize_document"]}` 的 JSON，程序核对：是否在白名单、是否重复、是否保留**完全相同的必要工具集合**、长度不超过 4。模型**不能凭空加一个 shell、SQL 写入或网络搜索工具**。

模型不可用、格式不合法、工具集合不符时，使用 `rule_fallback` 并记录失败类型。这既使项目可以有限利用模型的计划能力，也保证可重现和受控。

### 7.5 有状态循环与 ReAct 的关系

“观察 → 决策 → 行动 → 得到工具结果 → 再决策”具有 Agent 工具迭代的共同结构；但本项目不是每步都让模型重新自由推理一个全新 Action，而是 `plan` 先确定，`decide` 按顺序执行，达到上限即停止。

**面试表达推荐**：

> 使用 LangGraph 构建显式有状态、可恢复的受控工具型 Agent；简单任务规则路由，复杂任务可让 Qwen 在必要工具白名单内排序。图节点通过 TypedDict State 保存计划、工具结果与可靠性事件，并限制最多 8 步，防止无上限循环。

不要说“自主 ReAct Agent 可以处理任意任务”“LLM 自主探索任意工具”“多智能体协同”，因为源码并未实现。

### 7.6 为什么选择 LangGraph 而不是一段 while 循环？

在简单任务里 Python `while` 也能调用工具，但很难天然维护可见的节点状态、Checkpoint 和精确的审批恢复边界。LangGraph 的增益在于：
- 节点/边清晰、状态结构化；
- 编译图可以绑定 PostgreSQL `AsyncPostgresSaver`；
- `interrupt()` 可暂停并由 `Command(resume)` 继续；
- 每个节点可添加独立 Trace；
- 可用单元测试分别覆盖 route、decide、call_tool、synthesize。

其成本则是需要理解持久化线程 ID、状态覆盖、重放/并发边界，不能仅靠“引用了库”就保证安全性。

<a id="ch08"></a>
## 08｜工具系统与 MCP：Agent 是如何调用“外部能力”的？

### 8.1 工具不是任意 Python 函数

`app/tools/registry.py::invoke_tool` 为工具建立“名称 → Pydantic 参数模型 → 处理函数”的固定映射。模型输出或图拼接参数都要经过 `model_validate` 才能进入业务函数。

主要只读工具：

| Agent 工具名 | 源码 | 功能与实际限制 |
|---|---|---|
| `query_document_metadata` | `tools/metadata.py` | PostgreSQL 文档列表/状态/片段数量 |
| `extract_entities` | `tools/extraction.py` | 从 Qdrant 原始 Chunk 用正则找甲方/乙方/丙方与付款期限；不是通用法律 NER |
| `search_documents` | `tools/retrieval.py` | 完整 Dense+BM25+RRF+重排+Qwen RAG |
| `summarize_document` | `tools/summary.py` | 对**检索到的证据**做有引用的摘要，不保证覆盖整份文档 |
| `mcp_get_document` | `tools/mcp_bridge.py` | stdio MCP 的 `get_document`；文档元数据 |
| `mcp_get_document_page` | 同上 | stdio MCP 的 `get_document_page`；只对有真实页码的 PDF 有意义 |
| `mcp_find_clause` | 同上 | stdio MCP 的 `find_clause`；按关键词匹配原文 Chunk |
| `mcp_search_documents` | 同上 | stdio MCP 的 `search_documents`；返回混合检索**证据**，不调用 Qwen 生成 |

**受保护的 `save_review_note`** 不在普通只读工具注册表里；它只能通过专用 HITL 路径执行。这个区分是安全设计的关键。

### 8.2 看一眼实体抽取的真实能力

`app/tools/extraction.py` 读取指定文档已索引的文本，使用 `PARTY_PATTERN` 找“甲方：公司名称”等，使用 `TERM_PATTERN` 找中文/数字时间表达。只有与支付/付款/结算等词同句时，才将天/月/年的词组标记为“付款期限”。

抽到的实体含 `field`、`value`、`chunk_id`、`source_id`，并返回 `[S1]` 等引用。这是**正则规则工程基线**。它不具备通用 NER 模型的跨句角色理解、任意实体标签或监督训练能力；论文中的 NER 研究方法也没有自动集成进此工程。

### 8.3 MCP 的基本概念

MCP（Model Context Protocol）为工具提供**协议层的声明、发现和调用**。在本项目：

~~~text
LangGraph call_tool_node
   -> invoke_tool("mcp_find_clause", params)
   -> app/tools/mcp_bridge.py
   -> app/mcp_client/adapter.py::call_document_mcp
   -> stdio_client 启动独立进程（python -m mcp_server.server）
   -> MCP initialize
   -> tools/list（发现工具）
   -> tools/call("find_clause", 参数)
   -> FastMCP Server handler
   -> 读取 PG/Qdrant
   -> MCP 返回 structuredContent/JSON
   -> bridge 验证文档范围和证据字段
   -> LangGraph 合并来源、输出结果
~~~

**事实**：本项目使用官方 MCP SDK 的 `ClientSession` 和 `FastMCP`，协议承载在**stdio** 上；并非把一个 HTTP 接口随便叫 MCP，也不是将 Server 函数直接 import 到 Agent 里。当前是**每次调用新开本地 Server 子进程**，所以调用存在进程启动与协议初始化开销；不是跨多个请求共享一个长驻远端 MCP 服务。

### 8.4 为什么 MCP 要做 Adapter 与 Bridge 两层？

- `mcp_client/adapter.py`：解决协议生命周期（启动 stdio、初始化、发现、调用、解析结果、超时）。
- `tools/mcp_bridge.py`：解决业务契约（工具名映射、UUID 范围检查、从真实 Chunk 构造 `sources`、截取长度、引用编号）。
- `mcp_server/document_tools.py`：在 Server 进程里真正执行 PostgreSQL 元数据、Qdrant PDF 页/条款查找、混合检索。

**为什么不直接信任 MCP 返回值？** MCP Server 即使是自建的，也要防止工具参数错误、返回的 `document_id` 不匹配、证据缺失 `chunk_id`、伪造 `[S99]` 等。Bridge 发生源范围校验错误时不会“降级成调用本地函数偷偷成功”。

### 8.5 同名 `search_documents` 可能代表两个不同层次

- Agent Registry 的 `search_documents`：**完整 Qwen RAG**，会经过 Cross-Encoder、生成和 Citation 检查。
- MCP Server 的 `search_documents`：**混合检索的证据列表**，由 `mcp_server/document_tools.py::search_indexed_documents` 直接调用 `hybrid_search`，**不执行 BGE Cross-Encoder 重排或 LLM 回答**。
- Agent Registry 的 `mcp_search_documents` 才是调用第二者的桥接工具，返回 `mcp_tools_called=["search_documents"]`。

因此看日志要同时读 `tools_called` 与 `mcp_tools_called`，不能只看一个工具名字就断言一定经过 Qwen。

### 8.6 MCP 安全边界和面试答法

模型不能传任意脚本、数据库 SQL、文件路径等；已注册 MCP 工具全部是受限读取，UUID、页码、关键词、返回数量有严格验证。**MCP 提供互操作接口，但不天然提供生产鉴权、沙箱或零信任安全。** 本地 stdio 进程继承环境，必须控制运行权限和工具定义，不能把“用了 MCP”说成“工具调用自动安全”。

<a id="ch09"></a>
## 09｜M4：四种不同含义的 Memory

### 9.1 概念对照

| 名称 | 生命周期与存储 | 当前项目实例 |
|---|---|---|
| Working Memory | 一次图执行过程中的临时数据 | `AgentState.plan/tool_results/current_step/sources` |
| Session Memory | 若干对话轮次和当前文档，有限 TTL | `app/memory/session.py` 的 Redis JSON（最多 6 轮，空闲 3600 秒） |
| Long-term Memory | 用户明确保存且适合跨会话复用的偏好 | PG `memories` + Qdrant `memories_v1` |
| Checkpoint | LangGraph 节点执行快照，用于中断恢复 | `AsyncPostgresSaver`，使用 `thread_id=session_id` |

不能说“Redis 存所有持久记忆”或“Checkpoint 是聊天摘要”。两者目的与可靠性都不同。

### 9.2 Redis Session 保存了什么？

`app/memory/session.py::SessionStore.append_turn` 保存：用户原问题、解析后的 `resolved_query`、回答、状态、时间戳、当前 `document_id` 和选填的 `user_id`；每条 Query 最多截取 1000 字、Answer 1200 字。**不会把 Qdrant 的原始工具结果和整个检索候选集搬进会话**。

默认：
- `session_ttl_seconds=3600`（空闲超时）；
- `session_max_turns=6`；
- `session_lock_seconds=300`，通过 Redis `SET NX EX` 防止同会话同时执行；释放锁使用 Lua Compare-and-Delete，避免误删后续请求锁。

注意现存局限：**RAG 允许 420 秒执行而 Session 锁租期默认只有 300 秒**。虽然图还有 Checkpoint/暂停控制，面向并发的真实产品应设计锁续租/更长预算/任务队列，不能把这个本地 Demo 宣称为充分并发安全。

### 9.3 短追问到底是怎样“记住上下文”的？

`app/memory/session.py::resolve_followup` 是**保守规则扩展**。条件包含：
- 之前确实有会话轮次；
- 当前问题不长于 60 字；
- 当前与之前是**同一个 document_id**；
- 当前问题包含“如果、逾期、那、它、这个、还有”等提示词。

满足时将“上一个问题 + 当前追问”整理为可检索 Query，`context_applied=true`。例如先问“付款期限是什么”，再问“如果逾期呢”；本项目不是让另一个大模型任意归纳全部历史或开展复杂 Query Rewrite。

### 9.4 长期记忆为什么仅限显式偏好？

`app/memory/long_term.py` 只接受类似“请记住合同分析按主体、金额、期限、风险、引用格式输出”。白名单字段只有：

~~~text
主体、金额、期限、风险、引用
~~~

且至少包含 3 类有效字段。程序 `parse_format_preference` 按明确指令解析，然后 `LongTermMemory.save_format` 先在 PG `memories` 标记 `is_indexed=FALSE`，再把同一偏好向量写 Qdrant，完成后标记为 TRUE。

查询时 `LongTermMemory.search` 在 Qdrant 限定 `user_id` 与 `memory_type=preference`，随后**还要用 PG 再次校验**同一个用户和已索引状态，再将白名单字段变成 `format_hint` 给 RAG Prompt。

为什么做双端校验？因为向量库是语义候选索引，PG 是结构化权威来源；不能仅靠 Qdrant payload 作为用户权限或事务成功证明。**但这里的 user_id 由调用方提供，仍不是真实身份认证。**

### 9.5 Checkpoint 如何让 LangGraph 恢复？

`app/memory/checkpoint.py` 使用官方 `AsyncPostgresSaver`、`setup()`，`thread_config(session_id)` 映射：

~~~python
{"configurable": {"thread_id": session_id}, "recursion_limit": 30}
~~~

一次图运行完成节点后，会保存对应线程的 State 快照。受保护写入的 `interrupt()` 使图停在 `call_tool`，恢复时使用同一 `thread_id` 和 `Command(resume=...)`，而不是重新从文件解析、重新推理全部工具。

**要区分：**
- Session 记住**用户刚才说了什么**；
- Long-term Memory 记住**明确保存的稳定格式偏好**；
- Checkpoint 记住**图执行到了哪里、下一步如何继续**；
- AgentState 是**本次工作流的字段容器**。

### 9.6 本章练习

1. 把“先问付款期限，再问如果逾期”在 `chat.py` 和 `session.py` 中走一遍，找出 `context_applied` 赋值。
2. 说出 `memory_saved`、`retrieved_memories`、`memory_applied` 的区别。
3. 说出偏好在 PG 写入与 Qdrant Upsert 之间断电时如何表现。
4. 如果只给一个新 `session_id`，不提供既有 `user_id`，会自动检索以前存的偏好吗？
5. 为什么不能把“已部署 Redis”当作“已实现长期持久化记忆”？



<a id="ch10"></a>
## 10｜M6：可靠性、Human-in-the-Loop 与幂等写入

### 10.1 为什么 Agent 调用工具一定需要可靠性层？

普通 Python 调用失败抛异常即可，但 Agent 的用户可能等待多个工具串行执行：某一个 MCP 或 RAG 请求超时后，若直接报错，之前成功的工具答案可能丢失；若乱重试，可能造成重复计算甚至重复写入。

本项目把普通只读执行统一包在 `app/agent/reliability.py::execute_read_only_tool`：

~~~text
校验工具名在只读白名单中
  → 查询当前工具的 ToolPolicy
  → asyncio.wait_for(调用工具, timeout)
  ├── 正常结束：status=ok、记录耗时/尝试次数
  ├── 可重试的暂时性错误：在最多允许次数内等待并重试
  ├── 重试耗尽：status=tool_unavailable，返回无来源的 Fallback
  └── 参数/类型/来源契约错误：抛出，不伪装成成功
~~~

工具事件 `tool_events` 会记录 `tool/status/attempts/retries/timeout_seconds/duration_ms/error_type`，并与 LangGraph State 的 `retry_count` 对应。重试次数**不增加**图的 `current_step`；后者最多 8 个外部工具步骤。

### 10.2 目前的真实超时策略

| 工具 | 时间预算 | 自动重试 |
|---|---:|---:|
| `query_document_metadata` | 15s | 最多 2 次 |
| `extract_entities` | 45s | 最多 2 次 |
| `mcp_get_document` | 40s | 最多 2 次 |
| `mcp_get_document_page` / `mcp_find_clause` | 60s | 最多 2 次 |
| `mcp_search_documents` | 90s | 最多 2 次 |
| **`search_documents` / `summarize_document`** | **默认 420s，允许配置 300–600s** | **0 次** |

M9 的实际事故推动了最后一行的修改：BGE CPU 重排单次就可能超过 90s；`asyncio.wait_for` 取消等待时，`asyncio.to_thread` 中 ONNX 的底层计算不一定停止。三次重复执行只会浪费 CPU，并可能造成多个残留线程竞争。改为**一个足够但有界的完整 RAG 调用预算**，并通过进程内 `Lock` 限制并发 rerank 调用。

**边界仍然存在**：锁只针对当前 API 进程，不是多 Pod / 多容器分布式锁；超时后的 ONNX 工作线程也不一定被杀掉。生产方案可能需要独立推理服务、队列、GPU/更轻量模型及任务取消机制。

### 10.3 什么错误可以 Retry？

`retryable_error` 识别临时连接、超时、`httpx.TransportError`、`asyncpg.PostgresConnectionError`，以及指定 HTTP 429/5xx。格式不合法、未知工具、字段契约违背、非法引用不应被“重试直至生成一个看似合理结果”。

**Fallback 必须无事实编造**，例如“工具不可用，无法确认”，`sources=[]`。多工具任务中一个工具失败、另一个已经成功，可返回 `partial` 并保留成功来源。注意 `no_evidence` 与 `tool_unavailable` 不同：
- `no_evidence`：工具正常运行，但找不到相关证据；
- `tool_unavailable`：工具没有正常完成，不能断言资料不存在。

### 10.4 什么叫 HITL？

Human-in-the-Loop：在需要人批准的敏感动作前，系统**强制暂停**并等待外部决定。本项目受保护的写操作只有 `save_review_note`（保存审核备注），不是任意删除、银行支付或所有工具。

真实调用路径：

~~~text
用户 POST /v1/chat，query="保存审核备注：请核对付款条款"
  -> approvals/policy.py 精确匹配写入指令（备注 1–500 字）
  -> PG INSERT approvals(status=pending)，只针对已索引文档
  -> graph.ainvoke(..., approval_id=...)
  -> call_tool_node 特殊调用 _resume_protected_review_note
  -> interrupt({"approval_id": ..., "tool": "save_review_note"})
  -> PG Checkpointer 保存暂停图
  -> API 返回 approval_required / approval_id / session_id
  -> 此时 PG review_notes 必须为 0 条

用户 POST /v1/approvals/{approval_id}, decision="approve"
  -> API 校验 user_id、session_id 与审批记录一致
  -> PG row lock SELECT ... FOR UPDATE
  -> 持久保存 APPROVED 决策
  -> graph.ainvoke(Command(resume={...}), same thread_id)
  -> 图恢复 call_tool_node
  -> execute_approved_review_note()
  -> PG 事务 INSERT review_notes
  -> 返回 approved / review_note_id
~~~

拒绝会返回 `rejected`、不执行写入；相反的重复决策返回 HTTP 409。

### 10.5 为什么审批决定要先落库，再恢复图？

考虑“人点击批准后 API 立刻宕机”：
- 如果先执行外部写入后才保存批准状态，宕机重试可能无法确定是否写过。
- 本项目先在 PG 持久记录批准决策，再从 Checkpoint 恢复；即使恢复途中再次崩溃，下次可以核对决策和写入状态。
- `app/approvals/storage.py::execute_approved_review_note` 在事务中 `SELECT ... FOR UPDATE`，通过 `review_notes.approval_id UNIQUE`、`ON CONFLICT DO NOTHING` 与由 approval ID 派生的稳定 `review_note_id` 防止重复插入。

**这证明的是“当前受保护 PostgreSQL 审核备注写入”的幂等行为**，不能推广为“任意第三方转账、发送邮件、远程 MCP 写入都是 exactly-once”。

### 10.6 Human Approval ≠ 真实身份认证

审批 API 要求传精确 `user_id`、`session_id`，并检查数据库关联一致；但这些 UUID 是调用方自己提供的**演示身份标识**，不是 JWT/OAuth 登录凭证。真实多用户服务必须实现认证、RBAC、文档权限、审计保留及网络隔离。

### 10.7 本章考点

- Retry 与业务幂等有何关系？写操作为何不能与只读工具共用策略？
- `interrupt()` 与 `time.sleep()` 等人回复有什么本质区别？
- Checkpointer 在崩溃前后保留了什么？
- 执行完毕返回 HTTP 200，但 `status=partial` 怎么向用户解释？
- 为什么取消 asyncio Task 不代表 ONNX CPU 线程中断？

<a id="ch11"></a>
## 11｜M7：怎么评测 RAG、Agent 和系统性能？

### 11.1 为什么不只看“回答看起来对不对”？

需要把三个独立问题拆开：
1. **RAG 证据检索**：正确相关文档/片段是否进入候选 Top-K？
2. **Agent 工具和业务目标**：路由是否正确、工具是否完成、最终输出是否满足明确的字段与证据要求？
3. **运行成本**：请求总时延、检索/重排时延、工具调用、模型调用数与 Token 如何？

三个层次不互相替代：Recall 高可能生成出错；工具选对不等于业务事实正确；响应快也不意味着有效。

### 11.2 M7a：Recall@K 和 MRR@K

真实代码：`eval/rag_metrics.py`、`scripts/check_m7a.py`、`eval/datasets/m7a_retrieval.json`。

- **Recall@K** = Top-K 中命中的 gold 相关文档数 / gold 相关文档总数，最后对 Query 求平均。
- **MRR@K** = 对每个 Query 找到第一个 gold 相关文档的名次 `r`，计 `1/r`；没找到计 0，再取平均。
- 本项目的评价单位是**Document ID 去重后的排序**，不是 Chunk 级、实体级或答案级。

例子：一个 Query 的相关文档 `{A,B}`，Top-3 排序 `[C,B,D]`，则 Recall@3=1/2=0.5，RR@3=1/2=0.5。

2026-10-15 本地结果：3 个合成查询 Recall@3=1.0、MRR@3=1.0，另有 63 个非当前 Fixture 的候选 Chunk 参与检索。**小样本、共享 Qdrant、未隔离历史索引**，不能视作真实法律数据的泛化质量。

### 11.3 Citation Accuracy 不能混成 Faithfulness

`citation_provenance_accuracy` 使用 `validate_answer_citations` 检查来源 ID 合法性；**不做语义蕴含**。如果回答中时间是错的、来源 ID 却合法，这项检查可能依旧通过。

面试应主动区分：
- Citation-ID validity：引用编号是否存在于当前已检索来源。
- Provenance：编号是否能落回真实文件/页码/Chunk。
- Faithfulness / Groundedness：每个事实是否确实由对应证据支持。
- Answer Correctness：回答是否符合真实问题答案。

本项目实证验证前两类中的有限范围，不能声称已经证明完整语义忠实性。

### 11.4 M7b：Agent 评测指标

真实代码：`eval/agent_eval.py`、`eval/datasets/m7b_agent.json`、`scripts/check_m7b.py`。

| 指标 | 代码里的可操作定义 | 怎么理解 |
|---|---|---|
| Task Success Rate | 状态、明确字面片段、实体字段值、来源/页码、步数均符合固定 Gold | 一次确定性合成任务是否达成 |
| Tool Selection Accuracy | 执行工具的**集合**完全匹配预期，重复无效 | 工具选没选对，不评分调用顺序 |
| MCP Tool Selection Accuracy | MCP 名称序列与预期完全匹配 | 区别 `mcp_find_clause` 与协议内 `find_clause` |
| Tool Success Rate | `tool_events` 中状态 `ok` 的次数 / 实际工具调用数 | 运行结果，不等于任务正确性 |
| Average Agent Steps | 有效响应的 `steps` 平均值 | 成本/复杂度粗指标 |
| Failure Rate | HTTP/传输失败或明确 `partial/tool_unavailable/step_limit` 等状态占比 | **不一定等于** `1-Task Success Rate` |

结果：7 个合成案例任务成功率 100%、工具选择准确率 100%，共 8 次工具成功调用、平均 1.142857 步、故障率 0。**这些是 7 个结构化合成任务**，不代表任意复杂法律任务上的 Agent 泛化成功率。

### 11.5 M7c：性能测量要会看“单位与边界”

`eval/system_eval.py` 分开记录：
- 四次**串行** Agent HTTP E2E 延迟；
- 现有 read-only 工具事件耗时与覆盖率；
- 单独直接调用的 `hybrid_search` 延迟和 `rerank_hits` 延迟；
- 可选的一次真实 Qwen RAG Probe 的模型调用和 Token 使用。

M7c BASE / LIVE 分别观察到：
- Dense/BM25/RRF 独立检索约 **487.94 ms / 418.70 ms**；
- BGE CPU Rerank 独立耗时 **259,297.50 ms / 171,971.24 ms**；
- LIVE 额外一次 Qwen/RAG Probe 耗时 **39,578.30 ms**，Qwen 1 次调用、241 Prompt Tokens、16 Completion Tokens。

**不能把不同请求、不同缓存状态下的这些数字直接相加得到一个 Agent HTTP 请求时延**；也不能用四个串行样本推断 P95 生产吞吐。样本太少，p95 还使用 nearest-rank 方法。

### 11.6 如何设计更强的真实评测（尚未实现）

扩展方向可包括：
- 独立、冻结的测试集合和真实合同文档，明确去重与数据分区。
- Chunk 级 Recall、nDCG、MRR、Answer Exactness、完整引用事实校验。
- 可重复的模型/阈值/批大小/缓存/硬件记录。
- 复杂跨页、长合同、模糊意图、缺失证据、拒答与越权请求。
- 多轮记忆被污染时的负面案例，以及并发冲突/灾难恢复测试。

在面试中可以说“下一步设计”，**不要说已经完成了这些大规模实验**。

<a id="ch12"></a>
## 12｜M8：Trace、Prometheus 与系统级调试

### 12.1 日志、Trace 和 Metrics 的区别

| 类型 | 例子 | 适合回答 |
|---|---|---|
| Log | API 错误、容器启动、异常类型 | 某个具体事件发生了什么 |
| Trace | `trace_id` 关联请求、节点、工具、耗时、LLM Calls | 这一次请求**在哪一步失败/慢** |
| Metric | Prometheus Counter、Histogram | 一段时间总体请求量、成功率/失败率、延迟趋势 |

本项目不是 OpenTelemetry 跨服务全链路 Trace：`app/observability/tracing.py` 使用 Python `contextvars` 在请求上下文中记录 LangGraph 节点与模型调用元信息，最终经 `storage.py` 写入 PostgreSQL `agent_traces`。

### 12.2 三个容易混淆的 UUID

- `session_id`：一段会话的标识，关联 Redis 和 PG 图 Checkpoint；
- `request_id`：这一次 HTTP 处理的请求 ID；
- `trace_id`：M8 用于追踪该次请求对应节点和工具事件的 ID。

同一 Session 的下一轮会有新请求/Trace；HITL pending 请求和之后 approval resume 请求也有各自的追踪 ID。不要把 Trace 当作用户身份认证或 Session 凭证。

### 12.3 Trace 里记录什么、不记录什么？

`app/observability/tracing.py` 的 `observed_endpoint` 包装 chat/approval；`observed_graph_node` 包装 `route/decide/call_tool/synthesize`。每个节点记录起止时间、持续时间、状态、允许的工具名、LLM 调用和可用 Token。

PG `agent_traces` 还包含 `tool_names`、`tool_events`、总 `llm_calls`、Prompt/Completion Tokens 与异常**类别**。它**不持久化原始用户提问、证据全文、LLM 回答或凭据**，且没有对外提供无认证的 Trace 读取 API。

Token Usage 由 OpenAI 兼容服务报告时才记录；如果没报告，应是 `NULL`，不能瞎填 0。注意不调用 LLM 的规则/MCP 请求真实 `llm_calls=0`。

### 12.4 学会一条最有价值的 SQL

读取最近几次 Agent Trace 的健康与性能信息：

~~~cmd
docker compose exec -T postgres psql -U docmind -d docmind -c "SELECT status, llm_calls, ROUND(duration_ms::numeric) AS request_ms, tool_names, tool_events FROM agent_traces ORDER BY created_at DESC LIMIT 3;"
~~~

这是**只读查询**，在当前 Demo 默认数据库账号下可使用；如果你的本地 `.env` 自定义了数据库账号，需相应替换。

查询某一次调用失败的原因（`tool_events` 是 JSONB 数组）：

~~~sql
SELECT status,
       llm_calls,
       tool_events->0->>'error_type' AS error_type,
       tool_events->0->>'attempts' AS attempts,
       tool_events->0->>'timeout_seconds' AS timeout_s,
       tool_events->0->>'duration_ms' AS tool_ms
FROM agent_traces
WHERE operation = 'chat' AND tool_names ? 'search_documents'
ORDER BY created_at DESC
LIMIT 1;
~~~

**真实故障复盘**：曾出现 `status=tool_unavailable`、`TimeoutError`、`attempts=3`、`timeout_s=90`、`tool_ms≈270300`，以及 `llm_calls=0`。这直接证明失败发生在进入 Qwen 之前的工具路径；结合 M7c CPU 重排耗时，能够定位到 Reranker/超时机制。最终 M9 LIVE 修复后已成功通过。

### 12.5 Prometheus 指标从哪里来？

`GET /metrics` 由 `app/main.py` 暴露；具体 Counter/Histogram 定义在 `app/observability/metrics.py`。

重点指标：
- `agent_requests_total / agent_success_total / agent_failures_total`；
- `agent_steps`、`agent_e2e_latency_seconds`；
- `tool_calls_total / tool_failures_total / tool_latency_seconds`；
- `retrieval_latency_seconds / rerank_latency_seconds / rag_latency_seconds`；
- `llm_calls_total / llm_failures_total`，Prompt/Completion Tokens；
- `agent_trace_store_failures_total`（追踪写库失败）。

**Prometheus Counter** 单调累加，通常分析 `rate`；**Histogram** 将观测值放入各 `_bucket`，可估算 p95。请求 ID、原始文本等高基数字段不能当 Metric Label，否则指标序列会暴涨。当前标签只使用受控的 `operation`、工具名。

### 12.6 为什么 M8 已通过、Grafana 还不能说完成？

真实 API `/metrics`、PG Trace 跨 API Restart 的持久化已通过。可选的 Prometheus/Grafana 在 `compose.observability.yaml` 独立启动；用户最近一次拉取监控镜像时出现 `unexpected EOF`，未见实际 Dashboard/Prometheus Target UP 的完整验收日志。

因此准确说法是：“应用内可观测性与 Trace 已实现并验收，Grafana 配置已提交但尚未独立在本地验证。”**不要把 Dashboard 未启动说成 Agent 主流程没有完成，也不要声称看板已上线。**

<a id="ch13"></a>
## 13｜M9：真实合成 Demo、已验收范围与非目标

### 13.1 M9 BASE 实际做了什么？

`scripts/check_m9.py` 用真实 HTTP/容器服务依次完成：
1. 上传并索引一个 TXT、一份双页 PDF、一份 DOCX 合成合同；
2. LangGraph → MCP 两工具 `get_document` + `find_clause`；
3. 正则抽取甲乙方/付款期限，并验证引用；
4. 读取 PDF 第 2 页且校验页码为 2；
5. DOCX 条款匹配与来源；
6. Redis 多轮追问、PG Checkpoint，以及长期偏好跨会话召回；
7. HITL pending → approve → 持久写一次 → 同决策幂等 → 反向决策 409；
8. 检查 Prometheus/PG Trace。

脚本 `base_case_count=7` 是它记录的七个业务阶段结果；无需把上面所有子断言误说成“已覆盖所有业务场景”。

### 13.2 M9 LIVE 实际做了什么？

复用 BASE 的合成合同，`POST /v1/chat` 提问付款期限，实际执行：
- 规则路由 `search_documents`；
- Dense + BM25 + RRF、CPU BGE 重排；
- 调用真实 Qwen API；
- 检查答案中出现预期付款期限、有效的文档范围引用；
- 在 PostgreSQL Trace 核实实际 LLM 调用。

最终观察到 `status=answered`、`source_count=1`、`tools_called=["search_documents"]`，并打印 `M9 DEMO LIVE PASS`。这**不表示**完成真实语料的通用质量评测、所有工具覆盖或独立 Grafana 验收。

### 13.3 当前两个独立待办

1. **Grafana 可选监控**：镜像拉取出现 unexpected EOF，未有看板可访问和 Prometheus Target UP 的本地记录。
2. **新镜像的可复现构建**：Docker Hub 镜像源/代理 DNS 失败导致最新修复未能完成干净镜像重建，M9 LIVE 使用过临时复制源码到旧容器的方式通过功能验收。

这些是发布与环境收尾问题，不推翻已观察到的功能结果。暂时只学项目，完全没有必要在每章都重新构建镜像。

### 13.4 与“真正生产级 Agent”的差距

本项目**没有**：
- 已上线的完整 Web UI / 多租户登录鉴权 / RBAC；
- Kubernetes、分布式服务治理或高并发压测；
- 任意受保护写操作的完整事务保障；
- OCR、多模态图片/复杂表格文档全面理解；
- 泛化法律信息抽取或语义事实正确率的真实基准；
- “不限工具、无限步、任意网站浏览”的自主 Agent。

准确的岗位描述是：**一个有真实状态、工具协议、证据引用和审批恢复机制的本地文档知识 Agent 工程项目**。

<a id="ch14"></a>
## 14｜建议亲手追踪的四条完整调用链

请打开编辑器，按下面箭头逐个进入函数，在纸上写输入输出。每条建议用一页纸画出调用树，而不是运行耗时的推理。

### 调用链 A：文档上传并索引

~~~text
app/api/documents.py::upload_document
  -> safe_filename -> parse_document
  -> _write_document
  -> app/storage/postgres.py::add_document

app/api/documents.py::index_document
  -> claim_indexing
  -> parse_document
  -> app/rag/chunker.py::chunk_document
  -> app/rag/embedder.py::embed_texts
  -> app/storage/qdrant.py::store_document_vectors
  -> finish_indexing
~~~

观察：为什么`claim_indexing` 用数据库状态获取索引处理权？为什么 Qdrant Point ID 是 Chunk ID？

### 调用链 B：一个真实 Qwen RAG 问题

~~~text
app/api/chat.py::chat
 -> graph.ainvoke
 -> route_node -> app/agent/router.py::plan_tools
 -> decide_node -> call_tool_node
 -> app/agent/reliability.py::execute_read_only_tool
 -> app/tools/registry.py::invoke_tool("search_documents")
 -> app/tools/retrieval.py::search_documents
 -> app/rag/pipeline.py::answer_document_question
    -> app/rag/retriever.py::hybrid_search
       -> app/rag/embedder.py::embed_texts
       -> app/rag/sparse.py::bm25_rank
       -> app/rag/fusion.py::reciprocal_rank_fusion
    -> app/rag/reranker.py::rerank_hits
    -> app/rag/citation.py::build_sources / format_evidence
    -> app/llm/client.py::complete_chat
    -> app/rag/citation.py::validate_answer_citations
 -> synthesize_node
 -> Redis Session append_turn
 -> PG Trace persist_trace
~~~

观察：每一层的 `status` 和返回类型是什么？`llm_calls` 为什么可能是 0？

### 调用链 C：MCP 查询违约条款

~~~text
chat -> plan_tools（发现 query 中包含 MCP/条款/查找）
 -> call_tool_node("mcp_find_clause")
 -> invoke_tool -> tools/mcp_bridge.py::mcp_find_clause
 -> mcp_client/adapter.py::call_document_mcp("find_clause")
 -> stdio_client 启动 python -m mcp_server.server
 -> initialize -> tools/list -> tools/call
 -> mcp_server/server.py::find_clause
 -> mcp_server/document_tools.py::find_document_clause
 -> app/tools/document.py::load_document_chunks（Qdrant）
 -> bridge._result_with_evidence（校验真实来源）
 -> synthesize_node（重编号）
~~~

观察：MCP 名称 `find_clause` 与 Agent 工具名 `mcp_find_clause` 的关系是什么？是否经过 Qwen？

### 调用链 D：人工批准一条审核备注

~~~text
app/api/chat.py::chat
 -> approvals/policy.py::is_review_note_command / parse_review_note
 -> approvals/storage.py::create_approval（PG pending）
 -> graph.ainvoke -> call_tool_node
 -> nodes.py::_resume_protected_review_note
 -> LangGraph interrupt（PG Checkpoint 持久化）
 -> ChatResponse(status=approval_required, approval_id=...)

app/api/approvals.py::decide_review_note
 -> get_approval / graph.aget_state
 -> decide_approval（PG 状态先标 approved）
 -> Command(resume=...)
 -> nodes.py::_resume_protected_review_note
 -> execute_approved_review_note（PG 事务、唯一约束）
 -> 结果 status=approved + review_note_id
~~~

观察：为什么审批之前必须停在 Tool Node？数据库唯一约束在哪里？重复批准为何不重复插入？

<a id="ch15"></a>
## 15｜动手练习：从“看懂”到“真的能讲”

按难度递增，**不要求你现在扩展项目或修改业务代码**。

### Level 1：只读源码练习（零模型成本）

- **E01**：画 M0–M9 的模块框图并标记 PostgreSQL/Redis/Qdrant/LLM 职责。
- **E02**：打开 `app/agent/router.py`，对 6 种 Query 人工预测工具列表，再对照 `select_tool_plan`。
- **E03**：追踪从 `index_document` 到 `build_points` 的一个 `document_id`，写出 Chunk Payload 至少 8 个字段。
- **E04**：用纸笔演算第 06 章 A/B/C 三个 Chunk 的 RRF 排序。
- **E05**：在 `app/rag/pipeline.py` 标注所有会调用网络服务的行与只做本地 Python 计算的行。
- **E06**：从 `_initial_state` 说明哪些字段每轮清零、哪些在 Checkpoint Thread 中保留。
- **E07**：说明用户偏好保存为什么需要双写 PG/Qdrant，哪个为事实来源。
- **E08**：找出 `review_notes.approval_id UNIQUE` 所在 migration。
- **E09**：找出所有包含 `tools_called`、`mcp_tools_called`、`retry_count` 的输出构造处。
- **E10**：列举 4 种 Agent `status` 并解释每个状态的用户含义。

### Level 2：已有单元测试练习（无需 Docker 模型）

阅读 `tests/unit/` 下：
- `test_m2a_retrieval.py`：中文 BM25/RRF、过滤逻辑。
- `test_m2b_citation.py` 与 `test_m2b_pipeline.py`：未知来源编号拒绝。
- `test_m3b_agent.py`：多工具排序与引用合并。
- `test_m4a_memory.py`、`test_m4b_memory.py`：短追问和长期偏好。
- `test_m5b_mcp_agent.py`：MCP Client/Agent Adapter。
- `test_m6a_reliability.py`、`test_m6b_hitl.py`：失败处理和审批。
- `test_m9_live_timeout.py`：单次 CPU RAG 推理/超时回归。

练习方法：对每个测试回答“它防止什么 Bug？如果删除这个断言会有什么风险？”不要仅靠 `pytest` 显示 Passed 就认为理解了。

### Level 3：使用**已有**本地数据只读诊断

以下不会请求 Qwen 或重建镜像：

~~~cmd
cd /d E:\project\DocMind-Agent
docker compose ps
curl --noproxy "*" http://127.0.0.1:8090/health
curl --noproxy "*" http://127.0.0.1:8090/metrics
docker compose exec -T postgres psql -U docmind -d docmind -c "SELECT status, llm_calls, ROUND(duration_ms::numeric) AS ms, tool_names FROM agent_traces ORDER BY created_at DESC LIMIT 5;"
~~~

自测目标：从一次 Trace 判断是规则/MCP 请求还是 RAG/Qwen 请求，注意请求、工具、Rerank 与模型调用的区别。如果环境没有运行，**完全可以只读已归档的 M7/M8/M9 验收文档**，没有必要重新启动所有容器。

### Level 4：受控代码阅读/小改动建议（不要求立即实现）

如果未来打算真正动手，可先在自己本地分支做纯函数层面实验：
1. 为 `select_tool_plan` 增加一条新 Query 的**测试**，而非直接加新业务工具。
2. 对 `lexical_tokens` 的中文双字匹配写 5 个边界案例。
3. 构造一个 `[S99]` 的模型回答，验证为什么 `citation_unverified`。
4. 构造失败的 MCP 来源对象，观察 Bridge 为什么必须抛错。
5. 用 Mock 模拟 `TimeoutError`，确认普通工具与 CPU RAG 策略不同。

**不要为练习提交“提升真实业务准确率 X%”的宣传，除非有新数据与重复实验。**



<a id="ch16"></a>
## 16｜Agent / RAG 工程岗位高频面试问题与回答

**建议训练方法**：先不看答案，口述 60–90 秒；再核对是否包含：①一句话定义，②本项目真实实现，③为什么这么设计，④实际局限，⑤验证证据。以下答案不是要背诵的统一话术，而是可以追溯到源码的示范。

### A. Agent 设计、LangGraph 和工具机制

**Q01. 你怎么定义 Agent？这个项目为什么算 Agent，而不只是 RAG？**  
**答**：Agent 是能在当前任务和状态下选择、执行、观察工具能力并决定下一步的软件系统；LLM 不一定负责所有决策。DocMind-Agent 的 LangGraph 使用 `route → decide → call_tool → decide → synthesize` 的有限工具图，持有显式 State，支持多个不同工具、MCP、Redis/Checkpoint 和审批中断。单独的 `answer_document_question` 才是固定 RAG 子流程。它是**受控工具型 Agent**，不是开放式通用自主 Agent。

**Q02. LangChain 和 LangGraph 的角色分别是什么？**  
**答**：概念上 LangChain 常提供模型、Prompt、文档、工具等组合抽象；LangGraph 更侧重显式状态图、条件边、循环、持久化和恢复。本项目主要直接使用 `langgraph.graph.StateGraph` 和官方 PostgreSQL Checkpointer，节点内复用普通 Python 工具函数，不能说自己实现了整个 LangChain 生态能力。

**Q03. 你的 LangGraph 有哪些节点？状态怎么流转？**  
**答**：`graph.py` 注册 `route`、`decide`、`call_tool`、`synthesize`；条件边由 `next_edge` 决定是否继续调用工具。每个节点读取 `AgentState`，返回需要更新的字段字典，LangGraph 合并状态。默认计划完成或达到 8 步上限时进入合成，避免无限循环。

**Q04. Agent State 里为什么同时有 plan、current_step、tool_results？**  
**答**：`plan` 规定待执行的工具序列，`current_step` 表示执行到哪一个工具节点，`tool_results` 存对应结果。分开存可以允许多个工具依次执行、最终合并及断点恢复；如果只用一段自由文本历史，程序难以可靠校验已做的动作和剩余预算。

**Q05. ReAct 与 Plan-and-Execute 有何区别？你的项目属于哪种？**  
**答**：ReAct 的典型形式是反复“推理 → 行动 → 观察 → 再推理”；Plan-and-Execute 则先形成计划再逐步执行。本项目更接近**有限的计划执行 + 状态图**：规则优先建立必要工具计划，部分复杂任务允许模型只调整工具顺序，`decide_node` 按计划执行，不是每步让模型自由发明新工具。

**Q06. 哪些请求需要 LLM Planner？**  
**答**：`app/agent/router.py::plan_tools` 先用 `select_tool_plan` 得到必要工具。只有“至少 2 个必要工具、包含抽取或摘要、同时有 document_id”才尝试 Qwen 排序；元数据查询、MCP 查询以及单工具问答通常直接走规则。RAG 问答的**生成调用**与工具**规划调用**是两种不同的模型使用场景。

**Q07. 如何避免模型幻觉式地调用不存在的工具？**  
**答**：模型输出的工具计划必须是符合格式的 JSON，集合必须与规则确定的必要工具集合相同，不能重复、越过白名单或超过 4 个。执行前还有 `registry.py` 的 Pydantic 参数验证。非法计划触发 `rule_fallback`，记录失败原因，而不是根据模型自由文本 `eval()` 或调用任意 Python 函数。

**Q08. 为什么不所有决策都交给 LLM？**  
**答**：简单意图（文档元数据、明确页码、明确关键词、显式保存偏好）可以由规则确定。这样成本低、延迟可控、可回归测试，尤其是写操作不会因模型猜测自动触发。代价是灵活性有限；面试中应承认词面 Router 对复杂自然语言的泛化不足。

**Q09. 一个工具应包含哪些契约？**  
**答**：至少要有名称、参数 Schema、执行副作用或只读属性、正常返回结构、来源元数据、错误状态与超时预算。本项目的 `invoke_tool` 对输入进行 Pydantic `model_validate`；调用在 `reliability.py` 中记录 attempts、duration、error_type。可信的工具不是“模型说成功就成功”。

**Q10. 你的 Agent 最多执行几步？和 Retry 次数一样吗？**  
**答**：图的 `MAX_AGENT_TOOL_STEPS=8`，`current_step` 每执行一个工具节点加 1。普通只读工具可在这个节点内部临时重试至多 2 次，并增加 `retry_count`，不会额外占用图步骤。CPU RAG 工具改为零重试。另有 LangGraph `recursion_limit=30`，与业务层 8 步限制不同。

**Q11. Tool Calling 是模型 API 功能还是 Agent 的工程设计？**  
**答**：模型厂商可能提供函数/工具调用格式，但完整工程仍需工具注册、参数校验、执行、失败处理与结果拼接。此项目没有盲目开放任意函数，而是自己定义 Schema 与调用表；模型规划更严格，只能在必要工具范围内调整顺序。面试应重点讲受控执行而非只讲“支持 function calling”。

**Q12. 多工具结果为什么要重新编号引用？**  
**答**：两个独立工具都可能返回本地 `[S1]`，但分别对应不同 Chunk。直接拼接会使来源 ID 二义。源码 `app/agent/nodes.py::_relabel_tool_result` 为每个工具建立 old→new Source ID 映射，统一生成最终 Answer 级的编号，同时更新实体字段中的 `source_id`，并标记未知引用。

**Q13. 什么是 Planner Fallback？为什么不直接报错？**  
**答**：当用于排序的 Qwen 调用失败、返回非法 JSON 或违反工具集合约束时，代码保留规则计划并标记 `plan_source="rule_fallback"`。这样不因“辅助排序”失败而让整个确定性业务流程失效。但如果后续 RAG 生成服务本身不可用，依然可能 `tool_unavailable`，不能把 Planner 回退当成所有模型故障的万能恢复。

**Q14. 你如何测试路由/节点而不运行大型模型？**  
**答**：把逻辑集中在可调用纯函数/节点函数，例如 `select_tool_plan`、`next_edge`、`_relabel_tool_result`，配合单元测试构造 State、Fake 工具返回和不合规模型计划。只有验证真正服务集成时才调用 Docker/Qwen。对应 `tests/unit/test_m3a_agent.py`、`test_m3b_agent.py`。

### B. RAG、Embedding、混合检索与回答可信度

**Q15. RAG 的基本流程和核心价值是什么？**  
**答**：先按问题检索文档证据，再把证据和问题交给模型回答。本项目把检索结果的真实 Chunk/PDF 页码编号为 `S1/S2`，然后由 Qwen 生成带引用的回答。核心价值是减少纯模型记忆依赖、降低上下文负担并提供出处；代价是性能和答案质量高度依赖检索质量。

**Q16. Embedding 和 Reranker 的区别是什么？**  
**答**：Embedding（Dual Encoder 思路）可分别编码 Query 与文档，便于建立 Qdrant 向量索引并快速搜索；Cross-Encoder Reranker 对每个 Query-Chunk 对进行更精细的相关性计算。DocMind 用 512 维 BGE 小模型 Embedding、BGE Reranker ONNX CPU 重排，重排效果可能更精细但很慢。

**Q17. 为什么中文 BM25 使用字符 bigram？**  
**答**：中文缺少显式空格词边界，若引入分词器会额外带来词典和分词错误依赖。源码将连续汉字序列切成重叠的双字片段，英文和数字按 token 处理，提供一个可复现的词面检索基线。局限是片段可能不对应真实词，无法理解同义词、上下文角色或长距离语义。

**Q18. BM25 的 k1、b 有什么作用？**  
**答**：k1 控制词频饱和程度，b 控制文档长度归一化；该项目分别是 1.5 和 0.75。BM25 不只是计算“是否包含关键词”，它还考虑查询词在 Chunk 中出现的频率、词在语料中的稀有程度和 Chunk 长度。

**Q19. 为什么要用 RRF，不直接相加 Dense 与 BM25 分数？**  
**答**：不同检索器分数不可直接比较，RRF 把原始分数转换为排名贡献，按 `1/(60+rank)` 累加，简单稳健且便于复现。但它不能保证最优融合权重，也不会解决两个分支共同漏召的问题。

**Q20. 向量召回 Top-K 和 Rerank Top-K 各是什么意思？**  
**答**：先由 Dense/BM25 获得候选、RRF 排序，再把有限个候选交给 Cross-Encoder。本项目正常 RAG 的 RRF 输出候选默认 8 个，重排后的最终证据 2 个、每条给 LLM 的长度最多 160 字符。召回预算与最终证据预算要分开调，过小的前者可能漏召、过大的后者会增大 CPU 计算与 Prompt 成本。

**Q21. Chunk Size/Overlap 怎么影响检索？**  
**答**：Chunk 太小容易缺少句子/条款上下文；太大则降低检索精度、占用上下文并增加重排成本。Overlap 能减少边界信息被切断的风险，但会生成重复证据。该项目默认 400 字符与 60 重叠，按 PDF 页分 Block，仍不保证处理所有跨页/跨表关联。

**Q22. 为什么 PDF 页码可信、DOCX 页码为空？**  
**答**：PDF 页面可以由 PyMuPDF 明确枚举；DOCX 页码受布局、字体、分页渲染环境影响，仅解析 XML 文本无法可靠重建物理页。保留 `page=None` 是拒绝伪造来源的策略，实际可用章节标题 `section` 补足。

**Q23. 项目支持 OCR 或复杂表格吗？**  
**答**：不支持 OCR 扫描件。DOCX 表格做了有限文本行解析，但没有多模态表格结构理解。拿扫描图片 PDF 测试时会在 Parser 层出现无可提取文本，不能把这种错误归因于 Qwen；面试里要明确边界。

**Q24. 什么是 Prompt Injection？你的项目如何应对？**  
**答**：来自文档等低信任来源的文本试图冒充系统指令，引导模型偏离任务或泄露信息。代码明确将检索片段标记为不可信，只允许根据证据答题，并把输出来源编号限制为程序提供的范围。这是一个约束层，不代表已通过完整的对抗注入测试或有完备的隔离策略。

**Q25. Citation Accuracy 和 Faithfulness 是一回事吗？**  
**答**：不是。已实现的检查重点是模型引用了存在的 `S1/S2` 以及来源确实来自原 Chunk；不验证“答案中的每一个事实一定被该 Chunk 支持”。如果证据写“30 天”、回答写“90 天 [S1]”，编号存在也可能过关。需要额外的蕴含/事实一致性评测。

**Q26. 如果检索到了不相关证据，模型一定会正确拒答吗？**  
**答**：代码的 Prompt 要求证据不足时明确拒答，识别特定的标准拒答句型可返回 `insufficient_evidence`。但这是有限的规则检测，不保证所有自然语言变体都能正确区分，也不能保证模型不会在合法编号下胡编。应强调系统做了约束而非彻底杜绝幻觉。

**Q27. 为什么“只生成摘要”也需要来源引用？**  
**答**：一段摘要可能包含主体、期限、义务、风险等多个事实；没有来源，用户无法定位是否真实存在。DocMind 的 `summarize_document` 只总结检索到的证据，并在返回中标明 `retrieved_evidence_only`，不假装覆盖整个大合同。

**Q28. 为什么目前没有真正的 Query Rewrite？**  
**答**：`normalize_question` 只整理空白，Session 的 `resolve_followup` 对短追问做保守规则拼接。这可以降低外部 LLM 调用和错误改写风险，但复杂代词、多跳查询仍是空缺。不能因为需求图中写了 Rewrite 就声称完成了基于模型的查询重写。

### C. MCP、Memory、HITL 与系统安全

**Q29. MCP 是什么，它与 Tool Calling 的区别？**  
**答**：Tool Calling 是 Agent 决定需要调用某个能力的概念或模型接口；MCP 进一步规范外部工具如何声明、发现和被调用。本项目用官方 FastMCP 暴露四个只读工具，Agent 经 ClientSession 的 JSON-RPC stdio 生命周期调用，不是直接 import Server 函数；但不能因此声称支持所有 MCP Transport/远程 SaaS。

**Q30. 为什么采用 stdio MCP 而不是 HTTP MCP？**  
**答**：这是本地学习项目，stdio 不需要开放额外网络端口，子进程生命周期更明确，易于验证 `initialize/tools/list/tools/call`。代价是每次调用启动进程会有额外开销，不适合直接作为高并发的远程共享服务设计。

**Q31. MCP Server 出错，Agent 如何避免产生虚假答案？**  
**答**：Adapter 检查 `isError`、结构化输出类型、JSON，Bridge 再检查 `document_id`、`chunk_id`、`filename` 和页码范围；异常不悄悄换成另一个本地 Python 实现伪装成功。外层可靠性执行器对可重试暂时错误降级，最终返回明确状态而不捏造引用。

**Q32. Session Memory 和 Long-term Memory 的区别？**  
**答**：Session 是 Redis 的近期对话和文档上下文，最多 6 轮、空闲 TTL 1 小时；长期记忆是用户明确要求保存的合同输出格式，PG 作权威数据、Qdrant 做语义召回。长期记忆不是将所有对话自动向量化，主要为避免隐私污染和错误长期化。

**Q33. Working Memory、Checkpoint、Redis Session 怎么区分？**  
**答**：Working Memory 是当轮的 `AgentState`；Checkpoint 是官方 PG Saver 保存执行到哪一个节点的状态；Redis Session 只保存最近问答和可恢复的文档上下文。用户问“如果逾期呢”，Session 可帮助解释“哪份合同”；用户暂停写入后重启恢复，则依赖 Checkpoint。

**Q34. 记忆为什么需要白名单和用户过滤？**  
**答**：如果随意保存工具输出、合同全文或模型猜测，后续调用可能跨会话重复利用错误事实和敏感数据。项目只保存五类明确的格式字段，Qdrant 检索时按 `user_id` 过滤并用 PG 再次确认。注意调用方指定 UUID 不等于真实鉴权，因此多用户安全仍未完成。

**Q35. 什么是 LangGraph Checkpointer？这个项目在哪里初始化？**  
**答**：它持久化图执行快照，使中断后可以沿同一 `thread_id` 恢复。项目在 `app/memory/checkpoint.py::open_checkpointer` 使用官方 `AsyncPostgresSaver`、启动时 `setup()`，然后通过 `app/main.py` 把 Saver 传给 `build_agent_graph`。

**Q36. HITL 为什么不是简单让模型问一句“你确定吗”？**  
**答**：模型在 Prompt 中请求确认仍可能因控制流错误提前写入；真正的 HITL 必须在工具执行前建立程序级硬门禁。当前代码持久写 PG pending、通过 `interrupt()` 暂停图，再由独立审批端点决定是否恢复，用户拒绝时无插入，批准时才允许事务写入。

**Q37. 幂等性是什么意思？你是怎么保证的？**  
**答**：相同的合法审批请求重复到达不产生额外写入。本项目 `review_notes.approval_id` 唯一、`review_note_id` 根据 approval ID 稳定生成，PG 事务与 `ON CONFLICT DO NOTHING` 避免重复记录。适用范围只涵盖当前 PostgreSQL review-note 写操作，不是对任意外部服务的 exactly-once 保证。

**Q38. Redis Session Lock 为什么不等于完整并发安全？**  
**答**：当前同一 Session 用 Redis `SET NX EX` 的 300s 锁防重入，解锁使用 compare-and-delete。然而 CPU RAG 的最长等待预算可到 420s，锁可能提前到期；需要续租、任务队列或一致性设计才能在高并发下加强约束。面试主动指出这个边界比声称“无并发问题”更可信。

**Q39. 用户和 Session UUID 能当鉴权吗？**  
**答**：不能，它们由调用方传入，是本地 Demo 的业务作用域标识。生产中应通过登录认证映射真实用户身份，再按文档权限校验可访问范围，同时限制 Trace 和长期偏好查询、保护审批接口。若 API 直接暴露公网会有越权风险。

**Q40. 为什么写工具不放到普通 Tool Registry？**  
**答**：普通 `invoke_tool` 面向只读能力，允许有界瞬态重试；写操作需要审批、持久事务与幂等协议。项目把 `save_review_note` 特殊放在 LangGraph 中断/恢复节点，避免模型或可靠性自动重试器绕过人工决策。

### D. Eval、性能、观测和工程排障

**Q41. Recall@K 和 MRR@K 的区别？**  
**答**：Recall@K 看 Top-K 覆盖了多少 gold 相关文档；MRR@K 关注最早出现的相关文档位置。例如 gold 两篇，Top-3 只有第 2 位一篇，则 Recall@3=0.5，RR@3=0.5。DocMind M7a 用的是 Document ID 去重排序，三条合成查询结果都为 1.0。

**Q42. Tool Selection Accuracy 与 Task Success Rate 有什么不同？**  
**答**：前者检查调用的工具集合是否符合预期，后者还需要状态、预期文本/实体、来源范围与步数满足固定 Gold。工具选对可能提取错事实，任务正确也可能碰巧通过非预期工具。本项目将这两个指标分开，而不是把“调用成功”当作“任务成功”。

**Q43. M7b 100% 结果可以写成真实法律任务成功率 100% 吗？**  
**答**：不可以。7 个合成案例被设计为可确定性核验的规则/MCP 工具任务，样本量极小，未覆盖真实长合同、真实复杂规划、证据冲突或语义判断。只能写“在 7 个合成任务的本地回归测试中 7/7 通过”，并说明是工程流程烟雾测试。

**Q44. P50/P95 是什么？怎么避免样本量误导？**  
**答**：P50 是延迟中位数，P95 是有 95% 观测值不高于该值的分位数；M7c 仅四个串行 HTTP 样本，其 nearest-rank p95 对最高值很敏感。不能把四个样本的 p95 当生产 SLA，也不能将不同环境的独立阶段耗时相加。

**Q45. 你的项目最大的性能瓶颈在哪？**  
**答**：本机 M7c 的 BGE CPU Rerank 两次单独计时约 172–259 秒，而独立的 Dense/BM25/RRF 检索约 0.42–0.49 秒。现阶段重点瓶颈是 ONNX CPU Cross-Encoder 推理，而非 Qdrant 数据库本身。这还没有压测或优化收益量化，不能声称优化后已达到某个 QPS。

**Q46. M9 LIVE 为何出现 270 秒工具超时，但 `llm_calls=0`？**  
**答**：原策略对 `search_documents` 每次限 90 秒，最多执行 3 次。重排 CPU 工作时间超过限额，导致 RAG 工具在调用 Qwen 之前就超时。SQL Trace 实测 `TimeoutError`、`attempts=3`、`timeout_s=90`、`tool_ms≈270300`、`llm_calls=0`，所以不是“模型生成太慢”。

**Q47. 为什么后来对 CPU RAG 改成 420 秒、0 次 Retry？**  
**答**：在 `asyncio.to_thread` 中的 ONNX 线程不能简单依靠协程超时取消；重复尝试可能启动多个仍在计算的线程。新策略给完整检索+重排+LLM 一次有界预算，失败后输出无证据 fallback，不自动再跑 CPU 推理；其他 I/O 工具仍保留最多 2 次重试。420 是预算上限而非固定睡眠时间。

**Q48. HTTP 200 但 `tool_unavailable` 如何理解？**  
**答**：FastAPI 成功序列化了 Agent 的失败安全响应，所以 HTTP 是 200；业务结果明确是工具不可用，`sources=[]`。监控要同时看 HTTP 层、Agent 状态、`tool_events` 和 Trace，否则会误把“接口存活”当作“问答成功”。

**Q49. Log、Metric、Trace 的区别？**  
**答**：Log 给离散事件与错误，Metric 给一段时间的聚合趋势，Trace 串联一次请求内的节点、工具、耗时和 Token。DocMind 用 `contextvars` + PostgreSQL `agent_traces` 保存请求元数据，并通过 `/metrics` 暴露 Prometheus；没有完整的跨进程 OpenTelemetry 采集链路。

**Q50. 为什么不把 Query、文件名、Session ID 当 Prometheus Label？**  
**答**：它们几乎每次请求都不同，会造成指标高基数爆炸、内存与查询成本升高，也泄露用户敏感信息。项目使用有限工具名与 `operation` 白名单作为标签，具体请求的 UUID/步骤在权限受控的 Trace 系统里才适合保留。当前项目还需要真正的 Trace 访问权限控制。

**Q51. Docker 构建长耗时怎么定位？**  
**答**：先看 Docker Build 哪一步慢。如果卡在 `load metadata for python:3.12-slim` 并出现 mirror/proxy DNS 超时，业务代码甚至未开始编译，不应重复改 Python。M8 已调整 Dockerfile 层次缓存第三方依赖；但代理不能解析 `http.docker.internal` 时，缓存优化也无法解决镜像源请求失败。

**Q52. `docker compose restart api` 与 `--build`、`docker compose cp` 有何区别？**  
**答**：restart 只重启当前容器；build 尝试构建新不可变镜像；cp 是把源码复制到现有容器文件系统，不更新原镜像。曾经临时 cp 后通过 `PYTHONPATH=/app python -m scripts.check_m9` 才避免导入旧 wheel，因此功能测试通过不代表正式新镜像已经可复现构建。

**Q53. `429/503/TimeoutError` 应该如何处理？**  
**答**：先区分外部 HTTP、数据库、模型还是内部工作线程故障；只有被判定为暂时性的且允许重试的只读工具才按 Policy 重试。CPU 非可取消推理禁止自动重复启动；写操作走审批幂等路径。处理策略要按副作用风险分类，不是一律 Retry 3 次。

**Q54. 如果 Qwen 服务宕机，所有 Agent 请求都会失败吗？**  
**答**：不会。规则元数据、规则抽取、MCP 文档查询等可以独立执行；完整 RAG `search_documents`、`summarize_document` 和某些复杂工具排序依赖 Qwen。Planner 失败可以用规则计划回退，但需要模型生成答案的 RAG 失败不能用凭空文本伪装成有依据的正确回答。

**Q55. 你从这个项目里最大的工程教训是什么？**  
**答**：不能只看最后一行“PASS/FAIL”，要看每层的可观察状态。这个项目从 90 秒重排超时、旧 `site-packages` 导入、Docker Hub 代理 EOF 到 Grafana 拉取中断，分别属于 CPU 推理、Python 导入路径、容器网络镜像服务问题。把数据面、控制面、依赖部署分清楚后，排障会更有方向，也能避免无意义地重建大型镜像。

**Q56. 真实大厂面试官追问“项目最创新的地方”怎么回答？**  
**答**：如果投 Agent/RAG 工程岗，不必虚构算法突破。可以强调**多层工程能力的可靠集成**：来源元数据贯通 RAG 与 MCP、受约束工具计划、Redis/PG/Qdrant 各自明确职责、带 Checkpoint 的受保护写入、失败安全和 Trace。然后承认这些都是已知成熟技术的工程组合，价值是问题拆分、约束和可验证性，而非原创大模型算法。

**Q57. 如果让你从零再做一次，会首先改什么？**  
**答**：先建立真实合成之外的稳定 benchmark 和性能基线，特别是为 CPU Cross-Encoder 选择更轻/更快的执行方式；然后补真正鉴权与文档权限、确保 Session Lock 与最长 RAG 预算一致；再把 BM25 从限定大小的 Qdrant scroll 转为可扩展的索引服务。这样做基于已经观察到的局限，而不是漫无目的增加框架。

**Q58. 如何用 60 秒介绍你在这个项目中的工作？**  
**答**：可以这样组织： “我实现了一个面向合同文本的本地可追溯 RAG Agent。上传后解析 PDF/DOCX/TXT 并保留原文位置，BGE Dense 和中文字符 BM25 经 RRF 融合，再由 BGE Cross-Encoder 重排并让 Qwen 依据少量真实证据回答。上层用 LangGraph 的显式 State/Tool Registry/MCP 协调多工具，Redis 负责短期会话、PG Checkpoint 和长期偏好支撑多轮；需要写审核备注时用 `interrupt/resume` 加人审和数据库幂等。合成测试覆盖检索、工具、审批、Trace，但还没有真实法律数据泛化或生产多租户部署。” 然后根据面试官关注点深入讲某一条源码。

### 面试回答的四个禁区

1. 不要说“所有路由都由 LLM 自动决定”——源码规则优先。
2. 不要说“使用了通用法律 NER 模型”——当前实体抽取主要是规则。
3. 不要说“Recall@3=100% 证明实际业务准确率 100%”——只是 3 个合成案例。
4. 不要说“所有工程验收包括 Grafana 和干净镜像均完成”——这两项仍无成功记录。



<a id="ch17"></a>
## 17｜工程常见问题与实际排障手册

这一章面向最容易出现的真实情况。**统一原则：先定位是哪一层失败，再做最小修复；不要遇到所有问题都执行 `docker compose up --build`。**

### 17.1 五步通用诊断法

1. **看发生在哪一步**：Docker 拉镜像？容器启动？HTTP 请求？Agent Tool？Reranker？Qwen？
2. **看两种状态**：HTTP 状态码 + Agent `status`（以及 `tool_events`）。
3. **看输入范围**：文件是否索引、`document_id` 是否正确、Session 是否继承、是否触发审批。
4. **看真实证据**：`docker compose logs`、PostgreSQL Trace、`/health`、`/metrics`、实际模型服务地址。
5. **仅修改故障层**：修改路由参数/超时、更新文件或修网络，优先不重建镜像、不删数据卷。每次修复后用最短路径验证。

### 17.2 故障速查

| 症状 | 典型原因/识别信号 | 优先处理方式 |
|---|---|---|
| `docker compose up --build` 在 `FROM python:3.12-slim` 耗很久 | Docker Hub mirror `docker.xuanyuan.me` / `http.docker.internal` 代理 DNS 超时 | 先检查 Docker Desktop 代理、镜像源和 DNS；这是**拉基础镜像前**的构建问题，不是 FastAPI 代码 |
| Grafana/Prometheus 镜像 `short read ... unexpected EOF` | 分层镜像下载被中断，当前本机曾实际发生 | 单独排查 Docker 镜像网络，别因为可选可视化失败推翻 M8 核心 Trace 验收 |
| Build 慢且安装依赖重复 | Dockerfile COPY 顺序、BuildKit 缓存被清理或 `pyproject.toml` 修改 | 确认第三方依赖层在业务源码 COPY 前；不使用 `--no-cache` 反复清理 |
| `ImportError: no pq wrapper available` | Slim 镜像缺少 Psycopg C/binary 后端 | 检查 `psycopg[binary]` 和 Docker/CI 的 `pq.__impl__ == binary` 验证；不要误删 PG 数据 |
| 上传 HTTP 201、索引 HTTP 503 | 上传成功但 Embedding/模型下载或 Qdrant 操作失败 | `docker compose logs --tail 100 api`；先区分 ModelScope/Hugging Face 网络与数据本身错误 |
| `SSL: UNEXPECTED_EOF_WHILE_READING` 在 Hugging Face 请求 | 旧版 FastEmbed 首次取 HF 元数据网络问题 | 现有 M1 已切至 ModelScope 本地 ONNX 缓存；验证实际下载源，而非看到站点首页 HTTP 200 就判断模型权重可用 |
| PDF 上传 422 无可用文本 | 扫描件只有图片或损坏 | V1 不含 OCR；换可选中文本的 PDF 或先独立 OCR，不能通过改 Qwen Prompt 解决 |
| Qdrant 维度错误 | 模型向量不是 512 维，或已存在 Collection 的配置不匹配 | 检查 `EMBEDDING_VECTOR_SIZE` 与现有 Collection；**不要随意删除整个 Qdrant 数据卷** |
| 某条查询检索为空 | 指定文档没索引、UUID 不匹配、文本无相关词/语义 | 查 `documents.status`、Qdrant Payload 与 `document_id` 过滤 |
| BM25 报扫描上限错误 | Qdrant 可扫描文本超过 `max_scan_chunks=5000` | 这是故意的容量边界；需重设计可扩展稀疏索引，不能默默忽略后半语料 |
| HTTP 200 但 `tool_unavailable` | Tool 进入安全 Fallback | 查看 `tool_events.error_type/timeout_seconds/attempts` 和 Trace 的 `llm_calls` |
| `status=no_evidence` | 正常执行，但没有相关来源 | 检查检索范围与查询，而不是重试数据库连接 |
| `citation_unverified` | 回答引用未知 `[S数字]` 或多工具引用合并错误 | 核对 Answer 中 ID 与 `sources[].id`，不能为了让测试通过而关闭验证 |
| 某个 MCP 工具 409/503 | 不一定是 MCP 本身，有可能 API Session、数据、子进程等问题 | 查是否已经到 `call_document_mcp`，再定位初始化、发现、调用或 Bridge 校验 |
| MCP 请求比直接函数慢 | 每次调用启动 stdio 子进程并初始化/发现工具 | 读取 `adapter.py`，先衡量进程/协议开销，未来可优化长驻 Session，但当前未实现 |
| 同一 Session 多个请求出现 409 | Redis Session Lock 或已暂停待审批的图 | 检查正在执行的请求/审批状态，不要随便换 Session ID 绕开写入保护 |
| 重复审批返回 409 | **相反**决策与已有数据库记录冲突 | 这是正确的防重复逻辑；同决策幂等返回已有结果 |
| 写备注接口返回 422 | 缺少 `user_id`、`document_id`、无效指令格式或备注长度 | 使用精确 `保存审核备注：内容` 与已索引文档 ID |
| RAG 三次 90s 超时、`llm_calls=0` | 旧 `search_documents` Policy 与 CPU BGE 重排耗时不匹配 | 新版 `RAG_CPU_TIMEOUT_SECONDS=420`、不重试；检查进程内锁和源码版本，而非先怀疑 Qwen |
| `Settings ... rag_cpu_timeout_seconds` 不存在 | 旧 `site-packages` 与新 `/app/app` 源码混用 | 用 `PYTHONPATH=/app python -m scripts.check_m9` 优先导入源码；确认 `config.__file__` |
| Qwen 连接报拒绝 | 本机 `llm-serving-ops` 未启动、端口错误或 Docker 容器未正确访问 Windows | 检查 `LLM_BASE_URL=http://host.docker.internal:8000/v1` 和真实服务状态 |
| `llm_calls=0` 却很慢 | 可能是检索/重排在进入模型前卡住 | 对照 `rerank_latency` 和 `tool_events`，不要用生成模型相关日志替代定位 |
| Token 计数为 NULL | OpenAI 兼容端点没有报告 usage 或一次调用异常 | 缺失值不应填成 0；看 `llm_calls` 是否大于 0 |
| Grafana 页面打不开，但 `/metrics` 可以访问 | 可选容器尚未成功拉取/启动 | M8 核心 Metric 已实现，独立检查 `compose.observability.yaml` 及镜像网络 |

### 17.3 三条无损检查命令

查看服务：

~~~cmd
docker compose ps
curl --noproxy "*" http://127.0.0.1:8090/health
~~~

查看 API 真实异常：

~~~cmd
docker compose logs --tail 100 api
~~~

查看最近的业务状态：

~~~cmd
docker compose exec -T postgres psql -U docmind -d docmind -c "SELECT status, llm_calls, ROUND(duration_ms::numeric) AS ms, tool_names FROM agent_traces ORDER BY created_at DESC LIMIT 5;"
~~~

**提醒**：涉及 SQL 和日志的例子只供本地学习。生产中不能无授权暴露文档内容、用户个人信息、数据库账户与访问端口。

### 17.4 事故分析案例：为什么不能“只加重试”？

**观测**：`tool_unavailable`、`TimeoutError`、`attempts=3`、单次 `timeout_s=90`、总工具执行约 270.30 秒、`llm_calls=0`。

**排除**：Qwen 还未开始，因此不应优先诊断 Qwen 生成质量；Qdrant HTTP 200 也不能证明后续 CPU 重排顺利完成。

**原因链**：检索 → 进入 `rerank_hits` 的 ONNX CPU 任务 → 超过 90 秒 → coroutine 被取消，但线程可能仍运行 → Retry 再启动昂贵推理 → 三次预算耗尽。

**修复**：CPU RAG 采用一个 420 秒有界调用预算、取消自动 Retry，进程内 Mutex 序列化重排；通过 M9 LIVE 真正运行 Qwen 问答与引用，最后成功。

**教训**：超时、重试、幂等、工作线程取消机制必须一并设计；“每个请求都重试两次”对非可取消的高成本工作不是安全的默认选择。

### 17.5 事故分析案例：为什么改了源码却出现旧配置 AttributeError？

**观测**：验证新可靠性代码打印 `420 0`，但 `python scripts/check_m9.py live` 中的 `Settings` 却不认识新字段。

**原因**：临时复制到容器 `/app/app` 的源码与之前安装在 `site-packages` 的 Python 包版本不同；脚本直接按路径执行时，模块查找路径可能不以 `/app` 为首。

**修复**：`docker compose exec -T -e PYTHONPATH=/app api python -m scripts.check_m9 live`，并用 `import app.core.config as c; print(c.__file__)` 验证真正读取 `/app/app/core/config.py`。这次新启动方式后来也已通过 GitHub CI 与本机 LIVE 测试。

**教训**：对于已安装的 Python 项目，运行源码路径与 wheel 版本一致性同样是工程验收的一部分。

<a id="ch18"></a>
## 18｜综合自测题与参考答案

建议先覆盖参考答案，独立用纸笔写。**能够准确说出函数名和边界，比只写定义更重要。**

| 问题 | 核心参考答案 |
|---|---|
| 1. API 的宿主机端口和 Qwen 的宿主机端口？ | API 8090；Qwen/vLLM 位于独立服务的主机 8000；API 容器内部也用 8000 监听自身 |
| 2. 一次上传返回 201 后能否立刻 RAG？ | 不一定；上传只保存元数据/原文件，还需调用 `/index` 生成 Qdrant Points |
| 3. Chunk 的四个基本来源字段？ | `document_id`、`chunk_id`、`filename`、`page/section`（另有 offset 等） |
| 4. PDF 为什么不跨页 Chunk？ | 保持真实 1-based 页码来源，不让一个片段错误归属多页 |
| 5. Embedding 维度与主要模型？ | `BAAI/bge-small-zh-v1.5`，512 维，本地 ONNX/FastEmbed CPU |
| 6. BM25 如何处理中文？ | 将连续中文字符切成重叠 bigram；正向 IDF BM25，`k1=1.5,b=0.75` |
| 7. RRF 为什么看排名？ | Dense 和 BM25 分数尺度不同，RRF 用 `1/(60+rank)` 汇总名次 |
| 8. Rerank 与 Retrieval 的模型输入差别？ | Dense 独立向量编码；Cross-Encoder 共同看 Query+Chunk |
| 9. `[S1]` 由谁分配？ | Python `build_sources`，不是由 Qwen 随机编造 |
| 10. `citation_unverified` 与 `no_evidence` 差别？ | 前者回答引用未通过校验，后者检索正常但没有可用相关来源 |
| 11. 为什么 `search_documents` 与 `mcp_search_documents` 不同？ | 前者完整重排+Qwen，后者调用 MCP Server 混合检索证据，不做模型生成 |
| 12. 图有哪些节点？ | `route`、`decide`、`call_tool`、`synthesize` |
| 13. LLM Planner 能添加任意工具吗？ | 不能，必须与规则确定的必要工具集合完全一致，最多 4 个，允许重新排序 |
| 14. `current_step=8` 时会怎样？ | `decide_node` 标记 `step_limit`，不再调用工具 |
| 15. 最近 6 轮对话存哪里？ | Redis Session，空闲 TTL 默认 3600s |
| 16. 长期偏好可以保存任意个人事实吗？ | 不行，仅明确指令下的合同输出格式白名单，PG+Qdrant |
| 17. Checkpoint 的 thread ID 是什么？ | 对应 `session_id`，由 `thread_config` 转换 |
| 18. 审批前为什么 review_notes 仍为空？ | `interrupt()` 停在执行写工具前，只有批准并恢复图后 PG 才执行插入 |
| 19. 如何防止重复审批产生重复笔记？ | PG `review_notes.approval_id` 唯一，事务与 `ON CONFLICT` 以及稳定 UUID |
| 20. 何时 HTTP 200 却算失败？ | 返回 `status=tool_unavailable` 等安全降级业务状态 |
| 21. 为什么 M9 初次 270 秒失败时 `llm_calls=0`？ | 90 秒 CPU BGE Rerank 超时、重复三次，尚未执行 Qwen |
| 22. M7b 100% Task Success 意味着什么？ | 只意味着 7 个特定合成任务验证通过，不代表真实法律场景通用效果 |
| 23. Docker Build 卡在 `FROM python:3.12-slim` 要改 RAG 吗？ | 不要；先处理 Docker Hub 镜像源、代理与 DNS |
| 24. M8 Trace 和 Grafana 状态？ | PG Trace/Prometheus 核心已验收；可选 Grafana 因镜像拉取 EOF 未独立通过 |

额外加分题：为什么当前 `SESSION_LOCK_SECONDS=300` 与 `RAG_CPU_TIMEOUT_SECONDS=420` 值得关注？**答**：一个 RAG 请求可以在 Redis 锁租期结束后仍在运行，未来多用户/并发服务需锁续租、任务队列或额外的状态一致性控制；本地功能通过不等于生产并发安全。

<a id="ch19"></a>
## 19｜术语速查表

| 术语 | 一句话理解 | 本项目落点 |
|---|---|---|
| API | 系统对外提供的请求/响应接口 | `app/api/` |
| HTTP 200/201/409/422/503 | 传输层处理、创建、冲突、校验失败、服务不可用 | FastAPI 路由 |
| Pydantic | Python 输入输出的类型/约束校验 | `ChatRequest`、工具 Args |
| Async/Await | 非阻塞等待 I/O 的协程形式 | DB/HTTP/Qdrant 调用 |
| Thread | 可执行阻塞 CPU/C++ 计算的工作线程 | `asyncio.to_thread` 跑 ONNX |
| Embedding | 文本表示成高维向量 | BGE Small 512D |
| Cosine | 两个向量方向的相似度计算 | Qdrant `documents_v1` |
| Chunk | 文档切出的带来源的文本单元 | `DocumentChunk` |
| Payload | 向量点关联的结构化字段 | UUID/页码/offset/text |
| Dense Retrieval | 通过向量相似性找候选 | Qdrant QueryPoints |
| Sparse Retrieval | 通过词面匹配与统计打分 | 中文双字 BM25 |
| BM25 | 利用词频、IDF、长度正则化计算相关度 | `rag/sparse.py` |
| RRF | 只用排名融合多路检索 | `rag/fusion.py`，k=60 |
| Reranker | 对已召回候选更精细排序 | BGE Cross-Encoder CPU |
| RAG | 检索真实证据辅助 LLM 生成 | `rag/pipeline.py` |
| Grounding | 让回答受到证据约束 | Prompt + 来源编号 |
| Citation | 将答案指回来源证据 | `citation.py` |
| Faithfulness | 答案事实是否由证据蕴含 | **尚无完整语义评测** |
| Agent | 利用状态与工具执行多步任务的软件系统 | LangGraph |
| StateGraph | 定义节点、状态和条件边的图 | `agent/graph.py` |
| Router/Planner | 决定要执行的工具 | `agent/router.py` |
| Tool Schema | 工具允许的参数和类型 | `tools/registry.py` |
| ReAct | 推理-行动-观察循环范式 | 对比原理，**不是完全自由 ReAct** |
| MCP | 统一工具声明/发现/调用的协议 | stdio FastMCP + ClientSession |
| JSON-RPC | 有请求、响应和方法概念的 RPC 格式 | MCP stdio 通道 |
| Session | 一组近期对话和文档上下文 | Redis，TTL |
| Long-term Memory | 跨会话持久偏好 | PG + Qdrant |
| Checkpoint | 图执行状态的持久快照 | `AsyncPostgresSaver` |
| HITL | 敏感动作前要求人工决定 | `interrupt/resume` |
| Idempotency | 重试相同请求不重复产生业务效果 | 审批号唯一约束 |
| Fallback | 故障后有界且不编造事实的安全响应 | `tool_unavailable` |
| Trace | 一次请求内部节点/工具执行的完整路径元信息 | `agent_traces` |
| Metric | 可聚合的请求量、时延、失败/Token 数据 | Prometheus |
| Histogram/P95 | 延迟分布及高分位数 | `agent_e2e_latency_seconds` |
| Smoke Test | 小规模确认整个链路跑通 | M7/M9 合成测试 |
| Docker Image | 不可变应用镜像模板 | Dockerfile 构建 |
| Container | 由镜像运行出的进程环境 | `docker compose` |
| Volume | 容器重启/重建后保留的数据卷 | PG/Qdrant/模型缓存 |
| Python wheel | 安装后的包产物 | 曾与源码热补丁产生导入差异 |

<a id="ch20"></a>
## 20｜真实局限、工程优化和面试中的取舍分析

这些是**分析与优化建议**，不是已经实现或已经跑出更好数据的“项目成果”。

| 现状与限制 | 原因 / 风险 | 合理的下一步 |
|---|---|---|
| CPU BGE 重排很慢 | 大型 Cross-Encoder ONNX、候选文本/模型开销 | 先测冷/热缓存和真实候选对数，再比较小模型、量化、GPU 或外部推理服务 |
| BM25 对 Qdrant Payload 全量有界扫描 | 5000 Chunk 上限，不是倒排索引 | 独立 BM25 索引或 Qdrant 原生 Sparse/HYBRID，重新做 Recall/Latency 对比 |
| Route 规则依赖关键词 | 容易漏掉复杂自然语言、多语言指代 | 增加可校验分类或规划模型，并保留工具白名单与回退 |
| 实体抽取主要正则 | 只覆盖几类显式甲乙方/时间模式 | 引入适当监督 NER/IE 模型，但需真实标注数据、来源位置一致性和与规则基线的对比 |
| Citation 只检查合法编号 | 合法编号可以附着在错误事实上 | 增加 Claim→Evidence 对齐和人工评估；与语义相关性/准确率分开报告 |
| M7 合成数据很小 | 无法代表真实合同和复杂业务 | 数据集扩大并固定 split、任务难度、质量协议；记录失败类别 |
| RAG 预算 420s、Session 锁 300s | 长推理和锁租期不一致 | 分布式任务/续租/队列、明确取消与会话串行保障 |
| MCP stdio 每次新启动 | 进程初始化造成额外延迟 | 长驻客户端会话、批量化，增加健康与连接治理 |
| API 缺真实登录与文档访问控制 | 演示 UUID 不是身份校验 | 身份认证、权限模型、用户文档隔离、审计与密钥管理 |
| 模型与网络依赖本地环境 | Docker Hub 镜像网络不稳定、模型很大 | 固定镜像 digest/模型版本、离线镜像缓存、部署说明与可复现 CI 构建 |
| Trace 无生产保留策略 | 日志/追踪随时间增长且可能含敏感业务元信息 | 数据分级、访问审计、清理/保留周期、加密与脱敏 |
| 可选 Grafana 未实测 | 镜像拉取 `unexpected EOF` | 仅在环境网络恢复后独立验证 Prometheus Target + Dashboard |
| 多轮 Query Rewrite 很有限 | 规则拼接无法处理复杂指代 | 加离线对比实验，衡量 Query Rewrite 带来的召回改善和错误引入 |
| 无真实吞吐/并发数据 | 少量串行测试不反映生产负载 | 负载模型、压测指标、热冷启动/资源监控与稳定性分析 |

### 20.1 优化优先级怎么选？

如果未来真正要迭代（现在只是学习阶段，可以不动代码）：

1. **P0 正确性、安全性**：身份鉴权、文档范围隔离、HITL 幂等、真实样本的 Citation Faithfulness。
2. **P1 性能**：CPU Rerank 的模型/硬件与缓存策略、BM25 索引、限流和长任务调度。
3. **P2 体验和能力**：复杂查询改写、更多字段 IE、友好的前端、结果解释。
4. **P3 扩展系统**：多租户、远端 MCP、服务治理、分布式 Trace。

先有真实测量与回归协议，后讨论优化收益。不要在面试中承诺“做了某个技术就一定提速 80%”。

### 20.2 推荐 5 分钟项目讲解结构

- **第 1 分钟：场景和需求**——复杂合同需要有来源的问答、多步分析和审批写入。
- **第 2 分钟：数据与 RAG**——解析→Chunk 来源→BGE Dense/BM25/RRF→BGE Rerank→Qwen→Citation。
- **第 3 分钟：Agent 与记忆**——LangGraph State/Router/Typed Tools；Redis Session、PG Checkpoint、PG/Qdrant 偏好。
- **第 4 分钟：MCP、HITL 和可靠性**——标准 stdio 工具通道、审批 interrupt/resume、幂等、故障安全回退。
- **第 5 分钟：验证与局限**——M7 合成检索/Agent 指标、M9 真实本地 BASE/LIVE、Trace 性能诊断、CPU 重排瓶颈、正式镜像/Grafana 待完成。

练习结束时让别人打断你提问：**“这个函数到底在哪里？”“这个数字是在什么数据集上取得的？”“你的系统如果失败会不会编造法律结论？”**。如果能对着源码回答，就是掌握了项目。

<a id="ch21"></a>
## 21｜源码、验证证据和延伸阅读索引

### 21.1 源码主线（从入口到最深层）

- [应用生命周期](../app/main.py) → [文档 API](../app/api/documents.py) → [聊天 API](../app/api/chat.py) → [审批 API](../app/api/approvals.py)
- [Agent Graph](../app/agent/graph.py) → [AgentState](../app/agent/state.py) → [Router/Planner](../app/agent/router.py) → [Graph Nodes](../app/agent/nodes.py) → [可靠性执行器](../app/agent/reliability.py)
- [文档 Parser](../app/rag/parser.py) → [Chunker](../app/rag/chunker.py) → [Embedding](../app/rag/embedder.py) → [Retriever](../app/rag/retriever.py) → [BM25](../app/rag/sparse.py) → [RRF](../app/rag/fusion.py) → [Reranker](../app/rag/reranker.py) → [Citation](../app/rag/citation.py) → [RAG Pipeline](../app/rag/pipeline.py) → [LLM Client](../app/llm/client.py)
- [工具 Schema/Registry](../app/tools/registry.py) → [抽取](../app/tools/extraction.py) → [规则元数据](../app/tools/metadata.py) → [MCP Bridge](../app/tools/mcp_bridge.py)
- [MCP Client](../app/mcp_client/adapter.py) → [MCP Server](../mcp_server/server.py) → [MCP 实际工具实现](../mcp_server/document_tools.py)
- [Redis Session](../app/memory/session.py) → [长期偏好](../app/memory/long_term.py) → [Checkpoint](../app/memory/checkpoint.py)
- [审批输入策略](../app/approvals/policy.py) → [审批持久化与幂等](../app/approvals/storage.py)
- [Trace](../app/observability/tracing.py) → [Metrics](../app/observability/metrics.py) → [PG Trace Storage](../app/observability/storage.py)

### 21.2 优先阅读的测试与归档证据

- [M7a 检索评测](M7A_ACCEPTANCE.md)：合成 Recall@K / MRR@K。
- [M7b Agent 评测](M7B_ACCEPTANCE.md)：工具选择、任务成功、来源范围。
- [M7c 系统评测](M7C_ACCEPTANCE.md)：真实串行耗时和 BGE CPU 性能瓶颈。
- [M6b 人审恢复](M6B_ACCEPTANCE.md)：API 重启后的审批与幂等。
- [M8 Trace 验收](M8_ACCEPTANCE.md)：PostgreSQL Trace 跨 API 重启保留。
- [M9 BASE + LIVE 最终验收](M9_ACCEPTANCE.md)：完整跨模块与真实 Qwen 验证。
- [正式发布仍待办](RELEASE_CHECKLIST.md)：Grafana 和干净镜像构建。
- [API 字段细节](API.md)、[MCP 专题](MCP.md)、[记忆专题](MEMORY.md)、[可靠性专题](RELIABILITY.md)。
- [现有简历与面试资料](RESUME_PROJECT.md)：把工程能力写成可追问且有证据的经历。

### 21.3 最后的学习检查清单

- [ ] 不看 README 能画出 FastAPI、LangGraph、RAG、MCP、PG、Redis、Qdrant、Qwen 的连接关系。
- [ ] 能从 `POST /v1/chat` 追踪到某个业务工具的真实函数。
- [ ] 能解释 BM25、RRF、Cross-Encoder 的输入输出与计算取舍。
- [ ] 能指出 `S1/S2` 来源及其引用校验的边界。
- [ ] 能说清 Agent 状态字段与 `route/decide/call_tool/synthesize`。
- [ ] 能区分 Registry 普通工具和标准 MCP Client/Server。
- [ ] 能区分 Redis Session、PG Checkpoint 和长期偏好。
- [ ] 能完整复述 HITL pending→approved/rejected→幂等写入路径。
- [ ] 能复述实际发生过的“CPU 重排三次超时、模型调用 0 次”的排障过程。
- [ ] 能解释 M7 指标的公式、分母和样本规模限制。
- [ ] 能在 Trace 中定位工具异常与 LLM 调用次数。
- [ ] 面试能主动说明 Grafana 与干净镜像构建还没验收，且本项目尚非生产级。

**最终目标**：你不必记住每一个函数的全部源代码，但必须能在不同技术问题之间建立准确的“需求 → 数据 → 决策 → 执行 → 验证 → 故障处理”因果链。这比只会运行 BAT 命令更接近实际 Agent 工程师的能力。
