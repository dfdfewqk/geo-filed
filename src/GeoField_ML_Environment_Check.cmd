@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
title GeoField ML environment - READ ONLY, NO INFERENCE
set "GF_PACKAGE=%~dp0"
set "GF_PY="
echo [READ ONLY] This checks local GeoField ML runtime; it NEVER runs STEP inference.
echo [READ ONLY] Open GeoField_Start.cmd FIRST; no model weights or user data are changed.
if not exist "%GF_PACKAGE%verify_package.py" goto :incomplete
if not exist "%GF_PACKAGE%acceptance_probe.py" goto :incomplete
if defined LOCALAPPDATA if exist "%LOCALAPPDATA%\GeoFieldCAD\engines\geofield-analysis-win64\python.exe" set "GF_PY=%LOCALAPPDATA%\GeoFieldCAD\engines\geofield-analysis-win64\python.exe"
if not defined GF_PY for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do if exist "%%P" if not defined GF_PY set "GF_PY=%%P"
if not defined GF_PY for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)" 2^>nul') do if exist "%%P" if not defined GF_PY set "GF_PY=%%P"
if not defined GF_PY goto :no_python
"%GF_PY%" -u "%GF_PACKAGE%verify_package.py"
if errorlevel 1 goto :invalid
echo [READ ONLY] Requesting explicit BrepMFR and R12 preflight. May take up to 70 seconds.
"%GF_PY%" -u "%GF_PACKAGE%acceptance_probe.py" --check-ml-env
set "GF_RC=%ERRORLEVEL%"
echo [NOTE] Probe exit status also reflects CAD/FEA evidence, NOT just ML availability.
echo [NOTE] In the report read: brepmfr_environment, r12_environment, ml_probe_state.
echo [NOTE] Ready_for_research_inference_not_executed is NOT actual inference success.
echo [PRIVACY] Python paths, STEP files, CAD SHA, tokens and model weights are not saved.
pause
exit /b %GF_RC%
:incomplete
echo [BLOCKED] Candidate folder incomplete. No installation or Python code executed.
goto :fail
:no_python
echo [BLOCKED] Python not found. Existing GeoField remains unchanged.
goto :fail
:invalid
echo [BLOCKED] Candidate SHA verification failed. Existing GeoField unchanged.
:fail
pause
exit /b 1
