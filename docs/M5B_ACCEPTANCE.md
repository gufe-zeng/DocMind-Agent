# M5b Acceptance Record — 2026-10-15

**Decision: M5b Completed; M5 Completed (local functional acceptance).**

The developer ran `scripts\check_m5b.bat` after rebuilding the Docker API.
Both Windows-host `http://127.0.0.1:8090/health` and in-container
`http://127.0.0.1:8000/health` returned HTTP 200 and
`status=ok` for PostgreSQL, Redis and Qdrant.

The acceptance test indexed two fixtures:

- TXT contract: `9b38309b-feb8-4425-bc10-503f67ef9136`
- Two-page PDF: `263f7840-1e00-4a55-82f7-44909f524745`

## Real Agent-to-MCP execution

| Agent tool (`tools_called`) | MCP tool (`mcp_tools_called`) | Observed result |
|---|---|---|
| `mcp_find_clause` | `find_clause` | Contract breach clause, `[S1]`, PASS |
| `mcp_get_document` | `get_document` | Indexed TXT metadata, PASS |
| `mcp_get_document_page` | `get_document_page` | Actual PDF page 2 text and page provenance, `[S1]`, PASS |
| `mcp_search_documents` | `search_documents` | Hybrid RAG evidence, `[S1]`, PASS |
| `mcp_get_document` then `mcp_find_clause` | `get_document` then `find_clause` | Sequential LangGraph tools, source citation, PASS |

Full flow verified: `POST /v1/chat` → LangGraph → typed tool registry →
official MCP stdio ClientSession → independent Document MCP Server
→ real PostgreSQL/Qdrant/source evidence → final Agent response.

Console output:

```text
PASS DocMind API readiness at 127.0.0.1:8000
PASS Agent -> MCP find_clause source citation
PASS Agent -> MCP get_document metadata
PASS Agent -> MCP get_document_page PDF provenance
PASS Agent -> MCP search_documents Hybrid RAG evidence
PASS LangGraph multi-tool MCP sequence and citations
M5b AGENT MCP PASS
M5b Agent MCP validation passed.
```

## Previous failure and resolution

The first attempt failed with `httpx.ConnectError` during fixture upload,
before any MCP invocation. The API had just been rebuilt; a 90-second
`/health` readiness probe was added to the M5b smoke test.
The passing rerun confirms connection readiness, but does not prove
the root cause was exclusively a startup race.

## Acceptance boundaries

- M5a: official MCP stdio initialize / tools list / tools call accepted separately.
- M5b: actual Agent-to-MCP integration accepted here.
- Tests use read-only tools, deterministic explicit-MCP routing and source excerpts.
- No public/authenticated remote MCP hosting, high-volume load testing, or
  production retry/timeout/fallback/HITL guarantees are claimed.
- M6 adds reliability and approval-protected write actions.

**Next: M6 — Timeout, bounded retry, fallback and HITL.**