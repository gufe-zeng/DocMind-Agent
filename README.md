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

## M2b — Reranker + grounded generation (model/core accepted; live pending)

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

The 2026-10-15 local logs confirm `check_reranker.bat` and `check_m2b.bat`
**passed**. The second test uses a controlled mock LLM. The live test is still
pending because `host.docker.internal:8000` could not be reached.

Once `llm-serving-ops` serves a model on host port 8000, run:

```cmd
scripts\check_m2b_live.bat
```

A real answer must contain a valid `[S1]` citation; otherwise the pipeline
fails closed with `citation_unverified`. M2 remains In Progress until the
real endpoint works.

See [M2 Guide](docs/M2_GUIDE.md), [M2b Acceptance](docs/M2B_ACCEPTANCE.md)
and [M2a Acceptance](docs/M2A_ACCEPTANCE.md) for detailed checks.

## Related Project

Inference serving and observability base:

https://github.com/gufe-zeng/llm-serving-ops

## V1 Non-goals

V1 does **not** implement Multi-Agent, fine-tuning, Kubernetes, OCR, multimodal parsing, browser agents, A2A, autoscaling, or unlimited reflection.
