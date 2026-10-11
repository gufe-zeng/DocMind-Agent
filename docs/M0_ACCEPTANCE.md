# M0 Acceptance — 2026-10-11

Environment: Windows CMD, WSL2 and Docker Desktop.

The developer reported:

- `docker compose up -d --build`: image built successfully (13/13 steps).
- `docker compose ps`: API, PostgreSQL, Redis and Qdrant containers running; PostgreSQL/Redis reported healthy.
- `curl --noproxy "*" http://127.0.0.1:8090/health` returned:

```json
{
  "status": "ok",
  "stage": "M0",
  "dependencies": {
    "postgres": {"status": "up", "latency_ms": 149.12},
    "redis": {"status": "up", "latency_ms": 131.89},
    "qdrant": {"status": "up", "latency_ms": 132.52}
  }
}
```

**Decision: M0 Completed.**

The first curl attempt lacked a space between `--noproxy "*"` and the URL; the corrected request succeeded. Initial build time was about 149 seconds due primarily to image downloads and Python dependency installation.

This is a user-verified local acceptance record, not a CI report.
