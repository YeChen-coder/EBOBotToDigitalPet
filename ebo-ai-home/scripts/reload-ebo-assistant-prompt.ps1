[CmdletBinding()]
param(
    [int]$HealthTimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"
$ProjectDirectory = Split-Path -Parent $PSScriptRoot
$AssistantContainer = "ebo-ai-home-realtime-assistant"
$ProtectedContainers = @(
    "ebo-ai-home-homeassistant",
    "ebo-ai-home-ebo-engine"
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

function Assert-PromptConfigured {
    param([string]$EnvPath)

    if (-not (Test-Path -LiteralPath $EnvPath -PathType Leaf)) {
        throw "Missing configuration file: $EnvPath"
    }
    $promptLine = Get-Content -LiteralPath $EnvPath |
        Where-Object { $_ -match '^\s*EBO_ASSISTANT_INSTRUCTIONS\s*=' } |
        Select-Object -Last 1
    if ($null -eq $promptLine -or
        $promptLine -notmatch '^\s*EBO_ASSISTANT_INSTRUCTIONS\s*=(.*)$' -or
        [string]::IsNullOrWhiteSpace($matches[1])) {
        throw "EBO_ASSISTANT_INSTRUCTIONS is missing or empty in .env. The assistant was not changed."
    }
}

try {
    Write-Host "Apply updated EBO assistant prompt" -ForegroundColor White
    Write-Host "Only the Realtime Assistant container will be recreated."

    if (-not (Test-Path -LiteralPath $ProjectDirectory -PathType Container)) {
        throw "Project directory not found: $ProjectDirectory"
    }
    if (-not (Get-Command docker.exe -ErrorAction SilentlyContinue) -and
        -not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker CLI is not installed or is not available in PATH."
    }
    if (-not (Test-DockerEngine)) {
        throw "Docker Desktop is not running. Use the full desktop startup script first."
    }
    $DockerReady = $true
    Set-Location -LiteralPath $ProjectDirectory

    Write-Step "Checking .env and the updated prompt"
    Assert-PromptConfigured -EnvPath (Join-Path $ProjectDirectory ".env")
    & docker compose --profile assistant config --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose configuration validation failed."
    }
    Write-Host "Prompt is present and Docker Compose configuration is valid." -ForegroundColor Green
    Write-Host "The prompt text is intentionally not printed." 

    $protectedBefore = @{}
    foreach ($container in $ProtectedContainers) {
        $identity = Get-ContainerIdentity $container
        if ($null -eq $identity -or $identity -notmatch '\|true\|') {
            throw "$container is not running. Use the full desktop startup script first."
        }
        $protectedBefore[$container] = $identity
    }
    $assistantBefore = Get-ContainerIdentity $AssistantContainer

    Write-Step "Recreating only the Realtime Assistant container"
    & docker compose --profile assistant up -d --no-deps --force-recreate realtime-assistant
    if ($LASTEXITCODE -ne 0) {
        throw "Realtime Assistant recreation failed with exit code $LASTEXITCODE."
    }

    foreach ($container in $ProtectedContainers) {
        $identityAfter = Get-ContainerIdentity $container
        if ($identityAfter -ne $protectedBefore[$container]) {
            throw "$container changed unexpectedly. Review the logs below."
        }
    }
    $assistantAfter = Get-ContainerIdentity $AssistantContainer
    if ($null -eq $assistantAfter -or $assistantAfter -notmatch '\|true\|') {
        throw "The new Realtime Assistant container is not running."
    }
    if ($null -ne $assistantBefore -and $assistantAfter -eq $assistantBefore) {
        throw "The Realtime Assistant container was not recreated."
    }

    Write-Step "Waiting for Realtime, video, and audio to recover"
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $lastProgressAt = -15
    $health = $null
    while ($true) {
        $health = Get-AssistantHealth
        $ready = (
            $null -ne $health -and
            $health.ok -eq $true -and
            $health.realtime_connected -eq $true -and
            $health.video_streaming -eq $true -and
            $health.audio_streaming -eq $true
        )
        if ($ready) {
            break
        }
        if ($watch.Elapsed.TotalSeconds -ge $HealthTimeoutSeconds) {
            throw "The Realtime Assistant did not become fully healthy within $HealthTimeoutSeconds seconds."
        }
        if ($watch.Elapsed.TotalSeconds - $lastProgressAt -ge 15) {
            $lastProgressAt = [int]$watch.Elapsed.TotalSeconds
            $healthText = if ($null -eq $health) {
                "not responding"
            }
            else {
                "realtime=$($health.realtime_connected), video=$($health.video_streaming), audio=$($health.audio_streaming)"
            }
            Write-Host "Waiting: $healthText"
        }
        Start-Sleep -Seconds 5
    }

    Write-Step "Prompt update applied successfully"
    Write-Host "Realtime connected: $($health.realtime_connected)" -ForegroundColor Green
    Write-Host "Video streaming: $($health.video_streaming)" -ForegroundColor Green
    Write-Host "Audio streaming: $($health.audio_streaming)" -ForegroundColor Green
    Write-Host "Home Assistant and EBO Engine were not restarted." -ForegroundColor Green
    Write-Host "A new Realtime session is now using the prompt from .env."
    exit 0
}
catch {
    Write-Host ""
    Write-Host "PROMPT RELOAD FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($DockerReady -and (Test-Path -LiteralPath $ProjectDirectory)) {
        Set-Location -LiteralPath $ProjectDirectory
        Write-Host ""
        Write-Host "Container status:" -ForegroundColor Yellow
        & docker compose --profile assistant ps --all 2>&1 | ForEach-Object { Write-Host $_ }
        Write-Host ""
        Write-Host "Recent Realtime Assistant logs:" -ForegroundColor Yellow
        & docker compose --profile assistant logs --tail 100 realtime-assistant 2>&1 |
            ForEach-Object { Write-Host $_ }
    }
    Write-Host ""
    Write-Host "The window will remain open so this error can be read or photographed." -ForegroundColor Yellow
    exit 1
}
