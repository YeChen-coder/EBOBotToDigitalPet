[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$ProjectDirectory = Split-Path -Parent $PSScriptRoot
$DiagnosticDirectory = Join-Path $ProjectDirectory 'ops\diagnostics'
$TaskNames = @('EBO Diagnostics Host Bridge', 'EBO Diagnostics Health Report')
$Projects = @('ebo-ai-home', 'ebo-diagnostics')
$Problems = New-Object 'System.Collections.Generic.List[string]'
$TemporaryBridge = $null
$ShutdownVerified = $false
$LocalScopeConfigured = $false

function Add-Problem([string]$Message) {
    $Problems.Add($Message)
    Write-Host $Message -ForegroundColor Red
}

function Get-ProjectContainers {
    foreach ($project in $Projects) {
        $ids = @(& docker ps -aq --filter "label=com.docker.compose.project=$project")
        if ($LASTEXITCODE -ne 0) { throw 'Unable to list EBO containers. Check Docker Desktop.' }
        foreach ($id in $ids) { if ($id) { $id.Trim() } }
    }
}

Write-Host 'Stopping local EBO business services, diagnostics, and background tasks...' -ForegroundColor Cyan
Write-Host 'Configuration, recordings, images, and Docker volumes are preserved.'

try {
    $configPath = Join-Path $DiagnosticDirectory 'config.local.json'
    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    $config | Add-Member -NotePropertyName runtimeControlScope -NotePropertyValue 'local' -Force
    $config.maintenance = $true
    $config.observationOnly = $true
    [IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 30), (New-Object Text.UTF8Encoding($false)))
    $LocalScopeConfigured = $true
} catch { Add-Problem "Could not configure local shutdown: $($_.Exception.Message)" }

# Disable logon/retry launches while the controller completes local shutdown.
foreach ($taskName in $TaskNames) {
    try {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($task) { Disable-ScheduledTask -TaskName $taskName | Out-Null }
    } catch { Add-Problem "Could not disable task ${taskName}: $($_.Exception.Message)" }
}

try {
    if (-not $LocalScopeConfigured) { throw 'Local-only scope could not be saved; skipping the runtime controller.' }
    $tokenLine = Get-Content -LiteralPath (Join-Path $DiagnosticDirectory '.env') |
        Where-Object { $_ -match '^BRIDGE_TOKEN=' } | Select-Object -First 1
    if (-not $tokenLine) { throw 'BRIDGE_TOKEN is missing from diagnostic configuration.' }
    $headers = @{ Authorization = 'Bearer ' + ($tokenLine -split '=', 2)[1].Trim() }
    $runtimeUrl = 'http://127.0.0.1:8177/runtime'
    try {
        $runtime = Invoke-RestMethod -Uri $runtimeUrl -Headers $headers -TimeoutSec 5
        if ($runtime.scope -ne 'local') {
            $oldHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:8177/health' -TimeoutSec 5
            if (Get-ScheduledTask -TaskName $TaskNames[0] -ErrorAction SilentlyContinue) {
                Stop-ScheduledTask -TaskName $TaskNames[0]
            }
            $oldProcess = Get-CimInstance Win32_Process -Filter "ProcessId=$($oldHealth.pid)"
            if ($oldProcess -and $oldProcess.Name -eq 'node.exe' -and $oldProcess.CommandLine -match 'src[/\\]host-bridge\.mjs') {
                Stop-Process -Id $oldProcess.ProcessId -Force
            }
            throw 'Reload the controller in local-only mode.'
        }
    }
    catch {
        # Persist local stop intent even when diagnostics are already off.
        $nodeBinary = (Get-Command node.exe -ErrorAction Stop).Source
        $logDirectory = Join-Path $DiagnosticDirectory 'local'
        New-Item -ItemType Directory -Path $logDirectory -Force | Out-Null
        $TemporaryBridge = Start-Process -FilePath $nodeBinary `
            -ArgumentList '--env-file=.env', 'src/host-bridge.mjs' `
            -WorkingDirectory $DiagnosticDirectory -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $logDirectory 'shutdown-bridge.stdout.log') `
            -RedirectStandardError (Join-Path $logDirectory 'shutdown-bridge.stderr.log')
        $bridgeDeadline = (Get-Date).AddSeconds(40)
        do {
            try { $null = Invoke-RestMethod -Uri $runtimeUrl -Headers $headers -TimeoutSec 3; break }
            catch {
                $TemporaryBridge.Refresh()
                if ($TemporaryBridge.HasExited -or (Get-Date) -ge $bridgeDeadline) {
                    throw 'Unable to start the EBO shutdown controller.'
                }
                Start-Sleep -Seconds 1
            }
        } while ($true)
    }

    $runtime = Invoke-RestMethod -Uri $runtimeUrl -Headers $headers -TimeoutSec 5
    if ($runtime.scope -ne 'local') { throw 'The shutdown controller is not in local-only mode.' }
    $null = Invoke-RestMethod -Uri $runtimeUrl -Headers $headers -Method Post `
        -ContentType 'application/json' -Body '{"mode":"stopped"}' -TimeoutSec 15
    $deadline = (Get-Date).AddMinutes(20)
    $priorStep = ''
    do {
        $state = Invoke-RestMethod -Uri $runtimeUrl -Headers $headers -TimeoutSec 15
        if ($state.step -ne $priorStep) {
            Write-Host 'Checking local shutdown state...'
            $priorStep = $state.step
        }
        if (-not $state.busy -and $state.phase -ne 'switching') {
            if ($state.scope -ne 'local' -or $state.desired -ne 'stopped' -or
                $state.phase -ne 'ready' -or -not $state.actual.local.known -or -not $state.actual.local.stopped -or
                $state.actual.observedAt -lt $state.requestedAt) {
                throw "Local business shutdown could not be verified (error: $($state.error))."
            }
            $ShutdownVerified = $true
            Write-Host 'Local business services are confirmed stopped.' -ForegroundColor Green
            break
        }
        if ((Get-Date) -ge $deadline) { throw 'Local shutdown timed out.' }
        Start-Sleep -Seconds 2
    } while ($true)
} catch { Add-Problem $_.Exception.Message }

