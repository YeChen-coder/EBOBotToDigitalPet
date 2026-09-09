[CmdletBinding()]
param(
    [int]$DockerTimeoutSeconds = 240,
    [int]$ServiceTimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"
$ProjectDirectory = Split-Path -Parent $PSScriptRoot
$RequiredContainers = @(
    "ebo-ai-home-homeassistant",
    "ebo-ai-home-ebo-engine",
    "ebo-ai-home-realtime-assistant"
)
$DockerReady = $false
$DockerCliFound = $false

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-DockerEngine {
    $null = & docker info --format "{{.ServerVersion}}" 2>$null
    return $LASTEXITCODE -eq 0
}

function Test-ContainerRunning {
    param([string]$ContainerName)
    $state = & docker inspect --format "{{.State.Running}}" $ContainerName 2>$null
    return $LASTEXITCODE -eq 0 -and $state.Trim() -eq "true"
}

function Test-HomeAssistant {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://localhost:8123" -TimeoutSec 4
        return $response.StatusCode -eq 200
    }
    catch {
        return $false
    }
}

function Get-AssistantHealth {
    try {
        return Invoke-RestMethod -Uri "http://localhost:8099/health" -TimeoutSec 4
    }
    catch {
        return $null
    }
}

function Assert-RequiredEnvironment {
    param([string]$EnvPath)

    if (-not (Test-Path -LiteralPath $EnvPath -PathType Leaf)) {
        throw "Missing configuration file: $EnvPath"
    }

    $requiredNames = @(
        "EBO_EMAIL",
        "EBO_PASSWORD",
        "EBO_PAYLOAD_KEY",
        "EBO_SIGN_KEY",
        "EBO_API_TOKEN",
        "OPENAI_API_KEY"
    )
    $values = @{}
    foreach ($line in Get-Content -LiteralPath $EnvPath) {
        if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$') {
            $values[$matches[1]] = $matches[2].Trim()
        }
    }

    $missing = @(
        foreach ($name in $requiredNames) {
            if (-not $values.ContainsKey($name) -or
                [string]::IsNullOrWhiteSpace($values[$name]) -or
                $values[$name] -match '^replace-with-') {
                $name
            }
        }
    )
    if ($missing.Count -gt 0) {
        throw "Required values are missing from .env: $($missing -join ', ')"
    }
}

