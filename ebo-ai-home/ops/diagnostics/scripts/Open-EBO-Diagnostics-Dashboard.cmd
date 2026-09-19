@echo off
setlocal
set "DIAGNOSTICS_DIR=%USERPROFILE%\Documents\ChatGPT\EBOBotRelated\ebo-ai-home\ops\diagnostics"
set "DASHBOARD_URL=http://127.0.0.1:8179/"

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference = 'Stop';" ^
  "$url = $env:DASHBOARD_URL;" ^
  "$ready = $false;" ^
  "try { $ready = (Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 3).StatusCode -eq 200 } catch {}" ^
  "if (-not $ready) {" ^
  "  Write-Host 'EBO Diagnostic Dashboard is not running. Starting diagnostics...';" ^
  "  & (Join-Path $env:DIAGNOSTICS_DIR 'scripts\diagnostics.ps1') start;" ^
  "  $deadline = (Get-Date).AddSeconds(60);" ^
  "  do { try { $ready = (Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 3).StatusCode -eq 200 } catch { $ready = $false }; if (-not $ready) { Start-Sleep -Seconds 1 } } while (-not $ready -and (Get-Date) -lt $deadline);" ^
  "}" ^
  "if (-not $ready) { throw 'Dashboard did not become available at http://127.0.0.1:8179/' }" ^
  "Start-Process $url"

if errorlevel 1 (
  echo.
  echo Unable to open the EBO Diagnostic Dashboard. Make sure Docker Desktop is running.
  pause
  exit /b 1
)

endlocal
