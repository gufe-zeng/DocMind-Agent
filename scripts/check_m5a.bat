@echo off
setlocal
cd /d %~dp0\..

echo Checking official MCP stdio transport: initialize, tools/list, tools/call.
echo M5a uses existing DocMind PostgreSQL/Qdrant and ModelScope BGE cache.
docker compose exec -T api python scripts/check_m5a.py
if errorlevel 1 (
    echo M5a validation FAILED. Check docker compose logs --tail 100 api.
    exit /b 1
)
echo M5a validation passed.
endlocal
