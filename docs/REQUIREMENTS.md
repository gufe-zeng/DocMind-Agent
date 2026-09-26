# DocMind-Agent V1.0 Requirements

> Status: **FROZEN**  
> Target: 2027 autumn recruitment — Agent / LLM application engineering roles  
> Change rule: P0 scope is not expanded before V1 acceptance. New ideas go to V1.1/V2 backlog.

## 1. Product Positioning

DocMind-Agent is a traceable RAG Agent system for complex documents such as contracts, legal materials and public-sector documents.

The project is designed to prove practical engineering ability across:

```text
Document Processing
→ Hybrid RAG
→ Rerank
→ Citation
→ Agent Workflow
→ Tool Calling
→ Memory
→ MCP
→ HITL
→ Evaluation
→ Observability
```

The inference layer is decoupled through an OpenAI-compatible API and can reuse:

https://github.com/gufe-zeng/llm-serving-ops

## 2. Target Roles

Primary:

- Agent Engineer
- LLM Application Engineer
- RAG Engineer
- AI Application Backend Engineer

Secondary:

- LLMOps / AI Platform Engineer

The V1 scope prioritizes the capability intersection shared by these roles rather than any single company-specific JD.

## 3. Core User Scenarios

### S1 — Traceable document Q&A

User uploads a contract and asks:

> 付款期限是什么？违约责任是什么？

System returns:

- concise answer;
- evidence snippets;
- document name;
- page/source metadata;
- citation identifiers.

### S2 — Multi-step document analysis

User asks:

> 找出合同主体、付款期限、履约期限和违约责任，并总结主要风险。

Agent should:

1. identify intent;
2. retrieve evidence;
3. call extraction/summary tools as needed;
4. collect tool outputs;
5. synthesize a structured answer;
6. attach citations.

### S3 — Multi-turn conversation

User asks:

> 这份合同付款期限是什么？

Then:

> 如果逾期呢？

The second turn should resolve the conversational reference using Session Memory.

### S4 — Long-term preference reuse

A user preference such as:

> 以后合同分析都按“主体、金额、期限、风险、引用”输出。

may be persisted as long-term memory and retrieved in a later session.

### S5 — Human approval for a write action

When the Agent wants to execute:

```text
save_review_note(...)
```

execution must pause until the user explicitly approves or rejects it.

### S6 — Recoverable Agent execution

If execution is interrupted after several graph nodes, checkpoint state can be loaded and the task can continue without repeating every completed step.

## 4. Functional Requirements

### FR-01 Document ingestion

V1 supports PDF, DOCX and TXT.

Required pipeline:

```text
Upload
→ Parse
→ Normalize
→ Chunk
→ Metadata
→ Index
```

Every chunk must retain at least:

```json
{
  "document_id": "...",
  "filename": "...",
  "page": 12,
  "section": "...",
  "chunk_id": "...",
  "text": "..."
}
```

OCR is not part of V1.

### FR-02 Hybrid RAG

The retrieval pipeline is frozen as:

```text
Query
→ Query Rewrite
→ Metadata Filter
→ Dense Retrieval ─┐
                   ├→ RRF Fusion
BM25 Retrieval ────┘
→ Reranker
→ Top-K Evidence
→ LLM
→ Answer + Citation
```

Frozen implementation direction:

- Dense embedding: BGE Chinese embedding model
- Vector store: Qdrant
- Sparse retrieval: BM25
- Fusion: Reciprocal Rank Fusion
- Rerank: BGE reranker family
- Generation: OpenAI-compatible LLM endpoint

### FR-03 Citation

Every evidence-grounded answer must expose source references.

Minimum citation fields:

- document ID;
- filename;
- page or source location;
- chunk ID;
- evidence text.

Citation generation and validation are separate from answer text generation.

### FR-04 Agent workflow

The Agent runtime uses LangGraph-style stateful graph execution.

Frozen logical flow:

```text
START
→ Load Memory
→ Intent Router
→ Plan / Decide
→ Tool Node
→ Enough Evidence?
   ├─ No  → Tool Node
   └─ Yes → Synthesize
→ Citation Check
→ END
```

### FR-05 Agent State

The state contract includes:

- session_id
- user_id
- query
- messages
- intent
- plan
- retrieved_docs
- tool_results
- entities
- current_step
- retry_count
- approval_required
- final_answer

### FR-06 Tools

V1 must implement at least:

1. `search_documents`
2. `extract_entities`
3. `summarize_document`
4. `query_document_metadata`
5. `save_review_note` — HITL protected write operation

### FR-07 Memory

V1 implements four distinct concepts:

- Working Memory: Agent State for the current graph execution.
- Session Memory: Redis-backed recent context and conversation summary.
- Long-term Memory: persistent user preferences and confirmed facts.
- Checkpoint: persistent Agent execution checkpoint for interruption/recovery.

Long-term storage:

```text
Structured memory → PostgreSQL
Semantic memory   → Qdrant memories_v1
```

### FR-08 Memory Policy

