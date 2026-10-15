# M1 Acceptance Record — 2026-10-15

Status: **COMPLETED**. Evidence: the developer's Windows Docker Desktop/WSL2 console output. This is a locally reported runtime acceptance, not a CI E2E run.

## M1a — Document parsing and source-aware chunks

On 2026-10-14 the developer executed `scripts\\check_m1a.bat`:

- TXT synthetic contract: 1 block / 1 chunk with source metadata.
- PDF: 1 block / 1 chunk; real page number `page=1`.
- DOCX: heading `section="Payment Clause"` and table text correctly retained.
- Long text: split into 7 source-preserving chunks.
- Output: **`M1a PASS`**.

## M1b — Original storage, embedding and Qdrant

On 2026-10-15 the developer executed `scripts\\check_modelscope.bat`:

- ModelScope repository: `lyf219/bge-small-zh-v1.5-onnx`.
- Download: 6 files, completed successfully.
- Local cached ONNX: `/app/data/embed_cache/modelscope/bge-small-zh-v1.5-onnx/model_optimized.onnx`.
- ONNX size: **94,835,369 bytes**.
- ONNX SHA-256: `e256a606233996478f0eb6c99c9814e3797043d4a5563b4646b10929546196e5`.
- CPU inference: **512 dimensions**.
- Output: **`ModelScope ONNX PASS`**.

Then `scripts\\check_m1b.bat`:

| Fixture | Stored chunks | Vector dim | Result |
|---|---:|---:|---|
| sample_contract.txt | 1 | 512 | PASS |
| synthetic.pdf | 1 | 512 | PASS |
| synthetic.docx | 1 | 512 | PASS |
| Reindex first document | same count | 512 | PASS |

The M1b script checks PostgreSQL `documents.status = indexed` with correct
chunk counts and model identity, and checks Qdrant payload source identifiers,
page/section metadata, and actual vector length.

**Terminal output: `M1b PASS` / `M1b validation passed.`**

## Decision

- M0: Completed.
- M1a: Completed.
- M1b: Completed.
- **M1 Document Pipeline: Completed**.
- Next: M2 Hybrid Retrieval → Reranker → Citation.

No claim is made about RAG answer correctness or retrieval quality yet; those
belong to M2/M7 evaluation.
