@echo off
setlocal
cd /d %~dp0\..

echo M6a: test real Agent-MCP regression and injected transient tool failures.
echo No Qwen needed; reuse existing PostgreSQL, Qdrant and BGE cache.
docker compose exec -T api python scripts/check_m6a.py
if errorlevel 1 (
  echo M6a reliability validation FAILED.
  echo Inspect: docker compose logs --tail 100 api
  exit /b 1
)
echo M6a reliability validation passed.
endlocal
