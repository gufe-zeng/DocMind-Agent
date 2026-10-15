# M9 Business Demo and Engineering Acceptance — 2026-10-15

**Decision: M9 BASE and LIVE Completed — real local Docker functional acceptance.**

## BASE — accepted

The user ran `scripts\check_m9.bat` successfully against real PostgreSQL, Redis,
Qdrant, LangGraph, MCP and Prometheus services.

```text
PASS DocMind API /health and dependencies ready
PASS TXT/PDF/DOCX uploaded and indexed with real services
PASS LangGraph -> MCP two-tool chain with scoped citations
PASS source-grounded party/payment extraction with citations
PASS actual PDF page-2 source provenance
PASS parsed DOCX clause retrieval and citation
PASS Redis session follow-up and PostgreSQL checkpoint
PASS explicit preference persisted and recalled in new session
PASS HITL guarded write, approved once, replay idempotent, conflict denied
PASS Prometheus /metrics and persisted request-level Agent traces
M9 DEMO BASE PASS
M9 base demo validation passed.
```

The BASE fixture passed seven synthetic business stages, produced trace IDs
for each stage, and created an indexed contract reused by LIVE.

## LIVE — accepted

The user verified that the current API source directory is used when invoking
the test, with the expected runtime timeout setting:

```text
/app/app/core/config.py
420.0
```

The user then ran `scripts\check_m9_live.bat`:

```text
PASS DocMind API /health and dependencies ready
PASS real Qwen hybrid-RAG answer with factual deadline/citation
PASS Qwen request and token observations in Agent telemetry
{
  "stage": "qwen_grounded_rag",
  "status": "answered",
  "tools_called": ["search_documents"],
  "mcp_tools_called": [],
  "source_count": 1
}
M9 DEMO LIVE PASS
M9 live demo validation passed.
```

The LIVE assertion checks: Agent `status=answered`; exactly one
`search_documents` tool attempt; expected payment deadline in the answer;
at least one valid, document-scoped citation; and a persisted Trace with an
actual LLM call. This establishes **one real Qwen-grounded RAG answer** on
the indexed synthetic contract, not semantic correctness on real contracts.

## Earlier failure, diagnosis, and repair

The initial LIVE attempt ended with:

```text
status=tool_unavailable
error_type=TimeoutError
attempts=3
timeout_s=90
tool_ms=270300.42
llm_calls=0
```

Earlier M7c measurements had found BGE CPU reranking took 171.97–259.30
seconds, longer than the original 90-second tool deadline. The repaired
`search_documents` and `summarize_document` execution budget is
420 seconds by default, configurable within 300–600 seconds, with no retry
for potentially non-cancellable ONNX inference; the reranker also has an
in-process inference lock. Ordinary read-only tools retain the established
bounded retry policies.

A subsequent hotpatch test briefly raised an `AttributeError` for the
new timeout setting because direct `python scripts/check_m9.py` could
import the outdated installed copy of `app` from `site-packages`.
The BAT scripts now set `PYTHONPATH=/app` and invoke
`python -m scripts.check_m9`. The final successful run verified that
`/app/app/core/config.py` was loaded and the budget was 420 seconds.

## Deployment/build distinction and remaining release work

**This acceptance used an existing API container with the repaired Python
source copied in, because rebuilding the image was blocked by Docker Hub
mirror/proxy DNS failures.** The successful local runtime test is valid,
but it does **not** verify that a freshly rebuilt immutable API image
contains all repaired code. Restore Docker mirror/proxy connectivity and
complete one normal build when convenient; no volumes should be deleted.

M9 marks the frozen **core functional demo milestone Complete**. A
separate Grafana dashboard and Prometheus scrape check remains pending for
full frozen V1 release sign-off. Neither functional acceptance nor the tiny
synthetic evaluation sets establish authenticated multi-tenancy, production
deployment readiness, load capacity, or generalizable legal answer quality.

See [M9 Demo Guide](M9_DEMO.md), [Release Checklist](RELEASE_CHECKLIST.md),
and [Resume Evidence](RESUME_PROJECT.md).
