# Troubleshooting

This guide grows from verified failures rather than hypothetical issues.

## M0: `/health` returns 503

Inspect the dependency status in the JSON response, then check the matching service:

```cmd
docker compose ps
docker compose logs postgres
docker compose logs redis
docker compose logs qdrant
docker compose logs api
```

M0 host ports:

```text
5432 PostgreSQL
6379 Redis
6333 Qdrant REST
6334 Qdrant gRPC
8090 DocMind-Agent API
```

If a port is occupied:

```cmd
netstat -ano | findstr :8090
netstat -ano | findstr :5432
```

For local proxy interference, prefer:

```cmd
curl --noproxy "*" http://127.0.0.1:8090/health
```

Do not troubleshoot RAG/Agent layers until M0 infrastructure health is clean.


## M1b: Switch embedding downloads to ModelScope

Observed on 2026-10-14:

```text
POST /v1/documents -> 201 Created
POST /v1/documents/{id}/index -> 503
httpx.ConnectError: [SSL: UNEXPECTED_EOF_WHILE_READING]
```

The failure came from FastEmbed's default Hugging Face model download.
We replaced the network path:

```text
ModelScope (community BGE-small-zh-v1.5 ONNX snapshot)
    ↓ snapshot_download()
Docker persistent embedding-cache volume
    ↓ local ONNX weights + tokenizer
FastEmbed(specific_model_path=..., local_files_only=True)
    ↓
512-dimensional CPU embeddings
    ↓
Qdrant documents_v1
```

### Recovery steps (Windows CMD)

Check for uncommitted modifications before pulling:

```cmd
cd /d E:\project\DocMind-Agent
git status --short
git pull
```

If the root `.env` has a previous Clash proxy entry, normally remove:

```dotenv
DOCMIND_PROXY_URL=http://host.docker.internal:7897
DOCMIND_HF_ENDPOINT=https://huggingface.co
```

Then rebuild the API image (the ModelScope SDK is a new dependency):

```cmd
docker compose up -d --build api
```

First validate the standalone model download:

```cmd
scripts\check_modelscope.bat
```

Expected: `ModelScope ONNX PASS`.

Then verify full document ingestion:

```cmd
scripts\check_m1b.bat
```

Expected: `M1b PASS`.

### If ModelScope itself is unreachable

Inspect the recent application logs and verify the ModelScope model page:

```cmd
docker compose logs --tail 100 api
```

`https://modelscope.cn/models/lyf219/bge-small-zh-v1.5-onnx`

Unlike a model-page `200`, a successful `check_modelscope.bat` confirms
that the full ONNX file, tokenizer and CPU runtime are working.

For a community ONNX distribution, record and pin the model revision/hash
when promoting the project beyond the learning environment. The repository
does not silently fall back to Hugging Face when ModelScope fails.


## M4a: psycopg `no pq wrapper available` in python:3.12-slim

Reported on 2026-10-15 after `docker compose up -d --build api`:

```text
ImportError: no pq wrapper available.
- No module named 'psycopg_c'
- No module named 'psycopg_binary'
- libpq library not found
```

The application container exits at startup because the official LangGraph
`AsyncPostgresSaver` imports Psycopg 3. Psycopg's pure-Python implementation
still requires the system `libpq` shared library, which is absent from the
minimal base image. This is a missing **client library**, not a PostgreSQL
server outage.

**Fix committed:** `pyproject.toml` explicitly requires
`psycopg[binary]>=3.2,<4`; the Dockerfile checks its native binary backend
during image build. The CI pipeline separately enforces `PSYCOPG_IMPL=binary`.

In Windows CMD:

```cmd
cd /d E:\project\DocMind-Agent
git pull
docker compose up -d --build api
docker compose ps
docker compose exec -T api python -c "from psycopg import pq; print(pq.__impl__)"
scripts\check_m4a.bat
```

Expected backend: `binary`. Do not delete Docker volumes or reinstall
PostgreSQL. In particular, **never** run `docker compose down -v` for this
issue: the Docker volumes contain prior indexed documents, Qdrant vectors,
Redis and PostgreSQL state, and cached model weights.

## M5b: ConnectError before the first Agent/MCP request

Observed after an API rebuild on 2026-10-15:

```text
httpx.ConnectError: All connection attempts failed
scripts/check_m5b.py -> POST /v1/documents
```

This failure happens **before** `tools/list` or `tools/call`: it is not
evidence of an MCP protocol failure. The M5b smoke script is executed
**inside** the API service via `docker compose exec -T api`, where its
`http://127.0.0.1:8000` target is correct. Port `8090` is for Windows
host access; `8000` is the container's Uvicorn listener.

After `docker compose up -d --build api`, container startup and FastAPI
readiness may not be simultaneous. `scripts/check_m5b.py` now polls
`/health` for up to 90 seconds *before* indexing fixtures. This is a
potential startup-race mitigation; if the problem persists, inspect the
network/listener rather than claiming it was a race.

From Windows CMD:

```cmd
cd /d E:\project\DocMind-Agent
docker compose ps
curl --noproxy "*" http://127.0.0.1:8090/health
docker compose exec -T api python -c "import httpx; r=httpx.get('http://127.0.0.1:8000/health',timeout=10,trust_env=False); print(r.status_code,r.text[:300])"
docker compose logs --tail 100 api
```

Note: `docker compose logs --tail 100 api.` (with a period after `api`)
looks up a non-existent service named `api.`. Use exactly `api`.

If host `/health` and in-container `/health` both work, rerun only:

```cmd
scripts\check_m5b.bat
```

If the new readiness gate still fails, share `docker compose ps` and
`docker compose logs --tail 100 api`. Do not remove persistent volumes
or change ports solely based on this ConnectError.
