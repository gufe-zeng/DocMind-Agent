# M7c Acceptance — 2026-10-15

**Decision: M7c Completed; M7a–M7c have passed local functional evaluation gates.**

The user executed both `scripts\check_m7c.bat` (BASE) and
`scripts\check_m7c_live.bat` (real Qwen probe). Each indexed a fresh
synthetic contract. Both ran four serial Agent HTTP requests with five
read-only tool calls and separate direct Dense/BM25/RRF and BGE reranker
in-container timing samples.

## Observed results

| Metric | BASE | LIVE |
|---|---:|---:|
| Agent HTTP requests answered | 4/4 | 4/4 |
| Agent HTTP failure count | 0 | 0 |
| Agent E2E mean (ms) | 6,776.05 | 4,778.89 |
| Agent E2E p95 (ms, nearest rank) | 13,144.82 | 7,919.79 |
| Read-only tool events | 5/5 | 5/5 |
| Tool latency mean (ms) | 5,184.66 | 3,343.04 |
| Standalone hybrid retrieval (ms) | 487.94 | 418.70 |
| Standalone BGE reranker (ms) | 259,297.50 | 171,971.24 |
| Agent workload LLM calls | 0 | 0 |

The separate LIVE RAG/Qwen probe returned `status=answered`,
`llm_calls=1`, `prompt_tokens=241`, `completion_tokens=16`,
`latency_ms=39578.30`, and `tokens_measured=true`.

```text
M7c SYSTEM BASE PASS
M7c system base validation passed.
M7c SYSTEM LIVE PASS
M7c system live validation passed.
```

## Performance finding

The CPU BGE reranker took **171.97–259.30 seconds** in these two
standalone measurements. This is a separate inference bottleneck from the
**~405-second Docker image build** reported before M8; they should not
be conflated. Quantify reranker warm-cache variability before optimizing
batch size, thread counts or deployment.

## Interpretation and limits

- Four serial requests are **not** a concurrency/throughput benchmark.
- RAG retrieval/rerank values are measured by separate in-container calls,
  NOT traced phases within the Agent HTTP requests.
- The optional Qwen probe directly exercised the RAG pipeline, not
  Qwen-based planning inside an Agent HTTP request.
- The CPU and historical persistent cache conditions were not controlled.
- One synthetic fixture does not establish real-world accuracy or latency.

**Follow-on:** M8 adds durable request/node tracing and application-layer
Prometheus metrics. M7 results remain evaluation-smoke evidence.
