@echo off
setlocal
cd /d %~dp0\..
echo M7a: real hybrid retrieval metrics on synthetic fixture.
docker compose exec -T api python scripts/check_m7a.py
if errorlevel 1 (
  echo M7a RETRIEVAL FAILED. Inspect: docker compose logs --tail 100 api
  exit /b 1
)
echo M7a retrieval validation passed.
endlocal
