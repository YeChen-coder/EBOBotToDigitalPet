$ErrorActionPreference = 'Stop'
$TaskName = 'EBO Diagnostics Host Bridge'
$PreviousPid = $null
try { $PreviousPid = (Invoke-RestMethod -Uri http://127.0.0.1:8177/health -TimeoutSec 1).pid } catch {}
Stop-ScheduledTask -TaskName $TaskName
$StopDeadline = (Get-Date).AddSeconds(15)
while ((Get-ScheduledTask -TaskName $TaskName).State -eq 'Running') {
    if ((Get-Date) -gt $StopDeadline) { throw 'Host task did not stop' }
    Start-Sleep -Milliseconds 200
}
Start-Sleep -Seconds 1
Start-ScheduledTask -TaskName $TaskName
$StartDeadline = (Get-Date).AddSeconds(20)
while ((Get-Date) -lt $StartDeadline) {
    try {
        $Health = Invoke-RestMethod -Uri http://127.0.0.1:8177/health -TimeoutSec 1
        if ($Health.ok -and $Health.pid -and $Health.pid -ne $PreviousPid) { return }
    } catch {}
    # Task Scheduler may report Ready before the old listener has released its port.
    # Retry a failed start within this bounded window, rather than silently leaving no listener.
    if ((Get-ScheduledTask -TaskName $TaskName).State -eq 'Ready') { Start-ScheduledTask -TaskName $TaskName }
    Start-Sleep -Seconds 1
}
throw 'Host task did not restart with a new healthy process'
