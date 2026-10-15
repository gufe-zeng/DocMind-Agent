# M2 — Hybrid RAG Development Guide

Status: **M2a Completed (2026-10-15); M2b implemented, local validation pending**. M1a/M1b completed.

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

## M2b — Cross-Encoder reranking and grounded generation

The M2a integration test has now been accepted. M2b is implemented as:

```text
Normalized question
→ M2a Dense + BM25 + RRF, candidate Top 8
→ BGE-reranker-base (ModelScope ONNX, CPU, ~1.11 GB)
→ Top 2 source-preserving chunks, up to 160 chars each
→ Deterministic [S1], [S2] reference labels
→ OpenAI-compatible chat completion (max 128 output tokens)
→ Validate that cited IDs exist in the retrieved evidence
→ Answer with sources, or citation_unverified
```

### Source-aware citations

The code constructs source references *before* passing them to the model.
Each one retains document_id, filename, page or section, chunk_id and a
bounded evidence excerpt. The LLM can cite only these labels.

Unknown or absent IDs on a factual answer produce `citation_unverified`,
and the unsupported generated text is withheld. An exact evidence-insufficient
refusal can be citation-free.

**Boundary:** This check establishes *reference integrity*, not factual
entailment between every answer claim and its cited excerpt. Semantic
faithfulness is evaluated later in M7.

### Model choice

- Model: `BAAI/bge-reranker-base`, an original BAAI bilingual Cross-Encoder.
- Source: https://modelscope.cn/models/BAAI/bge-reranker-base
- Artifact: `onnx/model.onnx`, around **1.11 GB**.
- Load: `fastembed.TextCrossEncoder` with `specific_model_path`,
  `local_files_only=True`, and `cuda=False`.
- ModelScope snapshot is cached in the same persistent Docker volume as
  the embedding ONNX model. Neither model requires GPU memory.

The official ONNX weight is much larger than BGE-small-zh-v1.5 and CPU
reranking may add substantial latency. Keep `RAG_CANDIDATE_K=8` and
`RAG_EVIDENCE_K=2` for the local machine; benchmark later before optimizing.

### Three acceptance commands

In Windows CMD at `E:\project\DocMind-Agent`:

```cmd
git pull
docker compose up -d --build api
scripts\check_reranker.bat
scripts\check_m2b.bat
```

`check_reranker.bat` confirms actual ONNX weights and Cross-Encoder
scores. `check_m2b.bat` checks the full chain with a **controlled LLM
stub** so local model network errors cannot be mistaken for RAG errors.

For live vLLM (separate acceptance gate), start `llm-serving-ops` and
confirm its OpenAI-compatible API is available at
`http://host.docker.internal:8000/v1` *from inside the API container*.
Then run:

```cmd
scripts\check_m2b_live.bat
```

Expected final messages:

```text
M2b reranker PASS
M2b core PASS (deterministic mock LLM)
M2b LIVE PASS
```

The live model is Qwen3-0.6B unless the LLM configuration is changed.
Its answer quality is not assumed; a missing/incorrect citation is reported
as a failure rather than fabricated by postprocessing.

### M2b limitations

- Semantic query rewriting is **not** implemented yet. The current
  pipeline normalizes whitespace; real history-aware query rewriting
  is added together with session context (M4) if needed.
- No new public API is introduced; `POST /v1/chat` belongs to M3.
- The current Prompt has explicit external-document untrusted-data
  instructions but should not be treated as a complete prompt-injection
  defense.
- Only source-ID existence is validated; claim-level citation quality
  remains an evaluation task.


The full M2 acceptance requires an actual question to yield an
evidence-grounded answer with valid source metadata; a list of retrieved
chunks alone is **not** a completed RAG pipeline.
