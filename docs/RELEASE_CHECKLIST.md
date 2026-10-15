# V1.0 evidence-based release checklist

The original frozen scope remains in `docs/REQUIREMENTS.md`.

| Release criterion | Evidence | Status |
|---|---|---|
| PDF/DOCX/TXT parsing and indexing | M1a/M1b local acceptance | Accepted |
| Dense + BM25 + RRF + BGE reranking | M2a/M2b local acceptance | Accepted |
| Source/page provenance and valid citation IDs | M2b/M5b/M7b/M9 | Accepted on tested cases |
| Bounded typed Agent tools | M3b/M5b/M7b/M9 | Accepted |
| Redis multi-turn memory | M4a/M9 | Accepted |
| Cross-session explicit preference | M4b/M9 | Accepted |
| PostgreSQL LangGraph checkpoint/resume | M4b/M6b/M9 | Accepted |
| Real MCP stdio Server/Client | M5b/M9 | Accepted |
| HITL approval, no premature writes, idempotence | M6b/M8/M9 | Accepted |
| RAG/Agent/System evaluations | M7a/M7b/M7c | Accepted as synthetic smoke |
| Durable PostgreSQL trace + Prometheus | M8/M9 | Accepted |
| Unified V1 business demo — BASE | M9 Docker live services | Accepted 2026-10-15 |
| Qwen-grounded business demo — LIVE | M9 Qwen result with document citation and LLM trace | Accepted 2026-10-15 |
| Provisioned Grafana dashboard / live Prometheus target | Compose files exist | **Not yet locally verified** |
| Fresh immutable API Docker image with latest repairs | Docker mirror/proxy DNS blocked build | **Not yet verified** |

## M9 acceptance detail

M9 BASE validated seven synthetic workflow stages, three document formats,
real multi-tool MCP, document/page provenance, Redis/PG memory, long-term
preferences, approval replay/idempotence, trace persistence and Prometheus.

M9 LIVE initially timed out three times at 90 seconds before a Qwen call.
The corrected single-attempt 420-second RAG budget, ONNX lock and
`PYTHONPATH=/app` module entrypoint were applied to the **existing**
API container. The subsequent LIVE check produced:

```text
PASS real Qwen hybrid-RAG answer with factual deadline/citation
PASS Qwen request and token observations in Agent telemetry
M9 DEMO LIVE PASS
M9 live demo validation passed.
```

Full evidence: [M9 Acceptance](M9_ACCEPTANCE.md).

## Remaining local release gates

1. Verify the Grafana dashboard can be opened and the Prometheus
   `docmind-agent` target is UP, as documented in
   [Observability](OBSERVABILITY.md).
2. Once the Docker registry mirror/proxy works, build the latest API
   image once without removing data volumes. The current runtime success
   used manually hotpatched Python files and cannot substitute for a
   reproducible immutable image build.
3. Keep V1 described as a **locally accepted functional proof of concept**,
   not a secured production service.

## Performance and validity boundaries

M7a reported Recall@3=1.0/MRR@3=1.0 on three synthetic cases, while M7b
reported seven synthetic Agent tasks at Task Success Rate=1.0 and
Tool Selection Accuracy=1.0 (eight observed tool calls). These scores
are not estimates of real-contract performance. M7c measured two
standalone CPU BGE reranks lasting 171.97 and 259.30 seconds, separate
from the reported Docker build/mirror wait.

The demo does not implement authenticated user identities/RBAC,
contract-level tenant isolation, enterprise trace retention,
representative semantic citation entailment tests, or concurrency/load
testing. Do not claim production readiness.
