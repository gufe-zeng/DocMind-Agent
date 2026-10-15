# M4b Acceptance — 2026-10-15

**Decision: M4b Completed; full M4 Completed (local functional acceptance).**

Developer executed both real Docker tests using the existing PostgreSQL, Redis, Qdrant, ModelScope embeddings and live Qwen.

## Test 1: Cross-session long-term preference

- Command: `scripts\check_m4b.bat`.
- Demo user UUID: `3e624737-e56c-4eb8-b38b-b9f53e5c3101` (caller-supplied, not authenticated).
- Indexed `m4b_preference.txt`: document `0a732463-dde2-430a-9530-693ced8f81ac`.
- Explicit preference saved, PostgreSQL record: `f50bd8fb-31bc-5b89-b45e-bcb201ebfc38`.
- New session returned a live Qwen, cited, evidence-scoped summary with the previously saved format hint.
- Repeated saving reused the same memory identity.
- A different demo user ID did not retrieve the saved preference.
- Outputs: `PASS explicit preference save`, `PASS PostgreSQL structured memory`,
  `PASS cross-session semantic preference recall`,
  `PASS idempotent upsert and user-isolated semantic recall`,
  **`M4b MEMORY PASS`**.

## Test 2: Checkpoint interruption and resume

- Command: `scripts\check_m4b_resume.bat`.
- Checkpoint thread UUID: `4d58a5c0-f38f-422d-a83c-58d998a7550b`.
- Node pending at interruption: `('call_tool',)`.
- A fresh PostgreSQL checkpoint connection and graph resumed the pending
  `query_document_metadata` tool and produced a list of indexed documents.
- Outputs: `PASS PostgreSQL saved pre-tool interruption`,
  `PASS independent graph resumed only pending tool and completed`,
  **`M4b CHECKPOINT PASS`**.

## Scope and limits

Cross-session memory was limited to whitelisted, explicitly saved contract
analysis formatting preferences. Demo user IDs are not authenticated.
Checkpoint continuation was verified only for a deliberately paused
read-only tool, not exactly-once external writes or arbitrary worker crashes.
Answer citation IDs are verified for provenance linking, not entailment.
Retrieval quality and answer faithfulness benchmarks remain M7.

**Next:** M5 standard MCP Server + Client transport and Agent integration.