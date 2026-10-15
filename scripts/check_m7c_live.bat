@echo off
setlocal
cd /d %~dp0\..
echo M7c LIVE: full base profiling plus one real Qwen RAG token-usage probe.
echo Requires existing llm-serving-ops vLLM endpoint on host port 8000.
docker compose exec -T api python scripts/check_m7c.py --live
if errorlevel 1 (
  echo M7c SYSTEM LIVE FAILED. Check vLLM and API logs.
  exit /b 1
)
echo M7c system live validation passed.
endlocal
