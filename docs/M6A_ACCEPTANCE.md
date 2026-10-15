# M6a Acceptance — 2026-10-15

**Decision: M6a Completed after actual Windows Docker integration test.**

Developer ran `scripts\check_m6a.bat` inside the existing API container.
Indexed synthetic contract document: `2119ff13-e1ee-4e49-926d-be275b7bf979`.

## Observed results

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

Actual MCP traffic reached the Document MCP Server and Qdrant (`points/scroll`
HTTP 200). Synthetic transient faults were injected in the **test process**,
not in the production FastAPI worker.

The real PostgreSQL metadata tool succeeded on its third attempt after two
injected failures. Exhausted failures returned a non-factual, source-free
fallback. A mixed multi-tool run preserved successful MCP source citations.

## Limits

- Functional fault-injection test; not a production chaos/load benchmark.
- Coroutine deadlines may not terminate underlying CPU worker threads.
- General handling of write-side effects is deliberately excluded.
- M6b introduces the durable Human Approval gate for `save_review_note`.
