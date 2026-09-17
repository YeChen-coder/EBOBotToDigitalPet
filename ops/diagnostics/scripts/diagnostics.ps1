[CmdletBinding()]
param([ValidateSet('start','status','pause','resume','stop','reports','report','reload','login','environment','sampling','sampling-cost','dashboard')][string]$Action='status', [string]$Id,
  [ValidateSet('local','aws','stopped')][string]$Environment, [ValidateRange(30,3600)][int]$Seconds=60)
$ErrorActionPreference='Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
function Invoke-Docker { & docker @args; if ($LASTEXITCODE -ne 0) { throw 'Diagnostic Docker operation failed' } }
switch ($Action) {
  'dashboard' {
    Start-Process -FilePath 'http://127.0.0.1:8179'
  }
  'start' {
    if (-not (Get-ScheduledTask -TaskName 'EBO Diagnostics Host Bridge' -ErrorAction SilentlyContinue)) { & "$PSScriptRoot/install-host-task.ps1" }
    Start-ScheduledTask -TaskName 'EBO Diagnostics Host Bridge'
    Invoke-Docker compose up -d --wait
    & "$PSScriptRoot/set-mode.ps1" -Mode active
  }
  'status' {
    Invoke-Docker compose ps
    & node --env-file=.env scripts/status.mjs --compact
    if ($LASTEXITCODE -ne 0) { throw 'Watcher status unavailable; start diagnostics first' }
  }
  'pause' { & "$PSScriptRoot/set-mode.ps1" -Mode observe }
  'resume' { & "$PSScriptRoot/set-mode.ps1" -Mode active }
  'reload' { & "$PSScriptRoot/restart-host-task.ps1"; Invoke-Docker compose up -d --wait --force-recreate }
  'stop' {
    & "$PSScriptRoot/set-mode.ps1" -Mode maintenance
    # Let the Watcher suppress incidents and forward cancellations before shutting down its peers.
    Start-Sleep -Seconds 12
    Invoke-Docker compose stop
    Stop-ScheduledTask -TaskName 'EBO Diagnostics Host Bridge'
  }
  'reports' { Invoke-Docker compose exec -T diagnostic-service node src/report.mjs }
  'report' {
    if ($Id -notmatch '^[a-zA-Z0-9_-]{1,100}$') { throw 'Provide -Id from the reports list' }
    Invoke-Docker compose exec -T diagnostic-service node src/report.mjs $Id
  }
  'login' { & "$PSScriptRoot/use-local-codex-login.ps1" }
  'environment' {
    if (-not $Environment) { throw 'Provide -Environment local, aws or stopped' }
    & node --env-file=.env scripts/runtime.mjs $Environment
    if ($LASTEXITCODE -ne 0) { throw 'Runtime transition incomplete; see http://127.0.0.1:8179' }
  }
  'sampling' {
    & node scripts/configure.mjs sampling $Seconds
    if ($LASTEXITCODE -ne 0) { throw 'Sampling configuration failed' }
    & "$PSScriptRoot/restart-host-task.ps1"
    Invoke-Docker compose up -d --wait --force-recreate watcher
  }
  'sampling-cost' {
    & node scripts/sampling-cost.mjs
    if ($LASTEXITCODE -ne 0) { throw 'Sampling measurement incomplete' }
  }
}
