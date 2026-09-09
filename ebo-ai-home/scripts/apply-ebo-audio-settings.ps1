[CmdletBinding()]
param(
    [int]$HealthTimeoutSeconds = 300,
    [string]$ProjectDirectory = ""
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($ProjectDirectory)) {
    $ProjectDirectory = Split-Path -Parent $PSScriptRoot
}
$HomeAssistantContainer = "ebo-ai-home-homeassistant"
$EngineContainer = "ebo-ai-home-ebo-engine"
$AssistantContainer = "ebo-ai-home-realtime-assistant"
$AudioKeys = @(
    "EBO_AGORA_AEC_ENABLED",
    "EBO_AGORA_NOISE_SUPPRESSION_ENABLED",
    "EBO_AGORA_AGC_ENABLED"
)
$DockerReady = $false

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-DockerEngine {
    $null = & docker info --format "{{.ServerVersion}}" 2>$null
    return $LASTEXITCODE -eq 0
}

function Get-ContainerIdentity {
    param([string]$ContainerName)
    $identity = & docker inspect --format "{{.Id}}|{{.State.Running}}|{{.State.StartedAt}}" $ContainerName 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($identity)) {
        return $null
    }
    return $identity.Trim()
}

function Get-AssistantHealth {
    try {
        return Invoke-RestMethod -Uri "http://localhost:8099/health" -TimeoutSec 4
    }
    catch {
        return $null
    }
}

function Read-DotEnv {
    param([string]$EnvPath)
    if (-not (Test-Path -LiteralPath $EnvPath -PathType Leaf)) {
        throw "Missing configuration file: $EnvPath"
    }
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $EnvPath) {
        if ($line -match '^\s*#' -or $line -notmatch '^\s*([^=\s]+)\s*=\s*(.*)$') {
            continue
        }
        $values[$matches[1]] = $matches[2].Trim()
    }
    return $values
}

function ConvertTo-CanonicalBool {
    param([string]$Name, [string]$Value)
    switch ($Value.Trim().ToLowerInvariant()) {
        { $_ -in @("1", "true", "yes", "on") } { return "true" }
        { $_ -in @("0", "false", "no", "off") } { return "false" }
        default {
            throw "$Name must be true/false, 1/0, yes/no, or on/off (got '$Value')."
        }
    }
}

function Get-ContainerEnvironment {
    param([string]$ContainerName)
    $lines = & docker inspect --format "{{range .Config.Env}}{{println .}}{{end}}" $ContainerName
    if ($LASTEXITCODE -ne 0) {
        throw "Could not inspect environment for $ContainerName."
    }
    $values = @{}
    foreach ($line in $lines) {
        if ($line -match '^([^=]+)=(.*)$') {
            $values[$matches[1]] = $matches[2]
        }
    }
    return $values
}

function Show-Diagnostics {
    Write-Host ""
    Write-Host "Container status:" -ForegroundColor Yellow
    & docker compose --profile assistant ps --all 2>&1 | ForEach-Object { Write-Host $_ }
    Write-Host ""
    Write-Host "Recent EBO Engine logs:" -ForegroundColor Yellow
    & docker logs --tail 180 $EngineContainer 2>&1 | ForEach-Object { Write-Host $_ }
    Write-Host ""
    Write-Host "Recent Realtime Assistant logs:" -ForegroundColor Yellow
    & docker logs --tail 140 $AssistantContainer 2>&1 | ForEach-Object { Write-Host $_ }
}

