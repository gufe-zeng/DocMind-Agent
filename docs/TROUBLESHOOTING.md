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


## M1b: Embedding model download fails through Docker/Clash

Observed in local logs (2026-10-14):

```text
POST /v1/documents -> 201 Created
POST /v1/documents/{id}/index -> 503
httpx.ConnectError: [SSL: UNEXPECTED_EOF_WHILE_READING]
```

The stack trace originates from FastEmbed / Hugging Face Hub `model_info()`.
Upload works, but the API container cannot reliably access the model API.
A `200` response from the `hf-mirror.com` home page alone does **not**
verify the model API and artifact download routes.

### Runtime proxy configuration (Windows Clash HTTP/mixed port 7897)

Git for Windows may already use `http://127.0.0.1:7897`, but containers
have a different loopback interface. For Docker Desktop, the container must
use `http://host.docker.internal:7897` to reach the host proxy.

1. Verify Clash has the HTTP/mixed listener on port 7897. If container
   connections are refused, enable **Allow LAN** / appropriate bind address
   in Clash, and restrict exposure using the Windows Firewall as needed.
   Do not open the proxy to an untrusted network.
2. In the root `.env` file, add:

```dotenv
DOCMIND_PROXY_URL=http://host.docker.internal:7897
DOCMIND_HF_ENDPOINT=https://huggingface.co
```

3. Pull the repository's optional Compose proxy support, then recreate the API
   container so it receives the new environment variables:

```cmd
git pull
docker compose config
docker compose up -d --no-deps --force-recreate api
```

If `git pull` reports local changes to `compose.yaml`, inspect and preserve
those edits before updating; do not discard them blindly.

4. Verify the proxy is present inside the container:

```cmd
docker compose exec -T api python -c "import os; print(os.getenv('HTTPS_PROXY')); print(os.getenv('HF_ENDPOINT'))"
```

Expected URLs: `http://host.docker.internal:7897` and
`https://huggingface.co`.

5. Test the **model metadata API**, not just the website home page:

```cmd
docker compose exec -T api python -c "from huggingface_hub import model_info; print(model_info('BAAI/bge-small-zh-v1.5').sha)"
```

If this works, repeat:

```cmd
scripts\check_m1b.bat
```

The `NO_PROXY` setting bypasses Clash for PostgreSQL, Redis, Qdrant,
the API loopback tests, and the local vLLM host gateway.

This is a **runtime** networking fix. Docker image pulls and image build
downloads have separate proxy settings.
