@echo off
setlocal
cd /d %~dp0\..

echo M2b live test. Ensure llm-serving-ops vLLM runs on host port 8000.
docker compose exec -T api python scripts/check_m2b.py --live
if errorlevel 1 (
  echo M2b LIVE validation FAILED. Inspect vLLM reachability and model outputs.
  exit /b 1
)
echo M2b live validation passed.
endlocal
