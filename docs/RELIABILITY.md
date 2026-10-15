# M6 — Reliability and Human-in-the-Loop

Status: **M6a Completed (2026-10-15); M6b implemented, local acceptance pending.**

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

## M6b — Protected Write and Human Approval (local acceptance pending)

Frozen V1 write: `save_review_note(...)`. The Agent must create a durable
pending approval and **not write the note** until the user approves.
Frozen endpoint: `POST /v1/approvals/{approval_id}`.


### Actual protected-write lifecycle

1. `POST /v1/chat` with an **explicit** `保存审核备注：...` command, an
   indexed `document_id` and a local-demo `user_id` creates a PostgreSQL
   approval row in `pending` state. The note does **not** enter `review_notes`.
2. The actual LangGraph `call_tool` node invokes official `interrupt()`
   before `save_review_note` executes. The paused state is written to
   PostgreSQL using the accepted M4 `AsyncPostgresSaver`.
3. The response is `status=approval_required`, with `approval_id`,
   `approval_required=true`, `steps=0` and no executed tools.
4. `POST /v1/approvals/{approval_id}` accepts `approve` or `reject`,
   an exact `session_id`, and an exact demo `user_id`. The decision is
   first persisted as `approved` or `rejected`.
5. `Command(resume=...)` continues that **same** LangGraph checkpoint.
   If approved, the resumed node performs a single transactional write
   into `review_notes`; if rejected, no note is written.
6. Replayed approvals return the same persistent result. The unique
   `approval_id` and deterministic review-note ID protect against duplicate
   inserts after HTTP retries or graph checkpoint replay. An opposite
   decision yields HTTP 409.

PostgreSQL owns `approvals` and `review_notes` using migration
`003_approvals.sql`. The database records the pending request separately
from the approved note. The existing read-only registry intentionally
**does not expose** `save_review_note`: only the interrupted LangGraph
path can execute this protected write. No read-only retry policy is
applied to the write.

### M6b local acceptance — Windows CMD

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m6b.bat
```

The BAT script first uploads/indexes a synthetic contract, requests a
protected note, and verifies `pending` plus zero stored notes. It then
**restarts only the API container** (not PostgreSQL, Redis or Qdrant),
and resumes the pending graph from the durable checkpoint. It checks
approved save, duplicate approval, conflicting decision, rejection,
duplicate rejection, cross-user/session denial and invalid note syntax.

Expected terminal output:

```text
PASS pending approval persisted and no pre-approval write
PASS LangGraph interrupted before save_review_note
PASS mismatched scope denied and paused thread protected
M6b PREPARE PASS — restart API and resume the checkpoint
PASS approval + paused graph survive API container restart
PASS approved note saved once after LangGraph resume
PASS approval replay idempotent; conflicting decision rejected
PASS reject/replay never writes and later approval blocked
PASS malformed write request rejected before creating approval
M6b HITL PASS
M6b HITL validation passed.
```

**Operational boundary:** This local demonstration has no authenticated
user identities or RBAC. `user_id` and `session_id` are caller-supplied
UUIDs, not a security boundary against malicious clients. Keep the API
local-only. A production system must add real identity verification,
authorization, retention/deletion and observability before exposing
protected writes.

**Acceptance rule:** M6b must not be marked Completed until both Docker
phases have passed after a real API restart.
