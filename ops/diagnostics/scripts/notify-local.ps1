$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$notice = New-Object System.Windows.Forms.NotifyIcon
try {
    $notice.Icon = [System.Drawing.SystemIcons]::Warning
    $notice.Visible = $true
    $notice.BalloonTipTitle = 'EBO Diagnostics'
    $notice.BalloonTipText = $env:EBO_DIAGNOSTIC_MESSAGE
    $notice.ShowBalloonTip(5000)
    [System.Media.SystemSounds]::Exclamation.Play()
    Start-Sleep -Seconds 6
} finally { $notice.Dispose() }