try {
    Write-Host "EBO Home Assistant startup" -ForegroundColor White
    Write-Host "Project: $ProjectDirectory"

    if (-not (Test-Path -LiteralPath $ProjectDirectory -PathType Container)) {
        throw "Project directory not found: $ProjectDirectory"
    }
    if (-not (Test-Path -LiteralPath (Join-Path $ProjectDirectory "compose.yaml") -PathType Leaf)) {
        throw "compose.yaml was not found in the project directory."
    }

    $dockerCommand = Get-Command docker.exe -ErrorAction SilentlyContinue
    if (-not $dockerCommand) {
        $dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
    }
    if (-not $dockerCommand) {
        throw "Docker CLI is not installed or is not available in PATH. Install/start Docker Desktop."
    }
    $DockerCliFound = $true

    Write-Step "Checking Docker Desktop"
    if (-not (Test-DockerEngine)) {
        $dockerDesktopCandidates = @(
            (Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"),
            (Join-Path $env:LOCALAPPDATA "Docker\Docker Desktop.exe")
        ) | Select-Object -Unique
        $dockerDesktop = $dockerDesktopCandidates |
            Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
            Select-Object -First 1
        if (-not $dockerDesktop) {
            throw "Docker Desktop is not running and Docker Desktop.exe could not be found."
        }
        Write-Host "Docker is not ready. Starting Docker Desktop..."
        Start-Process -FilePath $dockerDesktop -WindowStyle Hidden | Out-Null
    }

    $dockerWatch = [Diagnostics.Stopwatch]::StartNew()
    while (-not (Test-DockerEngine)) {
        if ($dockerWatch.Elapsed.TotalSeconds -ge $DockerTimeoutSeconds) {
            throw "Docker did not become ready within $DockerTimeoutSeconds seconds. Open Docker Desktop and inspect its status."
        }
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 3
    }
    $DockerReady = $true
    Write-Host "Docker engine is ready." -ForegroundColor Green

    Write-Step "Checking project configuration"
    Assert-RequiredEnvironment -EnvPath (Join-Path $ProjectDirectory ".env")
    Set-Location -LiteralPath $ProjectDirectory
    & docker compose --profile assistant config --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Compose configuration validation failed."
    }
    Write-Host ".env and compose.yaml are valid." -ForegroundColor Green

    Write-Step "Starting Home Assistant, EBO Engine, and Realtime Assistant"
    & docker compose --profile assistant up -d homeassistant ebo-engine realtime-assistant
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose up failed with exit code $LASTEXITCODE."
    }

    Write-Step "Waiting for all services and media streams"
    $serviceWatch = [Diagnostics.Stopwatch]::StartNew()
    $lastProgressAt = -15
    $assistantHealth = $null
    while ($true) {
        $running = @($RequiredContainers | Where-Object { Test-ContainerRunning $_ })
        $homeAssistantReady = Test-HomeAssistant
        $assistantHealth = Get-AssistantHealth
        $assistantReady = (
            $null -ne $assistantHealth -and
            $assistantHealth.ok -eq $true -and
            $assistantHealth.realtime_connected -eq $true -and
            $assistantHealth.video_streaming -eq $true -and
            $assistantHealth.audio_streaming -eq $true
        )

        if ($running.Count -eq $RequiredContainers.Count -and
            $homeAssistantReady -and $assistantReady) {
            break
        }
        if ($serviceWatch.Elapsed.TotalSeconds -ge $ServiceTimeoutSeconds) {
            throw "Services did not become fully healthy within $ServiceTimeoutSeconds seconds."
        }
        if ($serviceWatch.Elapsed.TotalSeconds - $lastProgressAt -ge 15) {
            $lastProgressAt = [int]$serviceWatch.Elapsed.TotalSeconds
            $healthText = if ($null -eq $assistantHealth) {
                "not responding"
            }
            else {
                "realtime=$($assistantHealth.realtime_connected), video=$($assistantHealth.video_streaming), audio=$($assistantHealth.audio_streaming)"
            }
            Write-Host (
                "Waiting: containers {0}/{1}, Home Assistant={2}, Assistant={3}" -f
                $running.Count, $RequiredContainers.Count, $homeAssistantReady, $healthText
            )
        }
        Start-Sleep -Seconds 5
    }

    Write-Step "Startup completed successfully"
    & docker compose --profile assistant ps
    Write-Host ""
    Write-Host "Home Assistant: http://localhost:8123" -ForegroundColor Green
    Write-Host "Assistant health: http://localhost:8099/health" -ForegroundColor Green
    Write-Host "Realtime connected: $($assistantHealth.realtime_connected)"
    Write-Host "Video streaming: $($assistantHealth.video_streaming)"
    Write-Host "Audio streaming: $($assistantHealth.audio_streaming)"
    Write-Host "Persisted WAV files: $($assistantHealth.output_audio_files_persisted)"
    Start-Process -FilePath "http://localhost:8123" | Out-Null
    exit 0
}
catch {
    Write-Host ""
    Write-Host "STARTUP FAILED" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($DockerCliFound -and $DockerReady -and (Test-Path -LiteralPath $ProjectDirectory)) {
        Set-Location -LiteralPath $ProjectDirectory
        Write-Host ""
        Write-Host "Container status:" -ForegroundColor Yellow
        & docker compose --profile assistant ps --all 2>&1 | ForEach-Object { Write-Host $_ }
        Write-Host ""
        Write-Host "Recent logs:" -ForegroundColor Yellow
        & docker compose --profile assistant logs --tail 80 homeassistant ebo-engine realtime-assistant 2>&1 |
            ForEach-Object { Write-Host $_ }
    }
    Write-Host ""
    Write-Host "The window will remain open so this error can be read or photographed." -ForegroundColor Yellow
    exit 1
}
