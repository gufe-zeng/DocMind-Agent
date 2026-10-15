# DocMind-Agent V1 Memory Design

Status: **M4a code implemented (local acceptance pending); M4b planned**.

The frozen architecture separates four distinct state lifetimes:

| Layer | Storage | Implementation status |
|---|---|---|
| Working state | LangGraph AgentState | Implemented M3 |
| Session history | Redis with TTL | M4a implemented, pending live test |
| Durable graph checkpoint | LangGraph PostgreSQL AsyncPostgresSaver | M4a implemented, pending live test |
| Long-term reusable memory | PostgreSQL `memories` + Qdrant `memories_v1` | M4b planned |

## M4a — Redis short-term session memory

- Key: `docmind:session:{session_uuid}`.
- Idle TTL: 3600 seconds; keeps the last 6 turns.
- Each turn stores original question, resolved question, bounded answer, status and timestamp.
- Stores the last document UUID, so a follow-up can omit `document_id`.
- Short co-reference questions such as `如果逾期呢？` are expanded from the previous user question **only when the document remains the same**. The expansion is deterministic; no new LLM query-rewrite call is claimed.
- Session request lock uses Redis NX+EX and token-checked atomic deletion. The default 300-second lease is suitable for local demo, not a complete distributed worker locking system.
- `GET /v1/sessions/{session_id}` reads only bounded conversation history. No raw retrieved document passages or intermediate model traces are stored in Redis.

## M4a — PostgreSQL graph checkpoints

- Uses official `langgraph-checkpoint-postgres` `AsyncPostgresSaver`.
- Connection initialized during FastAPI lifespan; `setup()` creates/migrates LangGraph's checkpoint tables.
- Compiled StateGraph uses this checkpointer, and each chat uses `thread_id=session_id`.
- New turns explicitly reset prior turn-specific fields (tool results, step count, citations, status) before graph execution, while preserving the thread's durable checkpoint history.
- The independent connection test verifies persisted checkpoint readback from PostgreSQL.
- **Do not claim interruption/resume correctness yet**: a dedicated interrupted-node resume test is scheduled for M4b.
- Checkpoints can contain raw tool results/evidence and remain in PostgreSQL; sensitive-document retention and deletion controls require additional work.

## M4a acceptance (Windows CMD)

```cmd
git pull
docker compose up -d --build api
scripts\check_m4a.bat
```

The test uploads a synthetic contract, asks about its payment deadline,
asks `如果逾期呢？` using only `session_id`, confirms `context_applied`,
checks GET session history, Redis TTL, and native PostgreSQL checkpoint
from a separate connection. Expected `M4a PASS`.

Optional manual restart check:

```cmd
docker compose restart api
curl --noproxy "*" http://127.0.0.1:8090/v1/sessions/SESSION_ID_FROM_M4A_OUTPUT
```

Expect the same recent turns while the Redis TTL has not expired.

## M4b — planned, not implemented

- Store only **explicitly requested** reusable user preferences and confirmed facts, not arbitrary dialogue snippets.
- PostgreSQL structured memory with provenance and timestamps.
- `memories_v1` Qdrant semantic recall with per-user scope and no cross-user leakage.
- Document-derived text remains in the source document store, never promoted automatically into personal long-term memory.
- Validate real checkpoint resume after a deliberate graph interruption.
- Consider permission checks, memory deletion/retention, and session-summary consolidation; do not assert production security without them.

## Security and scope

M4a is a **local developer demo** with no authentication, authorization or
session ownership verification. A known session UUID can retrieve its recent
answers. Do not expose host port 8090 on an untrusted/public network.
PostgreSQL checkpoint retention is separate from Redis TTL expiry.
