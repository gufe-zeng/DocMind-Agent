# V1.0 evidence-based release checklist

The original scope remains frozen in `docs/REQUIREMENTS.md`.

| Release criterion | Evidence | Status |
|---|---|---|
| PDF/DOCX/TXT parsing/indexing | M1a/M1b local acceptance | Accepted |
| Dense + BM25 + RRF + BGE Rerank | M2a/M2b local acceptance | Accepted |
| Source/page provenance and citation IDs | M2b/M5b/M7b | Accepted for tested cases |
| Multiple typed Agent tool classes | M3b/M5b/M7b | Accepted |
| Redis multi-turn memory | M4a local acceptance | Accepted |
| Cross-session long-term preference | M4b local acceptance | Accepted |
| PostgreSQL graph checkpoint/recovery | M4b/M6b | Accepted |
| Real MCP Server/Client invocation | M5b/M6a | Accepted |
| Guarded approval/HITL/replay | M6b/M8 | Accepted |
| RAG, Agent, system evaluations | M7a/M7b/M7c | Accepted as synthetic smoke |
| Durable trace + Prometheus | M8 local Docker acceptance | Accepted |
| Grafana visualization | Optional Compose exists | Not yet verified locally |
| Unified V1 business demonstration | M9 scripts implemented | BASE/LIVE pending |

## Before declaring the entire V1 release accepted

1. Execute the M9 BASE and LIVE scripts and archive actual output.
2. Independently validate that Grafana shows its dashboard and Prometheus
   target `docmind-agent` reports UP.
3. Preserve user privacy: use synthetic examples, avoid real identifying
   document content, and do not publish session identifiers or credentials.
4. Explicitly state that this is a local proof-of-concept, not a secured
   multi-tenant production service.

## Measured limitations

M7a: document-level Recall@3 and MRR@3 each 1.0 over three synthetic
cases in a shared Qdrant collection. M7b: seven synthetic tasks achieved
Task Success Rate=1.0 and Tool Selection Accuracy=1.0, with eight
successful observed tool calls. These values do **not** estimate
real-document generalization.

M7c: two standalone CPU BGE Rerank measurements took 171.97 and
259.30 seconds. The old Docker image build took about 405.6 seconds.
These are separate operations. The M8 cached-dependency Dockerfile is
a structural improvement, not a verified time-saving percentage.

Remaining deployment gaps: caller-supplied user/session UUIDs are not
authentication; no full RBAC, production observability retention,
semantic entailment benchmark, concurrency/load testing, or hardened
public deployment.
