@echo off
setlocal
cd /d %~dp0\..

echo Running M1b upload/index/Qdrant validation.
echo The first run may download the BGE Chinese ONNX model.
docker compose exec -T api python scripts/check_m1b.py
if errorlevel 1 (
    echo M1b FAILED. Inspect: docker compose logs api
    exit /b 1
)
echo M1b validation passed.
endlocal
