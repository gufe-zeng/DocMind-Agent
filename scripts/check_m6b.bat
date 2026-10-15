@echo off
setlocal
cd /d %~dp0\..

echo M6b: real Human-in-the-Loop approval, rejection and checkpoint restart.
echo No Qwen required. API will be restarted once without deleting volumes.
docker compose exec -T api python scripts/check_m6b.py prepare
if errorlevel 1 (
  echo M6b PREPARE FAILED. Inspect: docker compose logs --tail 100 api
  exit /b 1
)
echo Restarting only the API container to test durable interrupted workflow.
docker compose restart api
if errorlevel 1 (
  echo M6b API RESTART FAILED.
  exit /b 1
)
docker compose exec -T api python scripts/check_m6b.py finish
if errorlevel 1 (
  echo M6b HITL FAILED. Inspect: docker compose logs --tail 100 api
  exit /b 1
)
echo M6b HITL validation passed.
endlocal
