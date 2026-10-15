> **更新提示（2026-10-15）**：本文件的部分里程碑文字来自早期 M3/M6 开发过程，已不再反映最终验收状态。M0–M9 核心功能目前已通过本地验收。请以 [完整中文源码学习与面试手册](LEARNING_GUIDE_CN.md)、[2026 Agent 面试高频精选补充](AGENT_INTERVIEW_HIGH_FREQUENCY_SUPPLEMENT_CN.md)、[当前简历证据版](RESUME_PROJECT.md) 和 [M9 验收记录](M9_ACCEPTANCE.md) 为准；下方内容保留作历史阅读资料。

# Interview Framing

## 30-second project framing

> DocMind-Agent is a complex-document RAG Agent project. I separate document ingestion, hybrid retrieval, Agent workflow, memory, MCP, evaluation and observability into explicit modules instead of putting everything inside one prompt loop. PostgreSQL owns durable structured state, Redis owns session context, Qdrant owns semantic document/memory retrieval, and generation is decoupled through an OpenAI-compatible endpoint.

## What M0 proves

M0 proves:

- reproducible Docker-based infrastructure;
- explicit PostgreSQL/Redis/Qdrant ownership;
- FastAPI service boundary;
- dependency health diagnostics;
- environment-based configuration;
- frozen V1 architecture and module boundaries.

Do **not** claim RAG, Agent, Memory or MCP functionality before the corresponding module acceptance tests pass.

## M3 interview framing

- M3a was validated with real LangGraph tool routing, PostgreSQL metadata and a live Qwen3 RAG citation.
- M3b adds four tools in total: source-pattern extraction and evidence-scoped summarization, with a bounded model-assisted ordering/fallback policy.
- Do not claim an unrestricted autonomous LLM planner, general legal NER, or full-document summarization accuracy.
- M3b code and unit tests exist but are not locally accepted yet.
- Memory, MCP, HITL and quantitative Agent evaluation remain future modules.


## M5 MCP integration (accepted 2026-10-15)

M5a uses the official Python MCP SDK, a separately launched stdio
server process, and the MCP initialize/tools-list/tools-call lifecycle.
Four bounded read-only document tools expose provenance-aware PostgreSQL,
Qdrant and Hybrid Retrieval results. This is distinct from M3's direct
Python function registry. M5a transport acceptance and M5b Agent integration both passed in the real Docker environment; this is functional testing rather than production reliability evaluation.

## M6 — Reliability and HITL (current boundaries)

- M6a passed actual fault-injection testing: two transient retries, explicit
  no-facts fallback, and partial multi-tool source preservation.
- M6b code uses a real LangGraph interrupt and a PostgreSQL approval
  state machine. Approving resumes the checkpoint and triggers an
  idempotent database transaction; rejecting never inserts a note.
- M6b **passed local Docker acceptance on 2026-10-15**, including API
  restart and both decision branches, before it can be called completed.
- No real authentication, policy-driven RBAC, remote MCP access or
  exactly-once arbitrary external side-effect execution is claimed.


The verified HITL chain is `POST /v1/chat` → PostgreSQL pending approval → LangGraph `interrupt()` → API restart → `POST /v1/approvals/{approval_id}` → resume/checkpoint → one approved `review_notes` insert. Reject and repeat/contradictory decisions were also exercised. The demo UUID scope checks are **not authentication**, and no production security or arbitrary external-write exactly-once guarantee is claimed.
