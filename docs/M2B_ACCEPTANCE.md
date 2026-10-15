# M2b Local Acceptance — 2026-10-15

**Status: reranker PASS; RAG core PASS; live vLLM integration PENDING.**

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

## Live vLLM integration — not yet accepted

- `scripts/check_m2b_live.bat` indexed document `d7a461fb-43b4-4076-bf23-9746bf608b99`.
- Failure: `httpx.ConnectError: All connection attempts failed` at
  `http://host.docker.internal:8000/v1/chat/completions`.
- The stack trace shows failure at model-service connection, *after* indexing/retrieval.
- Root cause still needs testing: vLLM may be stopped, not ready, or inaccessible through the host gateway.
- The checked `llm-serving-ops/compose.yaml` maps vLLM `8000:8000`, FastAPI `8080:8080`, Nginx `8081:80`.

## Next gate

1. In `E:\project\llm-serving-ops`, run `docker compose ps` and `docker compose up -d vllm` as needed.
2. Test Windows host: `curl --noproxy "*" http://127.0.0.1:8000/v1/models`.
3. Test from DocMind API container: `http://host.docker.internal:8000/v1/models`.
4. Re-run `scripts\check_m2b_live.bat` and inspect the model-generated citation.

**Do not mark M2 complete until the live vLLM answer/citation gate passes.**

This record is based on real user-provided Docker logs, not a GitHub Actions integration test.