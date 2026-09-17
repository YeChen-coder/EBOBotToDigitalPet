[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$DiagnosticRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $DiagnosticRoot
$NodeBinary = (Get-Command node.exe -ErrorAction Stop).Source
New-Item -ItemType Directory -Path (Join-Path $DiagnosticRoot 'local') -Force | Out-Null
# Credentials are loaded from disk by Node; never place their values on a command line.
& $NodeBinary --env-file=.env src/host-bridge.mjs
exit $LASTEXITCODE
