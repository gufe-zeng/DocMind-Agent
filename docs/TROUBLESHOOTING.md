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
