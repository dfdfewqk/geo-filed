@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
title GeoField verified Windows update - CAD FEA AI
set "GF_PACKAGE=%~dp0"
echo [BUILD] GEOFIELD-20261028-WIN-COMPAT-AUDIT-3
echo [PACKAGE LOCATION] "%GF_PACKAGE%"
echo [SAFETY] Check source compatibility BEFORE installation, without removing user files.
set "PYTHONDONTWRITEBYTECODE=1"
set "GF_PY="

rem A GitHub source checkout is not an authenticated install/update bundle.
rem It includes developer tests and a candidate builder instead of a re-staged
rem 26-file manifest. Refuse before SHA checks, installation or port handling.
if exist "%GF_PACKAGE%build_integration_candidate.py" if exist "%GF_PACKAGE%tests\test_integration_candidate.py" goto :source_checkout

rem Install files must be extracted together. Do not execute this CMD inside the ZIP.
if not exist "%GF_PACKAGE%bootstrap.py" (
  set "GF_MISSING=bootstrap.py"
  goto :source_checkout
echo [SOURCE CHECKOUT] This is a GitHub source ZIP, NOT a verified Windows update package.
echo [CAUSE] Source manifest/verify_package.py are historical staging inputs, not current release signatures.
echo [SAFE] No files, solver data, SQLite or installed GeoField runtime were modified.
echo [NEXT 1] For read-only runtime inspection run GeoField_Dev_Runtime_Check.cmd in this src folder.
echo [NEXT 2] To update an installed app use an independently verified one-extract Windows candidate ZIP.
echo [NEXT 3] Do NOT edit manifest.json or verify_package.py to silence checksum mismatches.
pause
exit /b 21

:unpacked
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

echo [1/3] Verify the GeoField current 26-file source update candidate (no downloads)...
"%GF_PY%" -u "%GF_PACKAGE%verify_package.py"
if errorlevel 1 goto :invalid

echo [2/3] Validate runtime, check safe source versions and offer a backed-up repair if needed...
echo [NOTICE] Port 8600: the launcher will check and close ONLY a confirmed old GeoField backend.
echo [SAFE] Unknown listeners or child-process activity will be left running. Save work before updating.
rem A code-only mismatch offers a one-time explicit backup+approval in THIS launcher.
set "GF_OFFER_MIGRATION=1"
"%GF_PY%" -u "%GF_PACKAGE%bootstrap.py" %*
set "GF_RC=%ERRORLEVEL%"
if "%GF_RC%"=="28" goto :safe_cancel
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
:safe_cancel
echo [CANCELLED] Source migration was declined. The existing GeoField files were not changed.
pause
exit /b 0
:run_failure
echo [ERROR] GeoField startup or installation returned code %GF_RC%.
echo [LOG] %LOCALAPPDATA%\GeoFieldCAD\diagnostics\r12_launcher
if "%GF_RC%"=="25" echo [ACTION] Read geofield_version_compatibility.json. Some targets are missing, unknown, or unsafe.
if "%GF_RC%"=="25" echo [ACTION] Do NOT run GeoField_Repair.cmd until only verified existing CODE mismatches remain.
if "%GF_RC%"=="25" echo [ACTION] Share only the read-only JSON report for identifying missing/unknown categories.
if "%GF_RC%"=="26" echo [ACTION] Installed engine_runtime.py API needs a compatible release.
if "%GF_RC%"=="27" echo [ACTION] Missing or incompatible runtime modules; see geofield_version_compatibility.json.
if not "%GF_RC%"=="25" echo [CHECK] bootstrap_latest.log and backend_latest.log
:fail
pause
exit /b 1
