@echo off
setlocal EnableExtensions
title Process Watcher - Start

rem Resolve the project relative to this file, never the caller's current directory.
set "ROOT=%~dp0"
cd /d "%ROOT%" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Could not change to the project directory:
  echo         %ROOT%
  echo         If the project is on a UNC share, map it to a drive letter first.
  if not defined PW_LAUNCHER_NO_PAUSE pause
  exit /b 1
)

set "PS_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%PS_EXE%" (
  echo [ERROR] Windows PowerShell was not found at:
  echo         %PS_EXE%
  if not defined PW_LAUNCHER_NO_PAUSE pause
  exit /b 1
)

"%PS_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start-processwatcher.ps1" %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
  echo.
  echo [ERROR] Process Watcher could not start. Review the messages above and .runtime\logs\.
  if not defined PW_LAUNCHER_NO_PAUSE pause
  exit /b %RC%
)

echo.
echo Process Watcher is running. You can close this window; the services keep running.
echo To stop everything, double-click Stop-ProcessWatcher.bat.
if not defined PW_LAUNCHER_NO_PAUSE pause
exit /b 0
