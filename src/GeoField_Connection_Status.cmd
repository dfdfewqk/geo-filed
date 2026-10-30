@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
title GeoField - CAD ML DeepSeek Connection Status
rem This command makes ONLY read-only GET requests to localhost:8600.
rem It does not run any installer, CAD/FEA job, ML inference or paid API.
set "GF_SRC=%~dp0"
set "GF_PY="
if defined GEOFIELD_PYTHON if exist "%GEOFIELD_PYTHON%" set "GF_PY=%GEOFIELD_PYTHON%"
if not defined GF_PY for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do if exist "%%P" if not defined GF_PY set "GF_PY=%%P"
if not defined GF_PY for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)" 2^>nul') do if exist "%%P" if not defined GF_PY set "GF_PY=%%P"
if not defined GF_PY if defined LOCALAPPDATA if exist "%LOCALAPPDATA%\GeoFieldCAD\engines\geofield-analysis-win64\python.exe" set "GF_PY=%LOCALAPPDATA%\GeoFieldCAD\engines\geofield-analysis-win64\python.exe"
if not defined GF_PY goto :no_python
if not exist "%GF_SRC%geofield_live_preflight.py" goto :missing
echo [CHECK] GeoField local server, R12 dependency and DeepSeek settings only
echo [SAFE] No API fee, no new CAD/FEA/ML job and no installed file changes
"%GF_PY%" -u "%GF_SRC%geofield_live_preflight.py" --port 8600
set "GF_RC=%ERRORLEVEL%"
if not "%GF_RC%"=="0" echo [RESULT] Local server unavailable or check failed. Exit %GF_RC%.
echo [INFO] A configured DeepSeek key does not imply that a paid API request has succeeded.
echo [INFO] R12 available does not mean the current STEP has been inferred.
pause
exit /b %GF_RC%
:missing
echo [BLOCKED] geofield_live_preflight.py must be beside this CMD.
goto :fail
:no_python
echo [BLOCKED] Existing Python not found. Do not install anything for this check.
:fail
pause
exit /b 2
