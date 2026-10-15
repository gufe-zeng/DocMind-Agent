# RAG Design

Status: **M1 complete; M2a accepted; M2b code implemented, local acceptance pending**.

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

## M2b implementation

- `app/rag/reranker.py`: ModelScope BGE Cross-Encoder, local CPU ONNX and Top-K reranking.
- `app/rag/citation.py`: deterministic evidence labels and reference-ID verification.
- `app/llm/client.py`: model-independent OpenAI-compatible chat client.
- `app/rag/pipeline.py`: grounded question answering and fail-closed citation handling.
- `scripts/check_reranker.bat`: genuine model download and CPU inference.
- `scripts/check_m2b.bat`: real RAG + mocked LLM citation checks.
- `scripts/check_m2b_live.bat`: actual vLLM integration.

The current scope is evidence grounding, not guarantee of semantic faithfulness. See [M2 Guide](M2_GUIDE.md).