# Keep monitoring in maintenance mode on disk, including on the next logon.
try {
    $configPath = Join-Path $DiagnosticDirectory 'config.local.json'
    $config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    $config.maintenance = $true
    $config.observationOnly = $true
    $config.runtimeEnvironment = 'stopped'
    [IO.File]::WriteAllText($configPath, ($config | ConvertTo-Json -Depth 30), (New-Object Text.UTF8Encoding($false)))
} catch { Add-Problem "Could not save maintenance mode: $($_.Exception.Message)" }

foreach ($taskName in $TaskNames) {
    try {
        if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
            Stop-ScheduledTask -TaskName $taskName
        }
    } catch { Add-Problem "Could not stop task ${taskName}: $($_.Exception.Message)" }
}
if ($TemporaryBridge) {
    try { $TemporaryBridge.Refresh(); if (-not $TemporaryBridge.HasExited) { Stop-Process -Id $TemporaryBridge.Id -Force } }
    catch { Add-Problem "Could not stop temporary shutdown controller: $($_.Exception.Message)" }
}

# Catch a manually launched bridge, but only the EBO Node listener on its known port.
try {
    $listeners = @(Get-NetTCPConnection -LocalPort 8177 -State Listen -ErrorAction SilentlyContinue)
    foreach ($listener in $listeners) {
        $process = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)"
        if ($process.Name -eq 'node.exe' -and $process.CommandLine -match 'src[/\\]host-bridge\.mjs') {
            Stop-Process -Id $process.ProcessId -Force
        }
    }
} catch { Add-Problem "Could not stop remaining EBO bridge: $($_.Exception.Message)" }

try {
    $containerIds = @(Get-ProjectContainers)
    if ($containerIds.Count -gt 0) {
        & docker update --restart=no @containerIds
        if ($LASTEXITCODE -ne 0) { throw 'Could not turn off automatic container restarts.' }
        foreach ($id in $containerIds) {
            $paused = & docker inspect --format '{{.State.Paused}}' $id
            if ($LASTEXITCODE -ne 0) { throw 'Could not inspect EBO container.' }
            if ($paused -eq 'true') {
                & docker unpause $id
                if ($LASTEXITCODE -ne 0) { throw 'Could not unpause EBO container for shutdown.' }
            }
        }
        & docker stop --timeout 30 @containerIds
        if ($LASTEXITCODE -ne 0) { throw 'Could not stop all EBO containers.' }
        $states = @(& docker inspect --format '{{.Name}} | {{.State.Status}} | restart={{.HostConfig.RestartPolicy.Name}}' @containerIds)
        if ($LASTEXITCODE -ne 0) { throw 'Could not verify final container states.' }
        $states | ForEach-Object { Write-Host $_ }
        foreach ($id in $containerIds) {
            $running = & docker inspect --format '{{.State.Running}}' $id
            if ($LASTEXITCODE -ne 0 -or $running -ne 'false') { throw 'An EBO container is still running or unverified.' }
        }
    }
} catch { Add-Problem $_.Exception.Message }

try {
    foreach ($taskName in $TaskNames) {
        $task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        if ($task -and ($task.State -eq 'Running' -or $task.Settings.Enabled)) {
            Add-Problem "Background task is still active or enabled: $taskName"
        }
    }
    $listeners = @(Get-NetTCPConnection -LocalPort 8177,8179 -State Listen -ErrorAction SilentlyContinue)
    if ($listeners.Count -gt 0) { Add-Problem 'The EBO host bridge/dashboard still has an active listener.' }
} catch { Add-Problem "Final background verification failed: $($_.Exception.Message)" }

Write-Host ''
if ($Problems.Count -gt 0 -or -not $ShutdownVerified) {
    Write-Host 'SHUTDOWN INCOMPLETE. Local shutdown was attempted; review the errors above and run again.' -ForegroundColor Red
    exit 1
}
Write-Host 'EBO SHUTDOWN COMPLETE. All local business and diagnostic services are stopped.' -ForegroundColor Green
Write-Host 'The one-click startup script will restore EBO scheduled tasks automatically.'
exit 0
