@echo off
setlocal
cd /d %~dp0\..
echo M9 LIVE: reuse the BASE fixture for one real Qwen hybrid RAG citation test.
echo Requires the existing llm-serving-ops Qwen/vLLM endpoint on host port 8000.
echo No Docker build, no volume removal and no new model download.
echo Force source imports from /app to avoid stale site-packages after local code copy.
docker compose exec -T -e PYTHONPATH=/app api python -m scripts.check_m9 live
if errorlevel 1 (
  echo M9 DEMO LIVE FAILED. Check vLLM and API logs.
  exit /b 1
)
echo M9 live demo validation passed.
endlocal