try {
    Write-Host "Apply EBO Engine Agora audio-processing settings" -ForegroundColor White
    Write-Host "Only EBO Engine and Realtime Assistant will be rebuilt/recreated."

    if (-not (Test-Path -LiteralPath $ProjectDirectory -PathType Container)) {
        throw "Project directory not found: $ProjectDirectory"
    }
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker CLI is not installed or is not available in PATH."
    }
    if (-not (Test-DockerEngine)) {
        throw "Docker Desktop is not running."
    }
    $DockerReady = $true
    Set-Location -LiteralPath $ProjectDirectory

    Write-Step "Validating .env audio switches and Docker Compose"
    $envValues = Read-DotEnv -EnvPath (Join-Path $ProjectDirectory ".env")
    $expected = @{}
    foreach ($key in $AudioKeys) {
        if (-not $envValues.ContainsKey($key) -or [string]::IsNullOrWhiteSpace($envValues[$key])) {
            throw "$key is missing or empty in .env."
        }
        $expected[$key] = ConvertTo-CanonicalBool -Name $key -Value $envValues[$key]
        Write-Host "$key=$($expected[$key])"
    }
    & docker compose --profile assistant config --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose configuration validation failed."
    }

    $homeAssistantBefore = Get-ContainerIdentity $HomeAssistantContainer
    if ($null -eq $homeAssistantBefore -or $homeAssistantBefore -notmatch '\|true\|') {
        throw "$HomeAssistantContainer is not running. Start the stack before applying this change."
    }
    $engineBefore = Get-ContainerIdentity $EngineContainer
    $assistantBefore = Get-ContainerIdentity $AssistantContainer

    Write-Step "Building the latest EBO Engine image"
    & docker compose --profile assistant build ebo-engine
    if ($LASTEXITCODE -ne 0) {
        throw "EBO Engine image build failed with exit code $LASTEXITCODE."
    }

    Write-Step "Recreating only EBO Engine and Realtime Assistant"
    & docker compose --profile assistant up -d --no-deps --force-recreate ebo-engine realtime-assistant
    if ($LASTEXITCODE -ne 0) {
        throw "Container recreation failed with exit code $LASTEXITCODE."
    }

    $homeAssistantAfter = Get-ContainerIdentity $HomeAssistantContainer
    if ($homeAssistantAfter -ne $homeAssistantBefore) {
        throw "Home Assistant changed unexpectedly."
    }
    $engineAfter = Get-ContainerIdentity $EngineContainer
    $assistantAfter = Get-ContainerIdentity $AssistantContainer
    if ($null -eq $engineAfter -or $engineAfter -notmatch '\|true\|') {
        throw "The new EBO Engine container is not running."
    }
    if ($null -eq $assistantAfter -or $assistantAfter -notmatch '\|true\|') {
        throw "The new Realtime Assistant container is not running."
    }
    if ($null -ne $engineBefore -and $engineAfter -eq $engineBefore) {
        throw "EBO Engine was not recreated."
    }
    if ($null -ne $assistantBefore -and $assistantAfter -eq $assistantBefore) {
        throw "Realtime Assistant was not recreated."
    }

    Write-Step "Verifying the EBO Engine container environment"
    $containerEnv = Get-ContainerEnvironment $EngineContainer
    foreach ($key in $AudioKeys) {
        if (-not $containerEnv.ContainsKey($key)) {
            throw "$key was not passed into the EBO Engine container."
        }
        $actual = ConvertTo-CanonicalBool -Name $key -Value $containerEnv[$key]
        if ($actual -ne $expected[$key]) {
            throw "$key mismatch: .env=$($expected[$key]), container=$actual."
        }
        Write-Host "$key=$actual" -ForegroundColor Green
    }

    $aecState = if ($expected["EBO_AGORA_AEC_ENABLED"] -eq "true") { "on" } else { "off" }
    $nsState = if ($expected["EBO_AGORA_NOISE_SUPPRESSION_ENABLED"] -eq "true") { "on" } else { "off" }
    $agcState = if ($expected["EBO_AGORA_AGC_ENABLED"] -eq "true") { "on" } else { "off" }
    $apmRequested = $expected.Values -contains "true"
    $apmState = if ($apmRequested) { "on" } else { "off" }
    $requestMarker = "[audio-apm] requested: aec=$aecState noise_suppression=$nsState agc=$agcState apm=$apmState"

    Write-Step "Waiting for RTC, video, robot-mic PCM, talk-stream, and APM verification"
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $lastProgressAt = -15
    $health = $null
    $engineLogs = ""
    while ($true) {
        $health = Get-AssistantHealth
        $engineLogs = (& docker logs $EngineContainer 2>&1) -join "`n"
        $healthReady = (
            $null -ne $health -and
            $health.ok -eq $true -and
            $health.realtime_connected -eq $true -and
            $health.video_streaming -eq $true -and
            $health.audio_streaming -eq $true
        )
        $rtcReady = $engineLogs.Contains("[RTC] connected")
        $talkStreamReady = $engineLogs.Contains("[talk-stream] internal PCM WebSocket listening")
        $requestSeen = $engineLogs.Contains($requestMarker)
        $initSeen = $engineLogs.Contains("[audio-apm] Agora service initialized (rc=0, apm=$apmState)")
        $filterReady = (-not $apmRequested) -or $engineLogs -match '\[audio-apm\] remote playback filter attached uid=.* rc=0(?:\D|$)'
        $filterFailed = $apmRequested -and $engineLogs -match '\[audio-apm\] remote playback filter attached uid=.* rc=(?!0(?:\D|$))-?\d+'
        if ($filterFailed) {
            throw "Agora attached the remote-playback APM filter, but setting its configuration returned an error."
        }
        if ($healthReady -and $rtcReady -and $talkStreamReady -and $requestSeen -and $initSeen -and $filterReady) {
            break
        }
        if ($watch.Elapsed.TotalSeconds -ge $HealthTimeoutSeconds) {
            throw "Audio services/APM did not become fully ready within $HealthTimeoutSeconds seconds."
        }
        if ($watch.Elapsed.TotalSeconds - $lastProgressAt -ge 15) {
            $lastProgressAt = [int]$watch.Elapsed.TotalSeconds
            $healthText = if ($null -eq $health) {
                "health endpoint not responding"
            }
            else {
                "realtime=$($health.realtime_connected), video=$($health.video_streaming), audio=$($health.audio_streaming)"
            }
            Write-Host "Waiting: $healthText, rtc=$rtcReady, talk_stream=$talkStreamReady, apm_filter=$filterReady"
        }
        Start-Sleep -Seconds 5
    }

    Write-Step "EBO audio settings applied successfully"
    Write-Host "Requested: AEC=$aecState, noise suppression=$nsState, AGC=$agcState" -ForegroundColor Green
    Write-Host "Agora service initialization: rc=0" -ForegroundColor Green
    if ($apmRequested) {
        Write-Host "Remote robot audio-track APM filter: rc=0" -ForegroundColor Green
    }
    Write-Host "RTC connected; video, robot microphone PCM, and custom talk-stream are ready." -ForegroundColor Green
    Write-Host "Home Assistant was not restarted." -ForegroundColor Green
    exit 0
}
catch {
    Write-Host ""
    Write-Host "EBO AUDIO SETTINGS APPLY FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($DockerReady -and (Test-Path -LiteralPath $ProjectDirectory -PathType Container)) {
        Set-Location -LiteralPath $ProjectDirectory
        Show-Diagnostics
    }
    exit 1
}
