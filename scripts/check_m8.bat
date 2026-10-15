@echo off
setlocal
cd /d %~dp0\..
echo M8: real LangGraph/MCP/HITL traces, Prometheus metrics and PostgreSQL restart durability.
echo No Qwen needed; reuse the already-built API and existing Docker volumes.
docker compose exec -T api python scripts/check_m8.py prepare
if errorlevel 1 (
  echo M8 PREPARE FAILED. Inspect: docker compose logs --tail 100 api
  exit /b 1
)
echo Restarting only the API container (no rebuild and no volume removal).
docker compose restart api
if errorlevel 1 (
  echo M8 API RESTART FAILED
  exit /b 1
)
docker compose exec -T api python scripts/check_m8.py finish
if errorlevel 1 (
  echo M8 OBSERVABILITY FAILED. Inspect: docker compose logs --tail 100 api
  exit /b 1
)
echo M8 Observability validation passed.
endlocal
