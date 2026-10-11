@echo off
setlocal
cd /d %~dp0\..

docker compose exec -T api python scripts/check_document_pipeline.py
if errorlevel 1 (
  echo M1a validation failed.
  exit /b 1
)

echo M1a validation passed.
endlocal
