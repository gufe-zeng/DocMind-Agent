# V1 API Contract

The V1 public API surface is frozen. Implementation is incremental.

## M0 — complete

```http
GET /health
GET /metrics
```

The health response includes PostgreSQL, Redis and Qdrant dependency status.

## M1 — document upload and indexing

### POST /v1/documents

- Request: `multipart/form-data`, field named `file`.
- Accepted: text-based PDF, DOCX, TXT.
- Size: 1 byte to 10 MiB.
- Effect: validate/parse file, persist original in a Docker volume, create
  a PostgreSQL `documents` record with status `uploaded`.
- This call **does not embed** the document.

```cmd
curl --noproxy "*" -X POST -F "file=@data/samples/sample_contract.txt" http://127.0.0.1:8090/v1/documents
```

Example `201 Created` response:

```json
{
  "document_id": "4ec81c88-c5ab-40f4-a36c-2b0f7d29e71e",
  "filename": "sample_contract.txt",
  "size_bytes": 400,
  "status": "uploaded"
}
```

Error responses: `400` missing filename/empty input; `413` too large;
`415` unsupported type; `422` invalid, unreadable or image-only content;
`503` unavailable storage.

### POST /v1/documents/{document_id}/index

- Request: no body.
- Effect: atomically claim document indexing in PostgreSQL; load persisted
  source; parse and chunk; compute Chinese BGE embeddings on CPU; ensure the
  `documents_v1` Qdrant collection exists with 512-dimensional cosine
  vectors; replace document points and verify stored point count; persist
  status and chunk count in PostgreSQL.
- The first request may take time to download the ONNX embedding model.

```cmd
set DOC_ID=4ec81c88-c5ab-40f4-a36c-2b0f7d29e71e
curl --noproxy "*" --max-time 600 -X POST http://127.0.0.1:8090/v1/documents/%DOC_ID%/index
```

Example `200 OK` response:

```json
{
  "document_id": "4ec81c88-c5ab-40f4-a36c-2b0f7d29e71e",
  "status": "indexed",
  "chunk_count": 1,
  "embedding_model": "BAAI/bge-small-zh-v1.5",
  "vector_size": 512
}
```

Error responses: `404` unknown document; `409` another active indexing
operation; `422` invalid document/chunk limit; `503` indexing failure.

### Storage after indexing

PostgreSQL: `documents` record, `status=indexed`, `chunk_count`.

Local original file: named Docker volume `documents-data`, stored by
document UUID; user-supplied filenames do not control storage paths.

Qdrant: collection `documents_v1`, each point payload contains
`document_id`, `filename`, `page` or `section`, `chunk_id`,
`chunk_index`, `start_offset`, `end_offset`, `text`,
`embedding_model`.

M1b smoke test: `scripts\check_m1b.bat`.

## M2 — Internal RAG query API (not a new HTTP endpoint)

M2 exposes the Python function:

```python
from app.rag.pipeline import answer_document_question, answer_to_dict

result = await answer_document_question(
    "服务验收后付款期限是多少天？",
    document_id="indexed-document-uuid",
)
response = answer_to_dict(result)
```

Return structure:

- `query`, `answer`, `status` (`answered`, `no_evidence`,
  `citation_unverified`, `insufficient_evidence`)
- `citation_valid`, `citations_used`
- `sources`: evidence ID, document ID, chunk ID, filename, page,
  section, evidence text and reranker score
- `retrieved_candidates`, `prompt_tokens`, `completion_tokens`

This will be consumed by the LangGraph runtime via the already frozen
`POST /v1/chat` endpoint in M3. It is not directly public in M2.

## M3 — Agent chat (accepted 2026-10-15)

```http
POST /v1/chat
Content-Type: application/json
```

Request:

```json
{
  "query": "根据合同，验收后付款期限是多少天？",
  "document_id": "uuid-of-an-indexed-document",
  "session_id": null
}
```

`query` is required (1–2000 chars); `document_id`, `session_id` and
M4b's local-demo `user_id` are optional UUIDs. From M4a, `session_id` is a real Redis short-term session
identifier, and LangGraph checkpoints share that thread ID. An omitted
session ID starts a new session. A short follow-up with the same ID reuses
its document context and may apply conservative query expansion.

Response:

