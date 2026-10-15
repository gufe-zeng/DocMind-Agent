# M7a Acceptance — 2026-10-15

**Decision: M7a Completed (local Docker functional acceptance).**

## Evidence from Windows CMD

```text
docker compose exec -T api python -c "from eval.rag_metrics import evaluate_retrieval; print('M7a import OK')"
M7a import OK

scripts\check_m7a.bat
M7a: real hybrid retrieval metrics on synthetic fixture.
{
  "cases": 3,
  "k": 3,
  "recall_at_k": 1.0,
  "mrr_at_k": 1.0,
  "evaluation_unit": "document",
  "candidate_chunks_outside_fixture": 63,
  "dataset_version": 1,
  "scope": "synthetic smoke benchmark, not generalization evidence"
}
M7a RETRIEVAL PASS (execution and metric-integrity smoke)
M7a retrieval validation passed.
```

The runner uploaded and indexed synthetic contract documents in the user's
Docker environment and invoked the actual BGE Dense + BM25 + RRF retrieval
pipeline. Recall@3 = 1.0 and MRR@3 = 1.0 describe exactly those **three
synthetic document-level gold cases**. The run observed 63 retrieved chunks
outside the current fixture across its queries.

## Interpretation and limits

- **Passed:** module packaging/import, real indexing and retrieval invocation,
  JSON fixture loading, deterministic document-level metric calculation.
- **Not established:** chunk-level relevance, answer factuality, real contract
  generalization, statistical significance, or a fixed isolated corpus.
- The shared persistent Qdrant corpus may evolve between runs; rerunning
  can yield different scores even with an unchanged fixture.
- The assertion for M7a checks metric integrity/range, not an accuracy
  threshold. This is explicitly a smoke/evaluation-pipeline acceptance.
- Citation provenance accuracy currently has unit tests, not a measured
  production-quality citation/faithfulness benchmark.

Next: M7b Agent task/tool evaluation, followed by system metrics in M7c.
