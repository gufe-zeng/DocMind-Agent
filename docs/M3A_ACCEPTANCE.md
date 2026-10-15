# M3a Acceptance — 2026-10-15

**Decision: Completed (local functional acceptance).**

The developer ran `scripts\check_m3a.bat` in their Windows / Docker Desktop environment.

## Observed steps

1. Uploaded and indexed the synthetic contract:
   `a6db983d-c594-4d6b-8af3-56e0b252ad8c`.
2. `POST /v1/chat` for document listing executed the real
   `query_document_metadata` tool and returned:
   `m3a_contract.txt（indexed，1 个片段）`.
3. `POST /v1/chat` for payment timing selected the real
   `search_documents` tool, which delegates to the accepted M2 RAG stack.
4. Live Qwen3-0.6B returned `付款期限是三十天 [S1]。`.
5. The citation resolved to `m3a_contract.txt`, chunk
   `4589b87a-6bac-5937-98c9-04f9074dc7c0`.
6. Terminal output: **`M3a PASS`** and
   **`M3a validation passed.`**.

## Acceptance boundary

This establishes that the LangGraph routing/loop/typed registry can invoke
the real PostgreSQL and RAG tools and preserve source references through the
HTTP API. It does **not** establish autonomous planning by an LLM,
entity extraction, document summary, session memory, durable checkpoints,
MCP, or advanced HITL behavior.

**Next:** M3b entity extraction, scoped summary, and bounded LLM-assisted
multi-tool planning with auditable rule fallback.
