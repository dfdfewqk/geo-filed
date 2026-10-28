@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
title GeoField A12 READ-ONLY PREFLIGHT - NO INSTALL OR FEA
set "GF_PACKAGE=%~dp0"
set "GF_PY="
echo [A12 PREFLIGHT] READ ONLY. No installation, server stop, STEP import, ML or FEA.
if not exist "%GF_PACKAGE%verify_package.py" goto :missing
if not exist "%GF_PACKAGE%bootstrap.py" goto :missing
if not exist "%GF_PACKAGE%manifest.json" goto :missing
if not exist "%GF_PACKAGE%payload\GeoField_CAD_Analysis.py" goto :missing
if not defined LOCALAPPDATA goto :local_missing
if exist "%LOCALAPPDATA%\GeoFieldCAD\engines\geofield-analysis-win64\python.exe" set "GF_PY=%LOCALAPPDATA%\GeoFieldCAD\engines\geofield-analysis-win64\python.exe"
if not defined GF_PY for /f "delims=" %%P in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do if exist "%%P" if not defined GF_PY set "GF_PY=%%P"
if not defined GF_PY for /f "delims=" %%P in ('python -c "import sys;print(sys.executable)" 2^>nul') do if exist "%%P" if not defined GF_PY set "GF_PY=%%P"
if not defined GF_PY goto :python_missing
set "PYTHONDONTWRITEBYTECODE=1"
echo [1/2] Verify unpacked 22-file source-lock and all package contents.
"%GF_PY%" -B -u "%GF_PACKAGE%verify_package.py"
if errorlevel 1 goto :invalid
echo [2/2] AUDIT ONLY: preexisting runtime files, static API and engine compatibility.
echo [NOTE] Paths may appear on YOUR screen. Redact paths/identifiers before sharing.
"%GF_PY%" -B -u "%GF_PACKAGE%bootstrap.py" --audit-runtime
set "GF_RC=%ERRORLEVEL%"
if not "%GF_RC%"=="0" (
  echo [STOP] Installed runtime NOT YET VERIFIED. Do NOT start the update or solve.
  echo [ACTION] Save the audit finding for Antigravity. No retry of the real game/FEA is needed.
  goto :finished
)
echo [PASS] Installed runtime static compatibility and source inventory checked.
echo [LIMIT] Does not prove successful imports, DLLs, Gmsh, CalculiX, 3D graphics or real solve.
echo [NEXT] Only after other checks, perform ONE actual GeoField_Start.cmd trial.
:finished
pause
exit /b %GF_RC%
:missing
echo [ERROR] Missing candidate file. Extract the ONE-EXTRACT ZIP once in File Explorer.
goto :fail
:local_missing
echo [ERROR] LOCALAPPDATA not available. No changes made.
goto :fail
:python_missing
echo [ERROR] No installed Python found. No dependencies downloaded.
goto :fail
:invalid
echo [ERROR] Package SHA-256 verification failed. No changes made.
:fail
pause
exit /b 1
