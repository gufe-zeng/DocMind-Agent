@echo off
setlocal
cd /d %~dp0\..

echo M4b: verify checkpoint interruption and resume from new connection.
docker compose exec -T api python scripts/check_m4b_resume.py
if errorlevel 1 (
    echo M4b checkpoint validation FAILED.
    exit /b 1
)
echo M4b checkpoint validation passed.
endlocal
