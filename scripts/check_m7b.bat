@echo off
setlocal
cd /d %~dp0\..
echo M7b: evaluate real Agent tool selection, task outcomes and MCP provenance.
echo No Qwen required. Reuse PostgreSQL, Qdrant and BGE cache.
docker compose exec -T api python scripts/check_m7b.py
if errorlevel 1 (
  echo M7b AGENT EVAL FAILED. Inspect: docker compose logs --tail 100 api
  exit /b 1
)
echo M7b Agent evaluation validation passed.
endlocal
