@echo off
setlocal
cd /d %~dp0\..

echo Running M3b with real PostgreSQL/Qdrant, CPU BGE, and live Qwen3.
echo Keep llm-serving-ops vLLM available on host port 8000.
docker compose exec -T api python scripts/check_m3b.py
if errorlevel 1 (
    echo M3b validation FAILED. Inspect docker compose logs --tail 100 api.
    exit /b 1
)
echo M3b validation passed.
endlocal
