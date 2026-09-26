# RAG Design

Status: **pipeline frozen; implementation scheduled for M1/M2**.

```text
Document:
Parse → Normalize → Chunk → Metadata → Embed → Qdrant

Query:
Rewrite → Metadata Filter
        → Dense Retrieval ─┐
        → BM25 Retrieval ──┤
                           → RRF → Rerank → Evidence → Answer + Citation
```

M1 owns ingestion/indexing.  
M2 owns hybrid retrieval, RRF, reranking and citation.

A retrieved chunk must preserve enough source metadata for deterministic citation reconstruction.
