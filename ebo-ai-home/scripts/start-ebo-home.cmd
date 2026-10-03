@echo off
setlocal
chcp 65001 >nul
title Start and Update All EBO Services
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-ebo-home.ps1" -RebuildAllServices
set "EBO_START_EXIT=%ERRORLEVEL%"
echo.
if not "%EBO_START_EXIT%"=="0" (
  echo EBO startup/update failed. Review the errors above.
) else (
  echo EBO code/configuration applied. Business and diagnostic services are healthy.
)
echo Press any key to close this window.
pause >nul
exit /b %EBO_START_EXIT%
