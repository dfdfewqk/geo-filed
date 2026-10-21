@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
title GeoField R12.13 - Port 8600 Auto Recovery
set "GF_PACKAGE=%~dp0"
set "GF_PY="

rem Install files must be extracted together. Do not execute this CMD inside the ZIP.
if not exist "%GF_PACKAGE%bootstrap.py" goto :unpacked
if not exist "%GF_PACKAGE%installer.py" goto :unpacked
if not exist "%GF_PACKAGE%manifest.json" goto :unpacked
if not exist "%GF_PACKAGE%verify_package.py" goto :unpacked
if not exist "%GF_PACKAGE%payload\GeoField_CAD_Analysis.py" goto :unpacked
if not defined LOCALAPPDATA goto :no_local

rem Prefer the existing installed GeoField runtime; no package downloads.
if exist "%LOCALAPPDATA%\GeoFieldCAD\engines\geofield-analysis-win64\python.exe" set "GF_PY=%LOCALAPPDATA%\GeoFieldCAD\engines\geofield-analysis-win64\python.exe"
if not defined GF_PY for /d %%D in ("%LOCALAPPDATA%\GeoFieldCAD\engines\r12-envs\geofield-ml-r12-*") do if exist "%%~fD\python.exe" if not defined GF_PY set "GF_PY=%%~fD\python.exe"
if not defined GF_PY for /d %%D in ("%LOCALAPPDATA%\GeoFieldCAD\engines\r12-envs\geofield-fea-r12-*") do if exist "%%~fD\python.exe" if not defined GF_PY set "GF_PY=%%~fD\python.exe"
if not defined GF_PY for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do if exist "%%P" if not defined GF_PY set "GF_PY=%%P"
if not defined GF_PY for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)" 2^>nul') do if exist "%%P" if not defined GF_PY set "GF_PY=%%P"
if not defined GF_PY goto :no_python

echo [1/3] Verify the R12.13 final test local package (no downloads)...
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
echo [ERROR] The ZIP has not been fully extracted or the CMD has been separated from its files.
echo [FIX] Right-click the ONE GeoField R12.13 FINAL TEST ZIP and select Extract All.
echo [FIX] Open the extracted folder and run GeoField_Start.cmd INSIDE that folder.
goto :fail
:no_local
echo [ERROR] LOCALAPPDATA is missing; this installer requires the existing Windows GeoField runtime.
goto :fail
:no_python
echo [ERROR] No installed Python interpreter was found. No GeoField files were changed.
goto :fail
:invalid
echo [ERROR] Package verification failed. No GeoField files were changed.
echo [FIX] Re-extract the original ZIP; do not disable antivirus.
goto :fail
:run_failure
echo [ERROR] GeoField startup or installation returned code %GF_RC%.
echo [LOG] %LOCALAPPDATA%\GeoFieldCAD\diagnostics\r12_launcher
echo [CHECK] bootstrap_latest.log and backend_latest.log
:fail
pause
exit /b 1
