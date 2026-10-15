# M2b Local Acceptance — 2026-10-15

**Status: reranker PASS; RAG core PASS; live vLLM integration PASS. M2 completed.**

## Real ModelScope ONNX reranker

- Source: BAAI/bge-reranker-base@master on ModelScope, six files downloaded.
- Artifact: `/app/data/embed_cache/modelscope/bge-reranker-base-onnx/onnx/model.onnx`.
- Bytes: **1,112,459,588**.
- SHA-256: `15b9a8c3da82eddf263df571281166e00e9308fe19d077084b642ebfcaf06d2b`.
- Real CPU scores: `[1.605858564376831, -8.400724411010742]`.
- Terminal result: **`M2b reranker PASS`**.

## RAG core with deterministic LLM stub

- `scripts/check_m2b.bat` passed.
- Uploaded/indexed synthetic document: `b9492d15-9acc-4926-a81f-868f0d84853d`.
- Answer: `服务验收合格后三十日内完成付款。[S1]`.
- Cited real source: `m2b_payment.txt`, chunk ID `12f3a634-b12d-5e2b-9312-69a8dc1c30dc`.
- Terminal result: **`M2b core PASS (deterministic mock LLM)`**.

## Live vLLM integration — accepted

- Initial live attempt could not connect to `host.docker.internal:8000`; the user restored the vLLM service.
- Successful live run indexed document `82a150c3-3a1b-4bac-9ead-5d480dd2d0c2`.
- Endpoint: `http://host.docker.internal:8000/v1`.
- Model: `Qwen/Qwen3-0.6B`.
- Answer: `根据合同，服务验收后付款期限是三十天。[S1]`.
- Source: `m2b_payment.txt`, page=None, chunk_id `dcbba77c-fbdb-51a6-b3b6-05defdb7bca3`.
- Terminal result: **`M2b LIVE PASS`** / **`M2b live validation passed.`**.

**Decision: M2 Completed (functional acceptance).**

Citation-ID validation checks source linkage, not semantic entailment.
Numeric retrieval evaluation and response factuality are deferred to M7.
History-aware query rewrite is not implemented yet and will be revisited in M4.

This record is based on real user-provided Docker logs, not a GitHub Actions integration test.