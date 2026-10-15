# RAG Design

Status: **M1 ingestion complete; M2a Dense+BM25+RRF implemented, local acceptance pending**.

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


## M2a implementation

- `app/rag/retriever.py`: indexed-chunk payload scan, Dense Qdrant and RRF orchestration.
- `app/rag/sparse.py`: BM25 with Chinese character bigrams and positive IDF.
- `app/rag/fusion.py`: deterministic Reciprocal Rank Fusion.
- `scripts/check_m2a.py`: real Docker/Qdrant hybrid retrieval smoke test.

M2a outputs ranked source evidence, **not** reranked, generated or citation-verified answers. See [M2 Guide](M2_GUIDE.md).
