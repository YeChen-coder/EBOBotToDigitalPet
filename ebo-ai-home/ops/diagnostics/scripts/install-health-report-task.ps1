[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$ReportRoot = Split-Path -Parent $PSScriptRoot
$ReportNode = (Get-Command node.exe -ErrorAction Stop).Source
$ReportTaskName = 'EBO Diagnostics Health Report'
$ReportUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
# The reporter is separate from Docker so it can still record Docker/Watcher outages.
$ReportAction = New-ScheduledTaskAction -Execute $ReportNode -Argument '--env-file=.env scripts/health-report.mjs --watch' -WorkingDirectory $ReportRoot
$ReportTrigger = New-ScheduledTaskTrigger -AtLogOn -User $ReportUser
$ReportPrincipal = New-ScheduledTaskPrincipal -UserId $ReportUser -LogonType Interactive -RunLevel Limited
$ReportSettings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Hidden
if (Get-ScheduledTask -TaskName $ReportTaskName -ErrorAction SilentlyContinue) { Stop-ScheduledTask -TaskName $ReportTaskName }
Register-ScheduledTask -TaskName $ReportTaskName -Action $ReportAction -Trigger $ReportTrigger -Principal $ReportPrincipal -Settings $ReportSettings -Force | Out-Null
Start-ScheduledTask -TaskName $ReportTaskName
Write-Output (Join-Path $ReportRoot 'local/health-report/index.html')
