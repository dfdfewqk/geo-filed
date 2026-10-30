@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
title GeoField - Windows Runtime Development Check
rem Safe development-only audit. Not the GeoField installer or app launcher.
rem Default performs no module imports from the private runtime and no server startup.
set "GF_SRC=%~dp0"
set "GF_MODE=--audit"
if /i "%~1"=="--check" set "GF_MODE=--check"
if not "%~1"=="" if /i not "%~1"=="--check" goto :usage
if not exist "%GF_SRC%dev_runtime_bridge.py" goto :missing
set "GF_PY="
if defined GEOFIELD_PYTHON if exist "%GEOFIELD_PYTHON%" set "GF_PY=%GEOFIELD_PYTHON%"
if not defined GF_PY if defined LOCALAPPDATA if exist "%LOCALAPPDATA%\GeoFieldCAD\engines\geofield-analysis-win64\python.exe" set "GF_PY=%LOCALAPPDATA%\GeoFieldCAD\engines\geofield-analysis-win64\python.exe"
if not defined GF_PY if defined GEOFIELD_R12_PYTHON if exist "%GEOFIELD_R12_PYTHON%" set "GF_PY=%GEOFIELD_R12_PYTHON%"
if not defined GF_PY for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do if exist "%%P" if not defined GF_PY set "GF_PY=%%P"
if not defined GF_PY for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)" 2^>nul') do if exist "%%P" if not defined GF_PY set "GF_PY=%%P"
if not defined GF_PY goto :no_python
echo [READ ONLY] GeoField existing Windows runtime verification.
echo [MODE] %GF_MODE%
echo [PYTHON] "%GF_PY%"
echo [SAFE] No installer, package downloads, FEA solver, ML inference or paid API requests.
echo [SAFE] The installed runtime and SQLite/model/STEP files remain unchanged.
"%GF_PY%" -u "%GF_SRC%dev_runtime_bridge.py" %GF_MODE% --python "%GF_PY%"
set "GF_RC=%ERRORLEVEL%"
if not "%GF_RC%"=="0" echo [RESULT] Blocked or failed, exit code %GF_RC%. Please share the error JSON, without secrets.
if "%GF_RC%"=="0" echo [RESULT] Mode %GF_MODE% succeeded. This is not proof of FEA accuracy or live API access.
pause
exit /b %GF_RC%
:usage
echo Usage: GeoField_Dev_Runtime_Check.cmd [--check]
echo No argument: static audit only. --check: also test backend imports without starting server.
goto :fail
:missing
echo [BLOCKED] dev_runtime_bridge.py not found beside this CMD.
goto :fail
:no_python
echo [BLOCKED] No installed Python interpreter identified.
echo [HINT] Set GEOFIELD_PYTHON or GEOFIELD_R12_PYTHON to an existing python.exe.
:fail
pause
exit /b 2
