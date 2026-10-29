@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
title GeoField - PRIVATE BrepMFR ML source review (read-only)
echo GeoField ML source review - no installation, model execution or external network.
echo WARNING: The review ZIP contains local Python source. Inspect it before sharing.
where py >nul 2>&1
if not errorlevel 1 (
  py -3 "%~dp0ml_runtime_source_review.py"
) else (
  where python >nul 2>&1
  if errorlevel 1 goto :no_python
  python "%~dp0ml_runtime_source_review.py"
)
set "GF_RC=%ERRORLEVEL%"
if not "%GF_RC%"=="0" echo [CHECK] Some ML source is missing or unsafe: %GF_RC%
echo Original CAD, SQLite, FEA and ML model files were not modified.
pause
exit /b %GF_RC%
:no_python
echo [BLOCKED] Python interpreter not found. Existing files untouched.
pause
exit /b 2
