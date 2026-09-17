[CmdletBinding()]
param([string]$AuthFile = (Join-Path $env:USERPROFILE '.codex/auth.json'))
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
if (-not (Test-Path -LiteralPath $AuthFile -PathType Leaf)) { throw 'Local Codex auth.json is unavailable. Use a dedicated container login instead.' }
# Copy just authentication into a private Docker volume; no settings, hooks, skills or task history.
foreach ($WorkerService in @('codex-worker', 'codex-triage')) {
& docker compose cp $AuthFile ($WorkerService + ':/home/node/.codex/auth.import.json')
if ($LASTEXITCODE -ne 0) { throw 'Authentication copy failed' }
& docker compose exec -T $WorkerService node --input-type=module -e "import fs from 'node:fs'; const p='/home/node/.codex/'; fs.writeFileSync(p+'auth.new.json',fs.readFileSync(p+'auth.import.json'),{mode:0o600}); fs.renameSync(p+'auth.new.json',p+'auth.json'); fs.unlinkSync(p+'auth.import.json');"
if ($LASTEXITCODE -ne 0) { throw 'Authentication import failed' }
}
Write-Host 'Only the login file was copied into the dedicated Codex volume. No credential values were displayed.'
