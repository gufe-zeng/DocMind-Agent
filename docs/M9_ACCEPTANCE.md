# M9 Business Demo and Engineering Acceptance

**Status: implementation submitted; local BASE/LIVE not yet verified.**

## Functional acceptance

**BASE:** Run `scripts\check_m9.bat` against the Docker stack.

Expected coverage: healthy dependencies; real TXT/PDF/DOCX indexing;
two-tool Agent→MCP; source-cited extraction and page-2 PDF evidence;
Redis multi-turn context; cross-session explicit preference; HITL
pending/approved/idempotent/409 conflict; durable PostgreSQL traces;
Prometheus metrics. Terminal lines:

```text
M9 DEMO BASE PASS
M9 base demo validation passed.
```

**LIVE:** With Qwen/vLLM available, run `scripts\check_m9_live.bat`
using BASE's indexed synthetic contract. It checks a real hybrid RAG
response, valid sources, correct payment deadline, and a persisted model
call. Terminal lines:

```text
M9 DEMO LIVE PASS
M9 live demo validation passed.
```

**CI:** Python unit checks validate static fixture creation, citation
scope checks and the no-rebuild BAT script contract. They cannot replace
the user's live Docker results.

## Release boundaries

M0–M8 core local acceptance was already reported by the user.
Grafana visualization has not been independently validated; the full
frozen V1 checklist therefore remains open until that separate check.
The M9 CLI demo is not a production UI or a real-world legal quality
benchmark. Do not mark M9 Completed until BASE and LIVE have passed.
