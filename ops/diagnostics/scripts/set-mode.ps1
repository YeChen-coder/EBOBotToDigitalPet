[CmdletBinding()]
param([Parameter(Mandatory)][ValidateSet('active', 'observe', 'maintenance')][string]$Mode)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$ConfigFile = Join-Path (Get-Location) 'config.local.json'
$DiagnosticConfig = Get-Content -LiteralPath $ConfigFile -Raw | ConvertFrom-Json
$DiagnosticConfig.observationOnly = $Mode -ne 'active'
$DiagnosticConfig.maintenance = $Mode -eq 'maintenance'
$ConfigText = $DiagnosticConfig | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($ConfigFile, $ConfigText, (New-Object System.Text.UTF8Encoding($false)))
# Reload only the monitoring system. Application containers are not touched.
& (Join-Path $PSScriptRoot 'restart-host-task.ps1')
& docker compose restart watcher
if ($LASTEXITCODE -ne 0) { throw 'Watcher reload failed' }
Write-Host ('Diagnostic mode: ' + $Mode)
