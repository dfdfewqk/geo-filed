@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
title GeoField CHECK ONLY - NOT THE APP - START GeoField_Start.cmd FIRST
set "GF_PACKAGE=%~dp0"
set "GF_PY="
rem CHECK ONLY: This file never starts the backend. Use GeoField_Start.cmd first.
rem Run this AFTER the one real CAD/FEA/AI test while GeoField is still open.
rem This command never installs, runs CalculiX, mutates CAD/SQLite or uses the LLM.
if not exist "%GF_PACKAGE%acceptance_probe.py" goto :missing
if not exist "%GF_PACKAGE%verify_package.py" goto :missing
if defined LOCALAPPDATA if exist "%LOCALAPPDATA%\GeoFieldCAD\engines\geofield-analysis-win64\python.exe" set "GF_PY=%LOCALAPPDATA%\GeoFieldCAD\engines\geofield-analysis-win64\python.exe"
if not defined GF_PY for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do if exist "%%P" if not defined GF_PY set "GF_PY=%%P"
if not defined GF_PY for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)" 2^>nul') do if exist "%%P" if not defined GF_PY set "GF_PY=%%P"
if not defined GF_PY goto :python_missing
echo [READ ONLY] Verifying the extracted integration package...
"%GF_PY%" -u "%GF_PACKAGE%verify_package.py"
if errorlevel 1 goto :invalid
echo [CHECK ONLY] This is NOT GeoField_Start.cmd. It does NOT start the GeoField server.
echo [CHECK ONLY] Verify the original GeoField CMD is open and http://127.0.0.1:8600/ is responding.
echo [READ ONLY] Checking active local GeoField CAD/FEA/AI evidence...
"%GF_PY%" -u "%GF_PACKAGE%acceptance_probe.py"
set "GF_RC=%ERRORLEVEL%"
if "%GF_RC%"=="25" echo [SERVER OFFLINE] The original GeoField backend is NOT reachable. Run GeoField_Start.cmd and keep its backend CMD open first.
if "%GF_RC%"=="25" echo [ACTION] If main start fails, inspect diagnostics\r12_launcher\bootstrap_latest.log and backend_latest.log; do not rerun this checker.
if not "%GF_RC%"=="0" if not "%GF_RC%"=="25" echo [NOT VERIFIED] Some API evidence is unavailable. Inspect the printed action before repeating. Not an installation failure.
echo [NEXT] If server offline, check the original startup log; if server active, share only the report and single test video.
echo [PRIVACY] No original STEP/FRD, IDs, SHA or API keys are written to the report.
pause
exit /b %GF_RC%
:missing
echo [ERROR] Candidate ZIP is not fully extracted. No files were changed.
goto :fail
:python_missing
echo [ERROR] Python not available. No files were changed.
goto :fail
:invalid
echo [ERROR] Candidate integrity failed. No files were changed.
:fail
pause
exit /b 1
