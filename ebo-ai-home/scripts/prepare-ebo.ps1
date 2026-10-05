param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$envPath = Join-Path $ProjectRoot '.env'
$dataPath = Join-Path $ProjectRoot 'ebo-data'
$optionsPath = Join-Path $dataPath 'options.json'

if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Missing $envPath. Copy .env.example to .env and fill in the EBO values."
}

$values = @{}
foreach ($line in Get-Content -LiteralPath $envPath) {
    if ($line -match '^\s*#' -or $line -notmatch '=') { continue }
    $name, $value = $line -split '=', 2
    $values[$name.Trim()] = $value.Trim()
}

$required = 'EBO_EMAIL', 'EBO_PASSWORD', 'EBO_PAYLOAD_KEY', 'EBO_SIGN_KEY', 'EBO_API_TOKEN'
$missing = @($required | Where-Object { -not $values[$_] })
if ($missing.Count -gt 0) {
    throw "Fill these values in .env first: $($missing -join ', ')"
}

New-Item -ItemType Directory -Force -Path $dataPath | Out-Null

$options = [ordered]@{
    email = $values['EBO_EMAIL']
    password = $values['EBO_PASSWORD']
    payload_key = $values['EBO_PAYLOAD_KEY']
    sign_key = $values['EBO_SIGN_KEY']
    api_token = $values['EBO_API_TOKEN']
    host_ip = $values['EBO_HOST_IP']
    region = if ($values['EBO_REGION']) { $values['EBO_REGION'] } else { 'GB' }
    host = if ($values['EBO_CLOUD_HOST']) { $values['EBO_CLOUD_HOST'] } else { 'ebox-eu.enabotserverintl.com' }
    robot_id = 0
    video = $true
    audio = $true
    talk = $false
    video_max_height = 720
    video_fps = 20
    video_bitrate = 2500
    video_preset = 'ultrafast'
    audio_codec = '8'
    standby_after_minutes = 5
    mcp = $false
    log_level = 'info'
}

# Use UTF-8 without a BOM so jq in the Linux container can read it reliably.
$json = $options | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText($optionsPath, $json, [System.Text.UTF8Encoding]::new($false))
Write-Host "Prepared $optionsPath"
Write-Host "Start EBO with: docker compose --profile ebo up -d"
