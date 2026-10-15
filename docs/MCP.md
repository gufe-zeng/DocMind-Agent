# M5 — Model Context Protocol (Document MCP Server + Client)

Status: **M5a implemented and unit-tested; local protocol acceptance pending**.

## Frozen V1 requirements

The self-built Document MCP Server exposes exactly these four tools:

| Tool | Arguments | Backend | Response |
|---|---|---|---|
| `search_documents` | `query`, optional `document_id`, `limit` | M2 Hybrid Retrieval | Ranked source chunks (without generating an answer) |
| `get_document` | `document_id` | PostgreSQL `documents` | File/index metadata |
| `get_document_page` | `document_id`, `page` | Qdrant indexed PDF chunks | Actual page source text and IDs |
| `find_clause` | `document_id`, `keyword`, `limit` | Qdrant indexed chunks | Exact lexical matches and provenance |

Neither arbitrary tool execution nor document modification is possible
through this MCP Server. All document selectors are UUID validated.

## M5a — Separate-process MCP transport

```text
Official MCP ClientSession (test process)
       ↓ stdio JSON-RPC initialize / tools/list / tools/call
mcp_server.server (FastMCP subprocess)
       ↓ validated document_tools handlers
PostgreSQL / Qdrant / M2 Dense+BM25+RRF
       ↓ structured source-aware results
Official MCP ClientSession
```

The server is run through `python -m mcp_server.server` and uses the
official `mcp` SDK, `FastMCP` and `stdio` transport. The test launches
it using `StdioServerParameters` and `stdio_client` from the same SDK.

The M5a test uses synthetic PDF/TXT fixtures, indexes them via the existing
FastAPI upload pipeline and calls **all four tools** through the
separate subprocess. It verifies:

1. Protocol initialization and discovery of exactly four names.
2. PostgreSQL metadata using `get_document`.
3. Real PDF page 2 with `get_document_page` and page metadata.
4. Clause text and original chunk ID using `find_clause`.
5. Dense/BM25/RRF evidence with exact document filtering from
   `search_documents`.

All returned text is bounded (500 characters per evidence chunk), and
server-side scans have a hard 200-chunk bound; a scan over the cap fails
rather than silently omitting pages. This is suitable for the V1 demo,
not a high-volume or untrusted multi-tenant production MCP service.

### M5a local acceptance — Windows CMD

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m5a.bat
```

Expected output:

```text
PASS MCP initialize + discover four official tools
PASS get_document metadata through MCP
PASS get_document_page with real PDF page provenance
PASS find_clause source-anchored lexical result
PASS MCP search_documents Dense/BM25/RRF evidence
M5a MCP PASS
M5a validation passed.
```

ModelScope BGE model files are already cached in the persistent Docker
volume; the MCP server does not need a new GPU or the live Qwen vLLM.
The Python MCP SDK package is a new dependency, so rebuild the API image.

### M5a limitations

- This is a **local stdio MCP Server**, not a remote public HTTP MCP host.
- The four tools are read-only and deliberately exclude arbitrary filesystem
  browsing and SQL execution.
- `get_document_page` is PDF-specific; TXT/DOCX return an explicit
  `page_not_applicable` status.
- `search_documents` returns retrievable evidence, not Qwen-generated
  factual answers; Agent synthesis is a separate concern.
- No user authentication/authorization is present in the local demo.
  Do not grant this subprocess access to untrusted users.

## M5b — Planned after M5a acceptance

M5b adds an adapter under `app/mcp_client/` and allows selected
LangGraph business tool calls to route through MCP ClientSession.
The checkpoint will verify that a **real Agent turn** invoked the MCP
Server and produced a source-grounded answer or metadata result.

Failure surfaces and bounded transport timeouts are exercised during
M5b. General retry/fallback/HITL policies stay in M6.
