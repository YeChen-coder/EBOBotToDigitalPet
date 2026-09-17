[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$DiagnosticRoot = Split-Path -Parent $PSScriptRoot
$NodeBinary = (Get-Command node.exe -ErrorAction Stop).Source
# Schedule Node directly: stopping the task must stop the listener, not only a wrapper shell.
$TaskAction = New-ScheduledTaskAction -Execute $NodeBinary -Argument '--env-file=.env src/host-bridge.mjs' -WorkingDirectory $DiagnosticRoot
$TaskTrigger = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$TaskPrincipal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$TaskSettings = New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'EBO Diagnostics Host Bridge' -Action $TaskAction -Trigger $TaskTrigger -Principal $TaskPrincipal -Settings $TaskSettings -Force | Out-Null
Start-ScheduledTask -TaskName 'EBO Diagnostics Host Bridge'
