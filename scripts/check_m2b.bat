@echo off
setlocal
cd /d %~dp0\..

echo M2b RAG core test: real BGE reranking + a controlled LLM stub.
docker compose exec -T api python scripts/check_m2b.py
if errorlevel 1 (
  echo M2b core validation FAILED.
  exit /b 1
)
echo M2b core validation passed.
endlocal
