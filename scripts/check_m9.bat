@echo off
setlocal
cd /d %~dp0\..
echo M9 BASE: end-to-end V1 local business demo, no Qwen needed.
echo Reuse PostgreSQL, Redis, Qdrant and ModelScope BGE cache. Do not rebuild here.
docker compose config -q
if errorlevel 1 (
  echo M9 Compose configuration is invalid.
  exit /b 1
)
docker compose exec -T api python scripts/check_m9.py base
if errorlevel 1 (
  echo M9 DEMO BASE FAILED. Inspect: docker compose logs --tail 120 api
  exit /b 1
)
echo M9 base demo validation passed.
endlocal
