@echo off
setlocal
cd /d %~dp0\..
if "%~1"=="" goto usage
if /i "%~1"=="rag" goto rag
if /i "%~1"=="agent" goto agent
if /i "%~1"=="system" goto system
if /i "%~1"=="system-live" goto systemlive
if /i "%~1"=="trace" goto trace
if /i "%~1"=="demo" goto demo
if /i "%~1"=="demo-live" goto demolive
goto usage

:rag
call scripts\check_m7a.bat
exit /b %errorlevel%
:agent
call scripts\check_m7b.bat
exit /b %errorlevel%
:system
call scripts\check_m7c.bat
exit /b %errorlevel%
:systemlive
call scripts\check_m7c_live.bat
exit /b %errorlevel%
:trace
call scripts\check_m8.bat
exit /b %errorlevel%
:demo
call scripts\check_m9.bat
exit /b %errorlevel%
:demolive
call scripts\check_m9_live.bat
exit /b %errorlevel%

:usage
echo Usage: scripts\run_eval.bat rag ^| agent ^| system ^| system-live ^| trace ^| demo ^| demo-live
echo Each mode uses an existing API image; none triggers docker compose build.
echo M7c system and LIVE modes may take minutes due to CPU BGE reranking.
exit /b 2
