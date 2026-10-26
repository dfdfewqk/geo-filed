@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
title GeoField - local runtime SOURCE review only
echo GeoField local source collection - no installation, no deletion, no network upload
echo Python files may contain private code. REVIEW the resulting ZIP before sharing.
where py >nul 2>&1
if not errorlevel 1 (
  py -3 "%~dp0runtime_source_collector.py"
) else (
  where python >nul 2>&1
  if errorlevel 1 goto :no_python
  python "%~dp0runtime_source_collector.py"
)
set "GF_RESULT=%ERRORLEVEL%"
if not "%GF_RESULT%"=="0" echo [CHECK] Inventory incomplete or blocked: %GF_RESULT%
echo Original GeoField files were not modified.
pause
exit /b %GF_RESULT%
:no_python
echo [BLOCKED] Python not found. No files were changed.
pause
exit /b 2
