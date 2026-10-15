@echo off
setlocal
cd /d %~dp0\..

echo Checking ModelScope download and CPU ONNX inference...
docker compose exec -T api python scripts/check_modelscope.py
if errorlevel 1 (
    echo ModelScope check FAILED. Run: docker compose logs --tail 100 api
    exit /b 1
)
echo ModelScope check passed.
endlocal
