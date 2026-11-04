@echo off
setlocal EnableExtensions
title Process Watcher - Stop

set "ROOT=%~dp0"
cd /d "%ROOT%" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Could not change to the project directory:
  echo         %ROOT%
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

"%PS_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\stop-processwatcher.ps1" %*
set "RC=%ERRORLEVEL%"

echo.
if not "%RC%"=="0" echo [ERROR] Some processes could not be stopped. See the messages above.
if not defined PW_LAUNCHER_NO_PAUSE pause
exit /b %RC%
