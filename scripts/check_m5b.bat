@echo off
setlocal
cd /d %~dp0\..

echo Validating LangGraph Agent -> official MCP Client -> Document MCP Server.
echo Real PostgreSQL/Qdrant/BGE used; live Qwen is not required.
docker compose exec -T api python scripts/check_m5b.py
if errorlevel 1 (
  echo M5b Agent MCP validation FAILED. Check docker compose logs --tail 100 api.
  exit /b 1
)
echo M5b Agent MCP validation passed.
endlocal