```json
{
  "request_id": "generated-uuid",
  "session_id": "generated-uuid",
  "status": "answered",
  "intent": "search_documents",
  "answer": "根据合同，服务验收后付款期限是三十日。[S1]",
  "tools_called": ["search_documents"],
  "plan_source": "rules",
  "planner_fallback_reason": null,
  "steps": 1,
  "entities": [],
  "context_applied": false,
  "effective_document_id": "uuid-of-an-indexed-document",
  "memory_saved": null,
  "retrieved_memories": [],
  "memory_applied": false,
  "sources": [
    {
      "id": "S1",
      "document_id": "uuid-of-an-indexed-document",
      "chunk_id": "qdrant-chunk-uuid",
      "filename": "contract.txt",
      "page": null,
      "section": null,
      "evidence": "..."
    }
  ]
}
```

The values above are *illustrative*, not a recorded test result.

Current allowlist: `search_documents`, `query_document_metadata`,
`extract_entities`, `summarize_document`. Complex tasks may use a validated
model tool order and observable rule fallback. `entities` contains extracted
facts with `source_id` and `chunk_id`, if applicable.

Errors: `422` invalid request/tool input; `503` failed service/model
dependency. API returns JSON errors without exposing stack traces.

Check: `scripts\check_m3a.bat`.

**M3a accepted**: `scripts\check_m3a.bat`.
**M3b accepted**: `scripts\check_m3b.bat` (2026-10-15).
**Not yet implemented:** M4 conversation memory/checkpoints; M5 MCP; M6 HITL/retries.

## M4a — Session history (implemented, local acceptance pending)

```http
GET /v1/sessions/{session_id}
```

Response: session UUID, most recent document UUID, `turn_count`, bounded
`turns` with original user query, context-expanded query, answer/status/time,
`created_at`, `updated_at`, and `checkpoint_saved` flag.

Redis idle expiration: 3600 seconds; maximum 6 turns per session.
An expired/unknown session returns HTTP 404. Concurrent POST /v1/chat
requests using the same `session_id` return HTTP 409 while a session lock
is held (300-second time-limited lease).

Usage:

```cmd
curl --noproxy "*" http://127.0.0.1:8090/v1/sessions/your-session-uuid
```

To follow up without passing document_id again:

```json
{"query":"如果逾期呢？","session_id":"your-session-uuid"}
```

This is a local-development feature. Session IDs function as bearer tokens
and there is no access control yet. Do not expose this API to the internet.

M4b long-term preferences/semantic memory and workflow resume are not
yet implemented.


## M6 — Human-in-the-loop approval (not implemented)

```http
POST /v1/approvals/{approval_id}
```

No additional public APIs are added without a corresponding frozen V1
requirement.

## M4b — Opt-in format preference (accepted 2026-10-15)

No new endpoint. Save a whitelisted preference through `POST /v1/chat`:

```json
{
  "query": "请记住：以后合同分析按主体、金额、期限、风险、引用格式输出。",
  "user_id": "a-stable-demo-user-uuid"
}
```

The response uses `status=memory_saved` and includes a structured
`memory_saved` record. A new session can supply the same `user_id`,
an indexed document ID, and a document-analysis question. Recalled Qdrant
preferences are reported in `retrieved_memories`; `memory_applied=true`
means a whitelisted formatting hint was passed into a RAG tool. It does
not prove every heading was followed.

A caller-provided user UUID is not real authentication. Run locally only.
Other preference classes and arbitrary long-term personal facts are not
supported by this demo implementation.


## M5a — MCP interface (not HTTP REST)

The Document MCP Server is a separate **stdio** server process rather than
a new public FastAPI path. Tool discovery and calls use the MCP protocol.
Required names: `search_documents`, `get_document`,
`get_document_page`, `find_clause`. Each tool validates IDs, limits
returned source text and retains source metadata. `get_document_page`
is meaningful only for PDFs with real page numbers.

A dedicated SDK client smoke test is provided as `scripts\check_m5a.bat`.
M5b will connect LangGraph through a reusable client adapter.

## M5b — Agent MCP tool reporting (pending Docker acceptance)

Explicit MCP requests use the unchanged POST /v1/chat API. Example:

```json
{"query":"通过MCP查找违约责任条款","document_id":"indexed-document-uuid"}
```

The new `mcp_tools_called` array contains actual MCP tools such as
`["find_clause"]`. The original `tools_called` field instead includes
LangGraph registry names such as `["mcp_find_clause"]`.
Evidence results include deterministic source citations, source chunk IDs
and PDF page metadata where available. No MCP HTTP port was added.
