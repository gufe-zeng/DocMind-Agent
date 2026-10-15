# DocMind-Agent

> 面向复杂文档的可追溯 RAG Agent 系统。

DocMind-Agent V1.0 的目标是面向法律、政务、合同等复杂文档，构建一条可解释、可评测、可恢复、可观测的 Agent 应用链路：

```text
Document Pipeline
→ Hybrid RAG
→ Rerank
→ Citation
→ LangGraph Agent
→ Tool Calling
→ Memory
→ MCP
→ HITL
→ Eval
→ Observability
```

**M0–M8 已通过本地功能与合成评测验收；M9 正在进行业务 Demo 和工程收尾。** 本地验收不代表生产就绪。

V1 范围已冻结，详见 [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) 和 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## M0 Quick Start

复制环境变量：

```cmd
copy .env.example .env
```

启动基础设施与 API：

```cmd
docker compose up -d --build
```

查看状态：

```cmd
docker compose ps
```

验证：

```cmd
curl http://127.0.0.1:8090/health
```

预期 PostgreSQL、Redis、Qdrant 均为 `up`。

Prometheus 格式指标：

```cmd
curl http://127.0.0.1:8090/metrics
```

停止：

```cmd
docker compose down
```

也可以直接运行：

```cmd
scripts\bootstrap.bat
scripts\smoke_test.bat
```

## Development Modules

| Module | Scope | Status |
|---|---|---|
| M0 | Skeleton + PostgreSQL/Redis/Qdrant + Health | Completed (2026-10-11) |
| M1 | Document Pipeline | Completed (2026-10-15) |
| M2 | Hybrid RAG + Rerank + Citation | Completed (2026-10-15) |
| M3 | LangGraph Agent + Tool Calling | Completed (2026-10-15) |
| M4 | Session/Long-term Memory + Checkpoint | Completed (2026-10-15) |
| M5 | MCP Server + Client | Completed (2026-10-15) |
| M6 | Retry + Timeout + Fallback + HITL | Completed (2026-10-15) |
| M7 | RAG/Agent/System Eval | Completed: M7a/M7b/M7c synthetic local gates (2026-10-15) |
| M8 | Agent Metrics + Trace | Completed: real PostgreSQL Trace, MCP/HITL and Prometheus acceptance (2026-10-15) |
| M9 | Engineering wrap-up + Demo + Resume | Implemented; BASE/LIVE Docker acceptance pending |

## M1a — Parse and chunk documents

M1a has **passed local validation** (2026-10-14): TXT, PDF, DOCX, source metadata and long-text chunking.
M1b was also accepted on 2026-10-15: source storage, ModelScope 512-d CPU embeddings, Qdrant payloads and idempotent reindex.

```cmd
git pull
docker compose up -d --build
scripts\check_m1a.bat
```

