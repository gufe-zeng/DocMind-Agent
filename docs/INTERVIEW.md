# Interview Framing

## 30-second project framing

> DocMind-Agent is a complex-document RAG Agent project. I separate document ingestion, hybrid retrieval, Agent workflow, memory, MCP, evaluation and observability into explicit modules instead of putting everything inside one prompt loop. PostgreSQL owns durable structured state, Redis owns session context, Qdrant owns semantic document/memory retrieval, and generation is decoupled through an OpenAI-compatible endpoint.

## What M0 proves

M0 proves:

- reproducible Docker-based infrastructure;
- explicit PostgreSQL/Redis/Qdrant ownership;
- FastAPI service boundary;
- dependency health diagnostics;
- environment-based configuration;
- frozen V1 architecture and module boundaries.

Do **not** claim RAG, Agent, Memory or MCP functionality before the corresponding module acceptance tests pass.
