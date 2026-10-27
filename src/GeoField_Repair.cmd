@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul 2>&1
title GeoField SAFE CODE MIGRATION - KEEP ORIGINALS
if not exist "%~dp0GeoField_Start.cmd" (
  echo [ERROR] Extract the complete ZIP first. GeoField_Start.cmd missing.
  pause
  exit /b 1
)
echo [NOTICE] Explicit code repair: only approved source files are eligible.
echo [NOTICE] Existing files are SHA-256 backed up BEFORE replacement.
echo [NOTICE] Original STEP, SQLite, INP, STA, FRD and ML weights are NOT touched.
echo [NOTICE] Unknown or missing runtime dependencies and unsafe symlinks remain BLOCKED.
call "%~dp0GeoField_Start.cmd" --migrate-local-code
exit /b %ERRORLEVEL%
