@echo off
setlocal

echo === DocMind-Agent root ===
curl --noproxy "*" -s http://127.0.0.1:8090/
echo.
echo.

echo === M0 dependency health ===
curl --noproxy "*" -s http://127.0.0.1:8090/health
echo.
echo.

echo === Prometheus metrics ===
curl --noproxy "*" -s http://127.0.0.1:8090/metrics | findstr /C:"python_info"
echo.

echo Smoke test finished.
endlocal