M1a accepted: `M1a PASS` (reported from the user's Docker environment).

Details: [M1 Guide](docs/M1_GUIDE.md) · [M0 Acceptance](docs/M0_ACCEPTANCE.md)

## M1b — Upload, embed and index in Qdrant

The CPU BGE model is downloaded from **ModelScope**, using a compatible
community-maintained ONNX conversion. FastEmbed then runs strictly from its
local cache; the first indexing run does not call Hugging Face:

- ModelScope repository: https://modelscope.cn/models/lyf219/bge-small-zh-v1.5-onnx
- Original model: `BAAI/bge-small-zh-v1.5`; vector dimension: 512
- Runtime: ONNX CPU (no PyTorch GPU dependency)

First run (on Windows CMD):

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_modelscope.bat
scripts\check_m1b.bat
```

A successful test prints three indexed documents (TXT/PDF/DOCX), checks 512-dimensional
vectors and source metadata in Qdrant, verifies PostgreSQL document statuses and
checks that re-indexing does not create duplicates. Final line: `M1b PASS`.

Manual API example:

```cmd
curl --noproxy "*" -X POST -F "file=@data/samples/sample_contract.txt" http://127.0.0.1:8090/v1/documents
```

Copy `document_id` from the response, then use Windows CMD:

```cmd
set DOC_ID=your-uuid-from-upload
curl --noproxy "*" -X POST http://127.0.0.1:8090/v1/documents/%DOC_ID%/index
```

Implementation and troubleshooting: [M1 Guide](docs/M1_GUIDE.md) ·
[M1b API Contract](docs/API.md).

**M1 Completed (2026-10-15).** Local tests passed: ModelScope ONNX download, 512-dimensional CPU embedding, TXT/PDF/DOCX upload and Qdrant indexing, and idempotent reindexing.

## M2a — Hybrid retrieval (accepted on 2026-10-15)

Stage M2a:

```text
Chinese query
├── Dense: CPU BGE query embedding → Qdrant cosine Top-K
└── Sparse: Chinese character bigrams → BM25 Top-K
       ↓
Reciprocal Rank Fusion (RRF, k=60)
       ↓
Source-aware ranked chunks (no generation yet)
```

Run in Windows CMD after pulling the latest commit:

```cmd
git pull
docker compose up -d --build api
scripts\check_m2a.bat
```

The 2026-10-15 local test indexed three synthetic TXT documents and confirmed Dense,
BM25, RRF, exact document filtering and no-result behavior. Output: `M2a PASS`.

M2a produces ranked evidence; it does not generate answers. M2b adds actual
Cross-Encoder reranking, evidence IDs and OpenAI-compatible LLM generation.

Implementation details: [docs/M2_GUIDE.md](docs/M2_GUIDE.md) ·
M1 acceptance evidence: [docs/M1_ACCEPTANCE.md](docs/M1_ACCEPTANCE.md).

## M2b — Reranker + grounded generation (accepted on 2026-10-15)

1. **ModelScope BGE Reranker**: BAAI/bge-reranker-base (ONNX, CPU).
   The initial ~1.11 GB download is considerably larger than the M1 embedding
   weights, and remains cached in the existing `embedding-cache` volume.
2. **Deterministic source citations**: Python assigns [S1], [S2] and checks
   the generated response only references real IDs. This checks provenance
   links, **not semantic entailment of individual claims**.
3. **LLM generation**: One OpenAI-compatible chat completion through your
   `llm-serving-ops` endpoint; max two evidence chunks and 128 output tokens
   by default for the local Qwen3-0.6B/1024-token context.

Run in Windows CMD:

```cmd
git pull
docker compose up -d --build api
scripts\check_reranker.bat
scripts\check_m2b.bat
```

The 2026-10-15 local logs confirm `check_reranker.bat`, `check_m2b.bat`,
and **`check_m2b_live.bat`** passed. The live test called
`Qwen/Qwen3-0.6B` through `host.docker.internal:8000` and returned a
cited answer: `根据合同，服务验收后付款期限是三十天。[S1]`.

Once `llm-serving-ops` serves a model on host port 8000, run:

```cmd
scripts\check_m2b_live.bat
```

The real model answer contained a valid `[S1]` citation. **M2 functional
acceptance is complete.** Query rewrite using session history and
quantitative retrieval/faithfulness evaluation remain future tasks.

See [M2 Guide](docs/M2_GUIDE.md), [M2b Acceptance](docs/M2B_ACCEPTANCE.md)
and [M2a Acceptance](docs/M2A_ACCEPTANCE.md) for detailed checks.

## M3a — LangGraph Agent routing and Tool Calling (accepted 2026-10-15)

M3a implements a real `StateGraph` with conditional edges and a typed tool
registry. It reuses the accepted M2 RAG path and the PostgreSQL document
metadata table. Routing was **rule based** in M3a. M3b adds constrained, validated LLM tool ordering, not open-ended autonomy.

```text
POST /v1/chat
     ↓
LangGraph: route → decide → call_tool → decide → synthesize
                             ↑          │
                             └──────────┘ (next bounded tool)
                    ↓
       search_documents / query_document_metadata
                    ↓
              answer + source IDs
```

To validate in Windows CMD, keep `llm-serving-ops` running on port 8000:

```cmd
git pull
docker compose up -d --build api
scripts\check_m3a.bat
```

The smoke test indexes a synthetic contract, calls the PostgreSQL metadata
tool and calls the full M2 RAG tool via the new `POST /v1/chat` interface.
Expected final output: `M3a PASS`.

**M3a passed local integration testing** on 2026-10-15. It has no cross-request
memory/checkpointer or model-selected multi-tool plan. See
[M3a Acceptance](docs/M3A_ACCEPTANCE.md) and [M3 Guide](docs/M3_GUIDE.md).

## M3b — Extraction, scoped summary and bounded tool planning

M3b implements four real read-only tools: `search_documents`,
`query_document_metadata`, `extract_entities` and `summarize_document`.
Contract extraction scans the actual Qdrant source chunks for explicit
parties and payment terms, with per-fact citations. It is a rule-based field
extractor, **not** a general-purpose legal NER model.

Summaries use the accepted M2 RAG and live Qwen path and are explicitly
labelled **retrieved-evidence summaries**, not complete document coverage.
Combined extraction/summary requests can use Qwen to reorder a
rule-required tool set. A model output must pass a strict allowlist/JSON
check; otherwise the graph uses an observable rule fallback.
Independent per-tool citations are renumbered into one global namespace.

To validate (Windows CMD, with the existing vLLM running on port 8000):

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m3b.bat
```

Expected final output: `M3b PASS` and `M3b validation passed.`.
Local test **passed on 2026-10-15**, including real Qwen-assisted multi-tool planning, source-backed extraction and S1–S4 citation integrity.
See [M3 Guide](docs/M3_GUIDE.md).

## M4a — Redis session history + PostgreSQL LangGraph checkpoints

Status: **accepted with a real multi-turn Qwen test on 2026-10-15**.

New behavior preserves recent conversation context under one `session_id`:

```text
POST /v1/chat (first question + document_id)
    ↓ Redis: create TTL-limited session, store bounded history
    ↓ LangGraph: checkpoint each node to PostgreSQL
POST /v1/chat (follow-up + same session_id, no document_id)
    ↓ Load Redis conversation/document context
    ↓ Conservative reference expansion for short follow-ups
    ↓ Reuse current document filter; run real RAG/Agent
    ↓ Refresh Redis TTL + durable PostgreSQL checkpoint
GET /v1/sessions/{session_id}
    ↓ Return bounded turns and checkpoint_saved status
```

Redis retains up to **6 turns** per session with **1-hour idle TTL**.
LangGraph uses official PostgreSQL `AsyncPostgresSaver`, not a fake memory
table. Old per-turn graph state is reset explicitly before every new turn.

**Local validation (Windows CMD, keep vLLM on host port 8000 running):**

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m4a.bat
```

The observed final output was **`M4a PASS`**. The script creates a contract, performs
two live-Qwen turns including `如果逾期呢？`, checks that the second turn
reuses the document, verifies Redis expiry and checks the PostgreSQL
checkpoint from a separate database connection.

Important: M4a does **not** implement durable cross-session preferences,
Qdrant `memories_v1`, or robust interrupted-run resume controls.
Those belong to M4b. The API has no end-user authentication yet and
must not be exposed on a public network.

See [Memory Design](docs/MEMORY.md).

## M4b — Long-term preference + Checkpoint recovery

M4b **passed local acceptance on 2026-10-15**, including both independent validation scripts. It stores an explicitly
requested contract-output format in PostgreSQL and Qdrant `memories_v1`.
A new session can recall the preference using the same demo `user_id`
and pass its whitelisted fields into the RAG answer format. No arbitrary
document text or chat history is automatically promoted.

A separate test interrupts LangGraph before a real read-only tool, then
continues from a PostgreSQL checkpoint using a fresh database connection.

In Windows CMD, keep the existing vLLM service running:

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m4b.bat
scripts\check_m4b_resume.bat
```

Expected: `M4b MEMORY PASS` and `M4b CHECKPOINT PASS`.

**Security boundary:** `user_id` is a caller-provided demonstration UUID,
not an authenticated identity. Keep the API local-only.

## M5a — Document MCP Server (accepted 2026-10-15)

M5a implements the four **frozen V1 document MCP tools** using the official
Python MCP SDK with JSON-RPC over **stdio**, not an imitation REST endpoint:

| MCP tool | Purpose |
|---|---|
| `search_documents` | BGE Dense + Chinese BM25 + RRF source chunks |
| `get_document` | PostgreSQL document status and metadata |
| `get_document_page` | Indexed PDF page text with page/chunk provenance |
| `find_clause` | Exact phrase/keyword lookup over document chunks |

The MCP server is a **separate subprocess** launched inside the API container.
`scripts/check_m5a.py` invokes it via real SDK `ClientSession`,
`stdio_client` and the MCP `tools/list`/`tools/call` operations.
The smoke test does not depend on vLLM; it reuses ModelScope BGE and existing
PostgreSQL/Qdrant data. No new port or Docker volume is required.

Windows CMD:

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m5a.bat
```

**Observed output on 2026-10-15:** `M5a MCP PASS` and `M5a validation passed.`.

M5a **passed** real MCP Server/Client transport acceptance using an independent client.
The LangGraph Agent continues to call its existing tools directly until
**M5b** integrates the MCP client adapter. See [MCP Guide](docs/MCP.md).

## M5b — LangGraph Agent MCP integration (accepted 2026-10-15)

M5b adds a real Model Context Protocol ClientSession adapter inside the
existing LangGraph Agent, without changing the accepted M2–M4 execution.
Explicit MCP queries route to four read-only typed Agent tools:

| LangGraph tool | MCP Server tool |
|---|---|
| `mcp_find_clause` | `find_clause` |
| `mcp_get_document` | `get_document` |
| `mcp_get_document_page` | `get_document_page` |
| `mcp_search_documents` | `search_documents` |

The flow is HTTP /v1/chat → LangGraph → typed registry → official
stdio MCP client → separate MCP server subprocess → document evidence.
Every response records both `tools_called` and `mcp_tools_called` so the
protocol boundary is observable. Existing ordinary RAG/Agent queries still
use their original tools; MCP results are sourced excerpts, not new
LLM-generated answers.

Run in Windows CMD:

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m5b.bat
```

The test drives all four MCP tools and one two-tool Agent workflow through
the live HTTP API, checking chunk/document/page provenance and citations.
Expected final lines: `M5b AGENT MCP PASS` and
`M5b Agent MCP validation passed.`. No vLLM is required.

**M5b passed real local Docker acceptance on 2026-10-15.** The actual Agent reported MCP tool names, original chunks, PDF page 2 provenance, and multi-tool execution. M5 is Completed; see [M5b acceptance](docs/M5B_ACCEPTANCE.md).
See [MCP Guide](docs/MCP.md).

## M6a — Tool Runtime: Timeout, Retry and Safe Fallback

**Completed (2026-10-15): real Docker acceptance passed.**

All eight currently supported **read-only** Agent tools have individual
timeouts and at most two retries for transient connection/timeout faults.
Malformed arguments and provenance violations are not retried.
Exhausted transient failures return a `tool_unavailable` response with
no fabricated facts or citations. Multi-tool tasks preserve successful
evidence and return `partial` when another tool is unavailable.
Retries do not consume extra LangGraph steps.

Windows CMD acceptance:

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m6a.bat
```

Observed: `M6a PASS` and `M6a reliability validation passed.`.
The test injects faults in its own process only. No additional model
downloads or a live Qwen service are required.

**M6b** is the separate `save_review_note` protected-write / HITL
implementation. See [M6 Reliability Guide](docs/RELIABILITY.md).

## M6b — Protected `save_review_note` / Human-in-the-Loop

**M6b Completed (2026-10-15): actual two-phase Docker HITL acceptance passed, including API restart, checkpoint continuation, approval and rejection.**

An explicit `保存审核备注：...` request creates a PostgreSQL approval
record. LangGraph then pauses with `interrupt()` **before** the note is
written. The frozen `POST /v1/approvals/{approval_id}` endpoint records
an approval or rejection, resumes the checkpoint and writes the note
transactionally **only if approved**. Repeated requests cannot duplicate
a note; a contradictory decision is rejected.

The test also verifies restart recovery of a pending approval:

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m6b.bat
```

The script will **restart only the API container once** between creating
the pending note and approving it. No Qwen is required and no databases,
volumes or model caches are removed.

Observed: **`M6b HITL PASS`** and **`M6b HITL validation passed.`** See [M6b Acceptance](docs/M6B_ACCEPTANCE.md).
See [M6 Reliability and HITL Guide](docs/RELIABILITY.md).

**Security:** demo `user_id`/`session_id` UUIDs are not authentication.
The approval workflow must not be exposed to untrusted clients.

## Related Project

Inference serving and observability base:

https://github.com/gufe-zeng/llm-serving-ops

## V1 Non-goals

V1 does **not** implement Multi-Agent, fine-tuning, Kubernetes, OCR, multimodal parsing, browser agents, A2A, autoscaling, or unlimited reflection.


## M7a — Retrieval evaluation (accepted 2026-10-15)

`scripts\check_m7a.bat` passed on the local Docker stack: three synthetic
document-level cases produced Recall@3=1.0 and MRR@3=1.0.
Sixty-three retrieved candidate chunks were outside the fixture's newly
indexed document IDs. These are smoke-test metrics, not real-world
generalization or semantic citation-accuracy claims.
See [M7a acceptance](docs/M7A_ACCEPTANCE.md).

## M7b — Agent evaluation (accepted 2026-10-15)

`eval/agent_eval.py` computes task success, tool selection, MCP tool selection,
tool success, average steps, and runtime failure rate against explicit
synthetic fixture assertions. The test calls the real Agent HTTP API and
stdio MCP stack without Qwen, and checks source evidence/document scope.

Windows CMD:

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m7b.bat
```

Observed: `M7b AGENT EVAL PASS` and
`M7b Agent evaluation validation passed.` on real local Docker.
Seven synthetic cases achieved Task Success=1.0, Tool Selection=1.0,
MCP Tool Selection=1.0 and Tool Success=1.0 (8/8 tool calls).
Average steps=1.142857, runtime failure rate=0.
See [M7b acceptance](docs/M7B_ACCEPTANCE.md) and
[Evaluation design](docs/EVALUATION.md).

## M7c — System evaluation (accepted 2026-10-15)

Both BASE and LIVE local Docker checks passed. Four real serial HTTP requests
per run had zero failures; five read-only tool events per run were complete.
The separate in-container BGE CPU reranker timings were **259.30 s** (BASE)
and **171.97 s** (LIVE). The direct Qwen RAG probe used one call
(241 prompt tokens, 16 completion tokens). These stage timings are NOT
Agent HTTP node-attributed or concurrency results. See
[the recorded M7c acceptance](docs/M7C_ACCEPTANCE.md).

## M8 — Metrics, durable request/node traces and faster rebuilds

The M8 implementation adds request and trace UUIDs, LangGraph node
timestamps/statuses, M6 tool-event durations, Prometheus metrics,
PostgreSQL `agent_traces` and privacy-safe logs. The existing
`/v1/chat`, `/v1/approvals/{approval_id}` and `/metrics` endpoints
are reused; no new public trace-read API is introduced.

The Dockerfile now installs third-party packages **before copying app source**.
The first rearranged image build may still be slow, but subsequent
source-only builds with unchanged `pyproject.toml` should reuse the
expensive dependency layer. Do not use `--no-cache`.

Run the **single** M8 local acceptance sequence in Windows CMD:

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m8.bat
```

The script automatically tests real Agent/MCP/HITL traces, restarts
**only the API container** and checks that PostgreSQL trace data persists.
The restart does not rebuild the API image; Qwen is not required.
Expected: `M8 OBSERVABILITY PASS`.
Observed: `M8 OBSERVABILITY PASS` and `M8 Observability validation passed.` on local Docker, including restart recovery. See [M8 acceptance](docs/M8_ACCEPTANCE.md) and [M8 guide](docs/OBSERVABILITY.md). Optional Grafana dashboards remain separately unverified.

## M9 — End-to-end business demo and engineering wrap-up (pending local acceptance)

M9 consolidates existing V1 capabilities rather than adding another public API:
real synthetic TXT/PDF/DOCX upload/index, LangGraph two-tool MCP, extraction
with source references, Redis follow-up, explicit cross-session preferences,
HITL approval/idempotency and PostgreSQL Trace/Prometheus.

Run Windows CMD **one new API build**, then the no-rebuild validators:

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m9.bat
```

Expected: `M9 DEMO BASE PASS`. With Qwen/vLLM already listening on host 8000:

```cmd
scripts\check_m9_live.bat
```

Expected: `M9 DEMO LIVE PASS`. The LIVE script reuses BASE's indexed
fixture for one Qwen-grounded RAG answer; CPU rerank may take minutes.
Neither validator rebuilds the Docker image. M9 remains pending actual
local results.

- [M9 Demo guide](docs/M9_DEMO.md)
- [M9 acceptance](docs/M9_ACCEPTANCE.md)
- [Resume and interview project description](docs/RESUME_PROJECT.md)
- [Evidence-based release checklist](docs/RELEASE_CHECKLIST.md)

The full frozen V1 sign-off additionally requires a local Grafana
dashboard check; the M8 core metrics already passed.
