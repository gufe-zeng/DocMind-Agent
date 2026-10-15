# M6 — Reliability and Human-in-the-Loop

Status: **M6a Completed (2026-10-15); M6b in development.**

## M6a — Bounded Read-Only Tool Runtime

### Failure policy

| Tool category | Timeout | Max retries |
|---|---:|---:|
| PostgreSQL metadata | 15 s | 2 |
| Hybrid RAG and scoped Qwen summary | 90 s | 2 |
| Deterministic extraction | 45 s | 2 |
| MCP metadata | 40 s | 2 |
| MCP page / clause read | 60 s | 2 |
| MCP hybrid document search | 90 s | 2 |

Only transient connection, transport and timeout failures qualify for
retry; HTTP 429/500/502/503/504 may also qualify. Unregistered tools,
invalid arguments, data-provenance violations and software errors are
not quietly converted into fallback success.

An initial call plus at most two retries means **three total attempts**.
On exhaustion, a tool returns `tool_unavailable`, an explicit inability
to confirm the facts, and **no citation**. A multi-tool run can return
`partial` while retaining the other tool's valid sourced answer.

### State and API

The Agent preserves the frozen `MAX_AGENT_TOOL_STEPS=8`. Retries contribute
only to `retry_count`; the outer graph's `current_step` does not increase.
`reliability_events` holds a structured outcome for every attempted
read-only tool: `tool`, `status`, `attempts`, `retries`, `timeout_seconds`,
`duration_ms`, and a sanitized `error_type` for exhausted retries.
The existing `/v1/chat` response exposes this as `tool_events`.

**Limitation:** coroutine deadlines do not forcibly kill CPU inference
threads already spawned via `asyncio.to_thread`. This is bounded
best-effort local execution, not exactly-once distributed processing.

### Local acceptance — Windows CMD

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m6a.bat
```

Expected outputs:

```text
PASS DocMind API ready
PASS real Agent -> MCP tool with success trace
PASS two retries recover real PostgreSQL metadata read
PASS exhausted retries return fail-closed no-facts fallback
PASS partial multi-tool result keeps real MCP citations
PASS bounded tool timeout and 2 retry limit
M6a PASS
M6a reliability validation passed.
```

The test **passed on 2026-10-15**. It uses real PostgreSQL/Qdrant/MCP for normal calls and injects
transient errors in its separate smoke-test Python process only.
No debug fault-injection API or additional network port is introduced.

## M6b — Protected Write and Human Approval (not yet implemented)

Frozen V1 write: `save_review_note(...)`. The Agent must create a durable
pending approval and **not write the note** until the user approves.
Frozen endpoint: `POST /v1/approvals/{approval_id}`.

Approval and rejection paths, repeated-decision idempotency, durable
PostgreSQL state, and graph continuation must pass independent local
acceptance before marking M6b completed. General write tools must not
be routed through the read-only retry executor.
