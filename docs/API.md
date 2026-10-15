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

## M3 — Agent chat (M3a accepted; M3b pending local acceptance)

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

`query` is required (1–2000 chars); `document_id` and `session_id`
are optional UUIDs. If omitted, `session_id` is generated as a correlation
identifier **only**; conversation persistence starts in M4.

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
**M3b implemented, local validation pending**: `scripts\check_m3b.bat`.
**Not yet implemented:** M4 conversation memory/checkpoints; M5 MCP; M6 HITL/retries.

## M4 — Sessions (not implemented)

```http
GET /v1/sessions/{session_id}
```

## M6 — Human-in-the-loop approval (not implemented)

```http
POST /v1/approvals/{approval_id}
```

No additional public APIs are added without a corresponding frozen V1
requirement.