| Information | Policy |
|---|---|
| Tool intermediate state | Working Memory |
| Recent conversation | Session Memory |
| Conversation summary | Session/Persistent summary |
| Explicit user preference | Long-term Memory |
| Document source content | Document store/index |
| Temporary retrieval candidates | Session only |
| Sensitive temporary content | Not written to long-term memory |
| Expired sessions | TTL / cleanup |

### FR-09 MCP

V1 includes one self-built Document MCP Server.

Required tools:

- `search_documents`
- `get_document`
- `get_document_page`
- `find_clause`

The Agent connects through an MCP client adapter.

### FR-10 Reliability

The runtime must support:

- tool timeout;
- maximum 2 retries for retryable tool failures;
- fallback path;
- maximum 8 Agent steps;
- checkpoint persistence;
- Human-in-the-Loop approval;
- traceable error responses.

Unlimited reflection is not permitted.

### FR-11 Evaluation

RAG:

- Recall@K
- MRR
- Citation Accuracy

Agent:

- Task Success Rate
- Tool Selection Accuracy
- Tool Success Rate
- Average Agent Steps
- Failure Rate

System:

- Agent E2E Latency
- Retrieval Latency
- Rerank Latency
- Tool Latency
- LLM Calls
- Token Usage

### FR-12 Observability

Every Agent request receives:

- request_id
- trace_id
- session_id

Each graph node records:

- start time;
- end time;
- status;
- tool;
- token usage when available;
- error when present.

Prometheus metrics include at least:

```text
agent_requests_total
agent_success_total
agent_failures_total
agent_steps
tool_calls_total
tool_failures_total
rag_latency_seconds
rerank_latency_seconds
tool_latency_seconds
agent_e2e_latency_seconds
```

### FR-13 API

Frozen V1 public API:

```text
POST /v1/documents
POST /v1/documents/{id}/index
POST /v1/chat
GET  /v1/sessions/{session_id}
POST /v1/approvals/{approval_id}
GET  /health
GET  /metrics
```

M0 only implements `/health` and `/metrics`.

## 5. Storage Ownership

PostgreSQL:

- documents
- sessions
- messages
- memories
- approvals
- agent_traces
- checkpoints

Redis:

- recent session messages
- conversation summary cache
- temporary state
- TTL-based session data

Qdrant collections:

```text
documents_v1
memories_v1
```

No Elasticsearch, Milvus or MongoDB is added in V1.

## 6. LLM Integration

Required configuration:

```text
LLM_BASE_URL
LLM_API_KEY
LLM_MODEL
```

Default local integration:

```text
Qwen3-0.6B
→ vLLM
→ OpenAI-compatible API
```

The Agent/RAG code must not directly depend on one model implementation.

## 7. Non-functional Requirements

- Traceability: explain where an answer came from and which nodes/tools executed.
- Recoverability: recoverable failures should not replay every completed Agent step.
- Separation of concerns: RAG, Agent, Memory, Tool, MCP, LLM and storage remain separate.
- Local reproducibility: Windows + WSL2 + Docker Desktop.
- Configuration isolation: no committed credentials.
- Honest scope: resume/README claims only implemented and verified functionality.

## 8. Explicit V1 Non-goals

Not implemented before V1 acceptance:

- Multi-Agent
- LoRA / QLoRA / SFT / fine-tuning
- Kubernetes
- OCR
- multimodal image/table understanding
- web browser/search Agent
- A2A
- autoscaling
- complex enterprise RBAC
- unlimited reflection

## 9. Module Roadmap

| Module | Scope | Completion gate |
|---|---|---|
| M0 | Skeleton + PostgreSQL + Redis + Qdrant | `/health` all UP |
| M1 | Document Pipeline | PDF/DOCX/TXT → chunks → Qdrant |
| M2 | RAG | Hybrid + Rerank + Citation |
| M3 | Agent Core | LangGraph + Tool Calling |
| M4 | Memory | Session + Long-term + Checkpoint |
| M5 | MCP | MCP Server + Client |
| M6 | Reliability | Retry + Timeout + Fallback + HITL |
| M7 | Evaluation | RAG/Agent/System Eval |
| M8 | Observability | Agent metrics + trace |
| M9 | Engineering wrap-up | Compose + README + Demo + resume |

Development order is fixed:

```text
M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9
```

## 10. V1 Final Acceptance

V1 is complete only when all conditions pass:

1. PDF/DOCX upload can be parsed and indexed.
2. RAG uses Dense + BM25 + Rerank.
3. Answers return document/page citations.
4. Agent completes at least three meaningful tool-call categories.
5. Multi-turn conversation uses Session Memory.
6. A new session can retrieve at least one long-term memory type.
7. Agent execution can resume from a persisted checkpoint.
8. Agent successfully calls the self-built MCP Server.
9. A protected write tool pauses for Human Approval.
10. Eval scripts and Prometheus/Grafana expose RAG/Agent/system metrics.

No new P0 feature is added until these conditions are satisfied.
