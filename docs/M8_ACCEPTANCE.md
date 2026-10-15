# M8 Observability Acceptance — 2026-10-15

**Decision: M8 core Completed by actual local Docker validation.**

The user executed `scripts\check_m8.bat`. Observed:

```text
PASS M8 API ready and synthetic document indexed
PASS durable trace for real LangGraph nodes and PostgreSQL tool
PASS real Agent->MCP trace with source-preserving tool event
PASS pending HITL graph request is traced without pre-approval write
PASS HITL approval checkpoint resume and second durable trace
PASS /metrics exposes request, node/tool and RAG stage families
M8 PREPARE PASS - restart only API and verify persisted traces
PASS M8 PostgreSQL Agent traces survive real API restart
PASS new requests produce traces after API restart
PASS Prometheus instrumentation active after API restart
M8 OBSERVABILITY PASS
M8 Observability validation passed.
```

Validated on real Docker: LangGraph node and MCP tool events, HITL pause/resume, durable PostgreSQL request traces across an actual API restart, new traces after restart, and Prometheus metric families.

Not validated: the separately provisioned Grafana dashboard, production authentication, trace retention, load testing, or distributed tracing into external Qwen/MCP subprocesses. This is local functional acceptance only.

M8 also rearranged Docker dependencies into a cached layer. No measured after-versus-before build speedup has been reported.
