@echo off
chcp 65001 >nul
title Rebuild and Restart EBO Local Docker
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-ebo-home.ps1" -RebuildAllThree
set "EBO_REBUILD_EXIT=%ERRORLEVEL%"
echo.
if not "%EBO_REBUILD_EXIT%"=="0" (
  echo EBO rebuild or health check failed. See the error and logs above.
) else (
  echo All five local EBO containers were recreated and are healthy.
)
echo Press any key to close this window.
pause >nul
exit /b %EBO_REBUILD_EXIT%
