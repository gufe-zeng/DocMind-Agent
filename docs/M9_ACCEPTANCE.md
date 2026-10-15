# M9 Business Demo and Engineering Acceptance

**Status: BASE locally accepted; LIVE previously failed on CPU-RAG timeout.
M9 is not complete until LIVE passes after the patch.**

## BASE — accepted 2026-10-15 (actual Windows Docker result)

The user ran `scripts\check_m9.bat` and confirmed:

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

The demo recorded seven completed synthetic workflow cases with distinct
PostgreSQL trace identifiers. No generalization or production assertions
follow from these seven cases.

## LIVE — failed 2026-10-15, cause confirmed by M8 PostgreSQL trace

```text
status=tool_unavailable
request_ms=272128
llm_calls=0
error_type=TimeoutError
attempts=3
timeout_s=90
tool_ms=270300.42
```

The BGE CPU ONNX reranker was measured at 171.97–259.30 seconds in M7c.
Under the old 90-second read-only RAG timeout, the tool exhausted three
attempts and **never called Qwen**.

**Patch under verification:** `search_documents` and
`summarize_document` use a default 420-second CPU-RAG deadline, with
zero retries. Reranker ONNX scoring is serialized by an in-process lock.
`RAG_CPU_TIMEOUT_SECONDS` is configurable (300–600) through the
Compose environment, and failed LIVE calls expose sanitized tool events.

This repair is supported by unit/CI tests, but **does not constitute
a successful LIVE result until the user reruns the Docker test**.

## One-rebuild verification after CI success

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
scripts\check_m9_live.bat
```

Do **not** repeat BASE; its demo documents persist in the named volume.
Expected completion:

```text
M9 DEMO LIVE PASS
M9 live demo validation passed.
```

A no-rebuild runtime tuning option (only if 420 seconds is insufficient):

```cmd
set RAG_CPU_TIMEOUT_SECONDS=540
docker compose up -d --no-deps --force-recreate api
scripts\check_m9_live.bat
```

This will recreate **only** the API container using its existing image,
not rebuild or delete PostgreSQL/Qdrant/Redis volumes. No need to run this
tuning step unless diagnostics show a single timeout at 420 seconds.

The separate Grafana local dashboard verification remains pending for
full frozen V1 checklist sign-off. The M9 CLI demo does not establish
production authentication or real-world legal correctness.

## 2026-10-15: hotpatch CLI import-path mismatch (CI patch pending)

The user copied the patched Python modules into the running API container
because Docker Hub metadata resolution was failing behind its configured
mirror/proxy. A manual `python -c` check showed the source reliability
policy was loaded with `timeout_seconds=420`, `max_retries=0`.

Yet `scripts\\check_m9_live.bat` failed **before sending a chat request**:

```text
AttributeError: 'Settings' object has no attribute 'rag_cpu_timeout_seconds'
```

Root cause: `python scripts/check_m9.py live` starts with
`/app/scripts` at the front of Python's import path and may resolve
`app.core.config` from the original installed project distribution
in site-packages instead of the hotpatched `/app/app` source tree.

The Windows BAT scripts now launch
`docker compose exec -T -e PYTHONPATH=/app api python -m scripts.check_m9 live`
(or `base`), which prioritizes the matching source tree. No dependency
installation, API rebuild or BASE rerun is needed.

From Windows CMD after `git pull`:

```cmd
docker compose exec -T -e PYTHONPATH=/app api python -c "import app.core.config as c; print(c.__file__); print(c.get_settings().rag_cpu_timeout_seconds)"
scripts\check_m9_live.bat
```

The first command must report `/app/app/core/config.py` and `420.0`
(or the configured timeout value). If it still raises AttributeError,
restore the hotpatched `app/core/config.py` with
`docker compose cp app/core/config.py api:/app/app/core/config.py`
and restart **only API** to reload its config, without rebuilding the image.

M9 LIVE remains pending until the user reports the actual success footer.
