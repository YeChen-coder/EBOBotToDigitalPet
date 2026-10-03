[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('father','mother')][string]$User,
    [Parameter(Mandatory=$true)][string]$PhotoDirectory
)
$ErrorActionPreference = 'Stop'
$ProjectDirectory = Split-Path -Parent $PSScriptRoot
$PhotoPath = (Resolve-Path -LiteralPath $PhotoDirectory).Path
if (-not (Test-Path -LiteralPath $PhotoPath -PathType Container)) { throw 'PhotoDirectory must be a directory of photos for one parent.' }
Push-Location -LiteralPath $ProjectDirectory
try {
    # This temporary process sends photos only to the internal Frigate face API.
    & docker compose --profile assistant run --rm --no-deps -v "${PhotoPath}:/photos:ro" realtime-assistant python register_faces.py --user $User --photo-directory /photos
    if ($LASTEXITCODE -ne 0) { throw 'Face registration did not complete. Check the supplied photos and Frigate status.' }
} finally { Pop-Location }
