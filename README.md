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

当前开发阶段：**M2 — Hybrid RAG**。M0、M1 均已通过实际部署及本地验收。

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
| M2 | Hybrid RAG + Rerank + Citation | In progress |
| M3 | LangGraph Agent + Tool Calling | Planned |
| M4 | Session/Long-term Memory + Checkpoint | Planned |
| M5 | MCP Server + Client | Planned |
| M6 | Retry + Timeout + Fallback + HITL | Planned |
| M7 | RAG/Agent/System Eval | Planned |
| M8 | Agent Metrics + Trace | Planned |
| M9 | Engineering wrap-up + Demo + Resume | Planned |

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

## M2a — Hybrid retrieval (implementation committed; awaiting local acceptance)

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

The smoke test indexes three synthetic TXT documents and confirms Dense,
BM25, RRF, exact document filtering and an empty result for an unknown
document. Success ends with `M2a PASS`.

M2a is intentionally **not yet RAG question answering**. Reranking,
query rewriting, answer generation and citation validation come next.

Implementation details: [docs/M2_GUIDE.md](docs/M2_GUIDE.md) ·
M1 acceptance evidence: [docs/M1_ACCEPTANCE.md](docs/M1_ACCEPTANCE.md).

## Related Project

Inference serving and observability base:

https://github.com/gufe-zeng/llm-serving-ops

## V1 Non-goals

V1 does **not** implement Multi-Agent, fine-tuning, Kubernetes, OCR, multimodal parsing, browser agents, A2A, autoscaling, or unlimited reflection.
