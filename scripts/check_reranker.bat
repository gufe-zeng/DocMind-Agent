@echo off
setlocal
cd /d %~dp0\..

echo First run downloads ~1.11 GB ONNX from ModelScope into persistent cache.
docker compose exec -T api python scripts/check_reranker.py
if errorlevel 1 (
  echo Reranker validation FAILED.
  echo Run: docker compose logs --tail 100 api
  exit /b 1
)
echo Reranker validation passed.
endlocal
