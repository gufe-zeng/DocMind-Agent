# M2 — Hybrid RAG Development Guide

Status: **M2a implemented; local validation pending**. M1a/M1b completed.

M2 scope is frozen as:
Query → Rewrite / Metadata Filter → Dense+BM25 → RRF → Rerank → LLM
→ Evidence-grounded Answer + Citation.

M2 will be accepted only after the full chain is implemented and tested.

## M2a — Dense + Chinese BM25 + RRF

M2a focuses on candidate retrieval before adding another model.

```text
User query
     ├── Dense: BGE-small-zh-v1.5 (ModelScope ONNX, CPU)
     │           ↓ Qdrant query_points() cosine Top-K
     │
     └── Sparse: character-bigram tokenizer → BM25
                 ↓ top-ranked chunks
                    ↓
              RRF (k = 60)
                    ↓
         Source-anchored RetrievalHits
```

### Why hybrid retrieval?

Dense similarity supports semantic matching and paraphrases. BM25 supports
exact terms such as contract parties, dates, article numbers and proper names.
Their numeric similarity scores have different scales; RRF merges rankings
rather than adding incompatible scores.

For RRF, a candidate at rank `r` contributes `1 / (60 + r)` per branch.

### Chinese BM25 tokenizer

M2a uses character bigrams instead of requiring an external word segmenter:

- "付款期限" → "付款", "款期", "期限".
- English and numbers are indexed as lowercase word/digit tokens.
- Positive IDF; `k1=1.5`, `b=0.75`.

This is a transparent learning baseline, not a claim that character bigrams
always outperform jieba segmentation or learned sparse retrieval.

### Data and query flow

- Dense queries use the same 512-dimensional BGE embedding implementation as M1.
- Dense Top-K is retrieved through Qdrant `query_points()`.
- M2a BM25 reads Qdrant text payloads with cursor-based scroll.
- The BM25 scan is **explicitly bounded to 5,000 chunks** and raises an error
  if exceeded; it never silently returns results from an incomplete corpus.
- Optional `document_id` filtering applies identically to both branches.
- RRF results retain `document_id`, `filename`, `page`, `section`,
  `chunk_id`, `text`, `dense_rank` and `sparse_rank`.

This initial BM25 approach trades scale for transparent implementation
and zero new storage dependencies. It is not production-level sparse
indexing; a persistent BM25/sparse index is a future scalability upgrade.

### M2a validation in Windows CMD

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m2a.bat
```

This test:

1. Uploads and indexes three **synthetic** contract documents.
2. Performs a real BGE/Qdrant Dense query and BM25 query.
3. Verifies both branches contribute to RRF for a selected document.
4. Verifies document_id metadata filtering.
5. Prints global ranked evidence and an empty-result check.

Expected last lines:

```text
PASS document metadata filter + Dense/BM25/RRF: ...
PASS nonexistent document filter returns empty evidence
M2a PASS
M2a validation passed.
```

Model weights should already be cached in the `embedding-cache` Docker volume
from the M1b acceptance test.

### Unit tests

`tests/unit/test_m2a_retrieval.py` validates BM25 tokenization,
nonmatching queries, RRF combination, deduplication and UUID filters.

### No new public API in M2a

V1 public API remains frozen. The integration test calls
`app.rag.retriever.hybrid_search()` inside the API container.
The business API will expose RAG/Agent functionality via the already
planned `POST /v1/chat` endpoint, rather than adding a proliferation
of unrelated REST endpoints.

## M2b — Planned after M2a acceptance

- Query rewriting (with a safe direct-query fallback).
- Reranker (BGE family, runtime and model provenance to be fixed).
- Evidence selection and deterministic citation construction.
- OpenAI-compatible generation via the existing vLLM service.
- Citation validity checks and an evidence-insufficient answer path.

The full M2 acceptance requires an actual question to yield an
evidence-grounded answer with valid source metadata; a list of retrieved
chunks alone is **not** a completed RAG pipeline.
