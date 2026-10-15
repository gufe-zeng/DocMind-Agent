@echo off
setlocal
cd /d %~dp0\..
echo M8 optional dashboard check: requires prometheus and grafana services running.
echo NOTE: do not rebuild the API image for this check.
curl --noproxy "*" -fsS --max-time 20 http://127.0.0.1:9091/-/ready
if errorlevel 1 (
  echo Prometheus not ready. Start optional stack from docs/OBSERVABILITY.md
  exit /b 1
)
echo.
curl --noproxy "*" -fsS --max-time 20 http://127.0.0.1:3091/api/health
if errorlevel 1 (
  echo Grafana not healthy.
  exit /b 1
)
echo.
echo M8 DASHBOARDS BASIC PASS
endlocal
