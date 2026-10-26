@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
title GeoField FEA EVIDENCE CLEANUP 5 - CAD FEA AI Candidate
set "GF_PACKAGE=%~dp0"
echo [BUILD] GEOFIELD-20261026-FEA-EVIDENCE-CLEANUP-5
echo [PACKAGE LOCATION] "%GF_PACKAGE%"
echo [SAFETY] Check source compatibility BEFORE installation, without removing user files.
set "PYTHONDONTWRITEBYTECODE=1"
set "GF_PY="

rem Install files must be extracted together. Do not execute this CMD inside the ZIP.
if not exist "%GF_PACKAGE%bootstrap.py" (
  set "GF_MISSING=bootstrap.py"
  goto :unpacked
)
if not exist "%GF_PACKAGE%installer.py" (
  set "GF_MISSING=installer.py"
  goto :unpacked
)
if not exist "%GF_PACKAGE%manifest.json" (
  set "GF_MISSING=manifest.json"
  goto :unpacked
)
if not exist "%GF_PACKAGE%verify_package.py" (
  set "GF_MISSING=verify_package.py"
  goto :unpacked
)
if not exist "%GF_PACKAGE%payload\GeoField_CAD_Analysis.py" (
  set "GF_MISSING=payload\GeoField_CAD_Analysis.py"
  goto :unpacked
)
if not defined LOCALAPPDATA goto :no_local

rem Prefer the existing installed GeoField runtime; no package downloads.
if exist "%LOCALAPPDATA%\GeoFieldCAD\engines\geofield-analysis-win64\python.exe" set "GF_PY=%LOCALAPPDATA%\GeoFieldCAD\engines\geofield-analysis-win64\python.exe"
if not defined GF_PY for /d %%D in ("%LOCALAPPDATA%\GeoFieldCAD\engines\r12-envs\geofield-ml-r12-*") do if exist "%%~fD\python.exe" if not defined GF_PY set "GF_PY=%%~fD\python.exe"
if not defined GF_PY for /d %%D in ("%LOCALAPPDATA%\GeoFieldCAD\engines\r12-envs\geofield-fea-r12-*") do if exist "%%~fD\python.exe" if not defined GF_PY set "GF_PY=%%~fD\python.exe"
if not defined GF_PY for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do if exist "%%P" if not defined GF_PY set "GF_PY=%%P"
if not defined GF_PY for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)" 2^>nul') do if exist "%%P" if not defined GF_PY set "GF_PY=%%P"
if not defined GF_PY goto :no_python

echo [1/3] Verify the GeoField A+B+AI update candidate package (no downloads)...
"%GF_PY%" -u "%GF_PACKAGE%verify_package.py"
if errorlevel 1 goto :invalid

echo [2/3] Validate the existing GeoField runtime and install safely...
echo [NOTICE] Port 8600: the launcher will check and close ONLY a confirmed old GeoField backend.
echo [SAFE] Unknown listeners or child-process activity will be left running. Save work before updating.
"%GF_PY%" -u "%GF_PACKAGE%bootstrap.py" %*
set "GF_RC=%ERRORLEVEL%"
if not "%GF_RC%"=="0" goto :run_failure
echo [3/3] GeoField session finished normally.
echo [LOG] %LOCALAPPDATA%\GeoFieldCAD\diagnostics\r12_launcher
pause
exit /b 0

:unpacked
echo [ERROR] GeoField source files are missing from the CMD execution directory.
echo [EXECUTED FROM] "%GF_PACKAGE%"
echo [MISSING] %GF_MISSING%
echo [CAUSE] A ZIP preview such as Bandizip may run ONLY this CMD inside a BNZ temporary folder.
echo [FIX 1] In Windows File Explorer, choose Extract All on the downloaded GitHub ZIP ONCE.
echo [FIX 2] Open the newly extracted folder using Windows File Explorer.
echo [FIX 3] Do NOT launch this CMD inside Bandizip, 7-Zip, or another archive preview.
echo [FIX 4] Run GeoField_Start.cmd next to bootstrap.py, installer.py and manifest.json.
echo [REQUIRED] verify_package.py and payload\GeoField_CAD_Analysis.py must also exist under that folder.
echo [SAFE] No GeoField installation or user engineering file was modified.
goto :fail
:no_local
echo [ERROR] LOCALAPPDATA is missing; this installer requires the existing Windows GeoField runtime.
goto :fail
:no_python
echo [ERROR] No installed Python interpreter was found. No GeoField files were changed.
goto :fail
:invalid
echo [ERROR] Package verification failed. No GeoField files were changed.
echo [FIX] Re-extract the ONE downloaded ZIP using Windows File Explorer. Do not disable antivirus.
goto :fail
:run_failure
echo [ERROR] GeoField startup or installation returned code %GF_RC%.
echo [LOG] %LOCALAPPDATA%\GeoFieldCAD\diagnostics\r12_launcher
echo [CHECK] bootstrap_latest.log and backend_latest.log
:fail
pause
exit /b 1
