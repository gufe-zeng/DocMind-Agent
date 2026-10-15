@echo off
setlocal
cd /d %~dp0\..
echo M7c: real Agent E2E, M6 tool latency, Dense/BM25/RRF and BGE rerank timing.
echo Qwen not required for BASE; no volumes are deleted.
docker compose exec -T api python scripts/check_m7c.py
if errorlevel 1 (
  echo M7c SYSTEM BASE FAILED. Inspect: docker compose logs --tail 100 api
  exit /b 1
)
echo M7c system base validation passed.
endlocal
