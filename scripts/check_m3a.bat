@echo off
setlocal
cd /d %~dp0\..

echo Testing M3a LangGraph routing and Tool Calling via real API.
echo llm-serving-ops vLLM must be ready on host port 8000.
docker compose exec -T api python scripts/check_m3a.py
if errorlevel 1 (
  echo M3a validation FAILED. Check docker compose logs --tail 100 api.
  exit /b 1
)
echo M3a validation passed.
endlocal
