# M7 — Evaluation

Status (2026-10-15): **M7a and M7b Completed via local Docker validation; M7c implemented, local BASE/LIVE validation pending.**

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

## M7b — Agent task/tool evaluation (accepted 2026-10-15)

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
| Failure Rate | Fraction with failed HTTP/transport or explicit `partial`, `tool_unavailable`, `citation_unverified`, `step_limit`, etc. Distinct from the complement of Task Success Rate. |

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
**Accepted on 2026-10-15:** seven fixture cases answered, all task/tool/MCP
selection metrics at 1.0, eight observed tool calls with Tool Success Rate=1.0,
Average Agent Steps=1.1428571428571428 and Failure Rate=0.
See [M7b acceptance](M7B_ACCEPTANCE.md).

## M7c — System evaluation (implementation available; local acceptance pending)

Runners: `scripts\\check_m7c.bat` (BASE, no Qwen) and
`scripts\\check_m7c_live.bat` (BASE plus real Qwen probe).
Aggregation: `eval/system_eval.py`.
Both use a synthetic contract and the existing frozen V1 API. No new public
endpoint or production Prometheus/tracing instrumentation is introduced.

BASE profiles four *serial* Agent HTTP requests (PostgreSQL metadata, MCP
clause lookup, MCP search, and a two-tool MCP request). It measures
`perf_counter` wall-clock **Agent E2E latency** around each request and reads
the existing `tool_events.duration_ms` for **read-only tool latency**,
including transport overhead/retries. Tool-event coverage and counts are
explicitly reported. Per-tool, aggregate mean/p50/p95 use milliseconds and
nearest-rank p95; only four HTTP samples, not a load test.

BASE also calls the **real** `hybrid_search` and `rerank_hits` functions
directly against the synthetic document and samples their own wall-clock
**retrieval latency** and **BGE rerank latency** separately. These are
in-container standalone stage measurements; they are **not** internally
attributed timings from the Agent HTTP requests and must not be summed to
explain HTTP E2E latency. Cache warm/cold state is uncontrolled.

BASE only uses a known rule/MCP-only request plan, so the validated Agent
routes do not call an LLM. It reports `agent_request_llm_calls=0` and
zero Agent-request token counts **only when all routes are verified**. For
unverified requests these fields are `null`, not fabricated zeros.

LIVE (optional second validation) additionally runs the complete RAG
pipeline against the same synthetic fixture with real Qwen. The evaluator
wraps its **own process's** `pipeline.complete_chat` to count actual
requests; the original client still performs the real API call. Usage
comes from the OpenAI-compatible endpoint's response: prompt/completion
token counts are `null` when unavailable. LIVE requires a cited answer,
exactly one model call, and real token counts to pass. This probe is
**not** a measurement of model-assisted Agent tool planning or complete
Agent HTTP response token usage.

Windows CMD (BASE, no Qwen):

```cmd
cd /d E:\\project\\DocMind-Agent
git pull
docker compose up -d --build api
scripts\\check_m7c.bat
```

Expected:
```text
M7c SYSTEM BASE PASS
M7c system base validation passed.
```

With the existing `llm-serving-ops` Qwen/vLLM endpoint running on host
port 8000, run LIVE separately:

```cmd
scripts\\check_m7c_live.bat
```

Expected:
```text
M7c SYSTEM LIVE PASS
M7c system live validation passed.
```

**Acceptance rule:** Do not mark M7c Completed until both BASE and LIVE
have actually passed on the local Docker environment. The top-level
`scripts/run_eval.bat` remains reserved until M7 acceptance.

## General boundaries

- All gold text is synthetic; no customer/private legal documents are needed.
- Deterministic checks cannot establish semantic faithfulness.
- Shared Qdrant makes performance metrics dependent on historical data.
- No production-level throughput or concurrency claims from these smoke tests.
