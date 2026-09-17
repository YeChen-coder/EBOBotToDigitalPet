[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$RuntimeAdmin = Get-Content -LiteralPath 'local/aws-provision-admin.json' -Raw | ConvertFrom-Json
$env:AWS_CONFIG_FILE = $RuntimeAdmin.configFile
$env:AWS_SHARED_CREDENTIALS_FILE = $RuntimeAdmin.credentialsFile
$env:AWS_LOGIN_CACHE_DIRECTORY = $RuntimeAdmin.loginCacheDirectory
$env:AWS_PAGER = ''
$env:AWS_CLI_AUTO_PROMPT = 'off'
Remove-Item Env:AWS_ACCESS_KEY_ID,Env:AWS_SECRET_ACCESS_KEY,Env:AWS_SESSION_TOKEN -ErrorAction SilentlyContinue
& $RuntimeAdmin.cliPath login --profile $RuntimeAdmin.readProfile --region ca-central-1 --no-cli-pager
exit $LASTEXITCODE
