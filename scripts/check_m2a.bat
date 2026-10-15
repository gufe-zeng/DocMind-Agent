@echo off
setlocal
cd /d %~dp0\..

echo Running M2a Hybrid Retrieval validation (Dense + Chinese BM25 + RRF).
docker compose exec -T api python scripts/check_m2a.py
if errorlevel 1 (
    echo M2a validation FAILED. Check: docker compose logs --tail 100 api
    exit /b 1
)
echo M2a validation passed.
endlocal
