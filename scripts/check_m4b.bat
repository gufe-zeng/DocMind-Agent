@echo off
setlocal
cd /d %~dp0\..

echo M4b: validate explicit user preference storage and semantic recall.
echo Ensure Docker services and host vLLM are running.
docker compose exec -T api python scripts/check_m4b.py
if errorlevel 1 (
    echo M4b memory validation FAILED.
    echo Inspect docker compose logs --tail 100 api.
    exit /b 1
)
echo M4b memory validation passed.
endlocal
