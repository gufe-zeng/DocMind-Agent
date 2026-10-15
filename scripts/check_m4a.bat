@echo off
setlocal
cd /d %~dp0\..

echo Validating M4a Redis recent turns and LangGraph PostgreSQL checkpoints.
echo Ensure llm-serving-ops vLLM is ready on Windows host port 8000.
docker compose exec -T api python scripts/check_m4a.py
if errorlevel 1 (
  echo M4a validation FAILED. Check: docker compose logs --tail 100 api
  exit /b 1
)
echo M4a validation passed.
endlocal
