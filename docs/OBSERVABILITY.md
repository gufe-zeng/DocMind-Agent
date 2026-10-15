# M8 — Agent Observability and Docker build caching

**Status: M8 core accepted by real local Docker on 2026-10-15; optional Grafana dashboard verification pending.**
M7a, M7b and M7c completed their local smoke gates on 2026-10-15.
M8 reuses the frozen V1 API. It does not add a trace-read HTTP endpoint
or expose confidential document contents in telemetry.

## 1. Request and graph trace contract

The existing `POST /v1/chat` returns `request_id`, `session_id`,
and the new `trace_id`. `POST /v1/approvals/{approval_id}` additionally
returns a `request_id` and `trace_id` without changing approval semantics.
The ID for an approval resume differs from the ID for the original paused
chat request. Both records share the same session ID when applicable.

A successful or failed validated endpoint invocation inserts one row
into PostgreSQL `agent_traces` (migration `004_agent_traces.sql`):

- `trace_id`, `request_id`, optional `session_id`, fixed operation name;
- HTTP and Agent terminal status, start/end timestamps, handler duration;
- LangGraph `route`, `decide`, `call_tool`, `synthesize` spans,
  with node start/end time, outcome and allowlisted tool identifier;
- the M6 read-only `tool_events` with retry attempts, type-only failures
  and duration; tool names and graph steps;
- model call attempts and prompt/completion tokens **only when available**.

The trace does **not** persist raw user requests, model prompts, LLM replies,
document excerpts, filenames, credentials, or memory contents. Errors
record exception **class names**, not error messages. Long-term retention,
deletion and access control are not implemented in this local demo.

Failure of the trace database write is observable as
`agent_trace_store_failures_total` and in the API logs. Telemetry
failures do not turn a successful legal-document query into a fabricated
tool failure. M8 local acceptance asserts PostgreSQL writes actually occur.

**Boundary:** FastAPI schema-validation errors rejected before endpoint
execution are not yet counted as an Agent endpoint invocation; these are
separate framework-level HTTP errors. Model token totals are nullable if
usage cannot be determined. LangGraph interrupted-node trace records
are generated for the interruption and for the later resume request.

## 2. Prometheus metrics

These are exported by the existing `GET /metrics` endpoint:

| Metric family | Measurement |
|---|---|
| `agent_requests_total`, `agent_success_total`, `agent_failures_total` | Per chat/approval request outcome, fixed `operation` label |
| `agent_steps` | LangGraph tool-step distribution |
| `agent_e2e_latency_seconds` | HTTP endpoint handler wall time, excluding trace DB insert |
| `tool_calls_total`, `tool_failures_total`, `tool_latency_seconds` | Real M6 read-only events and retries by allowlisted tool |
| `rag_latency_seconds` | Complete evidence-grounded RAG pipeline |
| `retrieval_latency_seconds` | Direct hybrid Dense/BM25/RRF stage |
| `rerank_latency_seconds` | Direct BGE inference stage |
| `llm_calls_total`, `llm_failures_total` | Actual OpenAI-compatible chat attempts and failures |
| `llm_prompt_tokens_total`, `llm_completion_tokens_total` | Only provider-reported token usage |
| `agent_trace_store_failures_total` | PostgreSQL trace persistence errors |

Prometheus labels contain no UUIDs, queries or exception strings. Timer
histograms are process-local and restart from zero on an API restart;
PostgreSQL trace history persists. Direct in-container evaluation scripts
(M7c) run in their **own Python process**, so their measurements are
not automatically part of the API process's `/metrics` scrape.

## 3. M8 local acceptance — one image build only

Keep existing PostgreSQL, Redis, Qdrant and embedding cache running.
Use **Windows CMD**:

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m8.bat
```

The BAT script uploads a synthetic contract, exercises real PostgreSQL
and MCP reads, requests/approves a protected review-note write, checks
`/metrics` and the trace table, then restarts **only the API container**.
A second phase verifies trace durability and newly emitted metrics.
**No Qwen is required, no Docker volumes are deleted and no second
`--build` is needed.**

Expected footer after local validation:

```text
M8 PREPARE PASS - restart only API and verify persisted traces
PASS M8 PostgreSQL Agent traces survive real API restart
PASS new requests produce traces after API restart
PASS Prometheus instrumentation active after API restart
M8 OBSERVABILITY PASS
M8 Observability validation passed.
```

**Observed on 2026-10-15:** both phases passed, including `M8 OBSERVABILITY PASS` after API restart. See [M8 acceptance](M8_ACCEPTANCE.md).

## 4. Optional Prometheus/Grafana dashboard (requires image downloads)

Opt in **without rebuilding the API image**:

```cmd
set DOCMIND_GRAFANA_ADMIN_PASSWORD=choose-a-local-password
docker compose -f compose.yaml -f compose.observability.yaml up -d prometheus grafana
scripts\check_m8_dashboards.bat
```

Browse `http://127.0.0.1:3091` (Grafana) or
`http://127.0.0.1:9091` (Prometheus), both bound to loopback.
The Grafana dashboard is provisioned from
`deploy/observability/grafana/dashboards/docmind-m8.json`.
The optional images are fetched once over the network if absent.
Do not expose the demo API or these monitoring ports publicly.

## 5. Docker rebuild optimization

The previous Dockerfile copied all source **before** running
`pip install .`; every Python change therefore invalidated the costly
dependency install layer (the user observed a ~405.6-second rebuild).

The M8 Dockerfile instead:

1. copies **only `pyproject.toml`** and extracts its runtime dependency list;
2. installs third-party dependencies in a cacheable layer;
3. copies application, scripts, migrations and README **afterward**;
4. installs the local project wheel with
   `pip install --no-deps --no-build-isolation .`;
5. validates `eval`, M8 trace imports and psycopg binary backend.

The **first** use of the rearranged Dockerfile may still pay the entire
installation cost once. With unchanged `pyproject.toml` and a preserved
Docker BuildKit cache, subsequent source-only rebuilds can reuse the
dependency layer. Do not use `--no-cache` for normal development.
This optimizes **Docker rebuilds**, not the separate 172–259-second
BGE CPU rerank timings seen during M7c.

## 6. Scope not yet covered

There is no distributed OpenTelemetry collector, cross-service span
propagation into the stdio MCP subprocess or remote Qwen server, secure
multi-tenant trace reader, full production authorization, or sustained
load test. These remain explicit deployment limitations, not M8 claims.
