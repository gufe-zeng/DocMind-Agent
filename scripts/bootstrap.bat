@echo off
setlocal
cd /d %~dp0\..

if not exist .env (
  echo Creating .env from .env.example...
  copy .env.example .env >nul
)

echo [1/3] Validating Compose configuration...
docker compose config >nul
if errorlevel 1 exit /b 1

echo [2/3] Starting M0 stack...
docker compose up -d --build
if errorlevel 1 exit /b 1

echo [3/3] Current service status:
docker compose ps

echo.
echo DocMind-Agent API: http://127.0.0.1:8090
echo Run scripts\smoke_test.bat after the API finishes starting.
endlocal
