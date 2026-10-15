# M7 — Evaluation

Status (2026-10-15): **M7a Completed via local Docker validation; M7b implemented, local validation pending; M7c planned.**

M7 reuses the frozen V1 interfaces and does **not** add a public API.
Synthetic smoke tests are evidence of a functioning evaluation pipeline,
not research-quality effectiveness/faithfulness measurements.

## M7a — Document retrieval evaluation (accepted)

Runner: `scripts\check_m7a.bat`; gold:
`eval/datasets/m7a_retrieval.json`.

- Unit of retrieval relevance: **document** (distinct document IDs), not chunks.
- Recall@K: mean fraction of gold relevant document IDs found among first K distinct retrieved document IDs.
- MRR@K: mean reciprocal rank of the first relevant document in the top K distinct document IDs.
- Citation provenance test: checks referenced source IDs exist; **not** semantic entailment.

Observed on 2026-10-15: 3 synthetic cases, Recall@3=1.0,
MRR@3=1.0, 63 retrieved candidate chunks outside the fixture.
See [M7a acceptance](M7A_ACCEPTANCE.md).

**Limitations:** the long-lived Qdrant collection includes prior smoke
documents. There is no isolated fixed candidate corpus, so global rankings
and scores can change across runs. The pass gate proves execution and metric
integrity; it does not impose a task-quality threshold.

## M7b — Agent task/tool evaluation (local validation pending)

Runner: `scripts\check_m7b.bat`; gold:
`eval/datasets/m7b_agent.json`; metric code: `eval/agent_eval.py`.

The fixture indexes synthetic TXT/PDF documents, runs real
`POST /v1/chat` requests with independent sessions and scoped document IDs,
and checks the rule-driven LangGraph tools and actual stdio MCP tools.
No Qwen is needed. Cases exercise metadata, limited-rule field extraction,
MCP document/page/clause/search, and two-tool MCP execution.

Metrics:

| Metric | Operational definition |
|---|---|
| Task Success Rate | Fraction of fixture cases matching expected response status, explicit answer substrings/entity values, source provenance, and step constraints. **Independent** of tool-choice scoring. |
| Tool Selection Accuracy | Fraction whose executed tool **set** exactly matches fixture tools (duplicates invalid); order is not scored. |
| MCP Tool Selection Accuracy | Exact match of reported MCP protocol-tool sequence to the expected MCP list. |
| Tool Success Rate | Successful `tool_events` (status `ok`, aligned by tool and bounded attempts) divided by observed read-only tool calls. Missing events count as failures; no observed attempts yields `null`. |
| Average Agent Steps | Mean valid `steps` among HTTP-successful responses that report steps, excluding unavailable responses; count reported separately. |
| Failure Rate | Fraction with failed HTTP/transport or explicit `partial`, `tool_unavailable`, `citation_unverified`, `step_limit`, etc. Distinct from (1 - \text{Task Success Rate}). |

Source checks require real document/chunk IDs, legal `[S#]` source
identifiers and matching document/page scope. This evaluates deterministic
data/provenance contracts only. Neither an LLM-judge nor a human review of
legal answer correctness is included.

Windows CMD:

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m7b.bat
```

Expected success footer:

```text
M7b AGENT EVAL PASS
M7b Agent evaluation validation passed.
```

The Docker script reports case-level outcomes and all metric denominators.
**M7b is not Completed until the actual local run passes.**

## M7c — System evaluation (planned)

Required V1 measurements: Agent E2E latency, retrieval/rerank/tool
latencies, LLM calls and token usage. This must distinguish model-backed
requests from no-LLM MCP/metadata requests and disclose unavailable metrics
instead of silently setting them to zero.

The top-level `scripts/run_eval.bat` remains reserved until the complete
M7 benchmark suite is ready.

## General boundaries

- All gold text is synthetic; no customer/private legal documents are needed.
- Deterministic checks cannot establish semantic faithfulness.
- Shared Qdrant makes performance metrics dependent on historical data.
- No production-level throughput or concurrency claims from these smoke tests.
