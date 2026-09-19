[CmdletBinding()]
param([switch]$OpenAdminKeysPage)

$ErrorActionPreference = 'Stop'
$DiagnosticRoot = Split-Path -Parent $PSScriptRoot
$EnvPath = Join-Path $DiagnosticRoot '.env'
$AdminKeysUrl = 'https://platform.openai.com/settings/organization/admin-keys'

if ($OpenAdminKeysPage) {
  Start-Process -FilePath $AdminKeysUrl
}

Write-Host 'OpenAI Billing 配置'
Write-Host '1. 在官方 Admin keys 页面创建 Organization Admin API Key。'
Write-Host '2. 密钥只会完整显示一次；复制后回到本窗口。'
Write-Host '3. 下方输入不可见，脚本不会打印或记录密钥。'
Write-Host "官方页面: $AdminKeysUrl"

if (-not (Test-Path -LiteralPath $EnvPath)) { throw "Missing diagnostics .env: $EnvPath" }
$SecureKey = Read-Host '请粘贴 sk-admin-... 密钥，然后按 Enter' -AsSecureString
$Bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureKey)
$PlainKey = $null
try {
  $PlainKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($Bstr)
  if ($PlainKey -notmatch '^sk-admin-[A-Za-z0-9_-]{20,}$') {
    throw '这不是有效的 OpenAI Organization Admin API Key；没有修改 .env。'
  }

  $Lines = [Collections.Generic.List[string]]::new()
  $Found = $false
  foreach ($Line in [IO.File]::ReadAllLines($EnvPath)) {
    if ($Line -match '^OPENAI_ADMIN_KEY=') {
      $Lines.Add("OPENAI_ADMIN_KEY=$PlainKey")
      $Found = $true
    } else {
      $Lines.Add($Line)
    }
  }
  if (-not $Found) { $Lines.Add("OPENAI_ADMIN_KEY=$PlainKey") }
  [IO.File]::WriteAllText($EnvPath, ($Lines -join "`r`n") + "`r`n", [Text.UTF8Encoding]::new($false))
} finally {
  if ($Bstr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr) }
  $PlainKey = $null
  $SecureKey = $null
}

& (Join-Path $PSScriptRoot 'restart-host-task.ps1')

$Deadline = (Get-Date).AddSeconds(25)
do {
  Start-Sleep -Seconds 1
  try {
    $Status = Invoke-RestMethod -Uri 'http://127.0.0.1:8179/api/status' -TimeoutSec 3
    $OpenAI = $Status.billing.openai
    if ($OpenAI.status -eq 'ok') {
      Write-Host '完成：OpenAI 账单已成功同步到 Dashboard。' -ForegroundColor Green
      return
    }
    if ($OpenAI.status -in @('error', 'stale')) {
      throw "OpenAI 账单验证失败：$($OpenAI.error)。请确认该 Key 是组织 Admin Key。"
    }
  } catch {
    if ((Get-Date) -ge $Deadline) { throw }
  }
} while ((Get-Date) -lt $Deadline)

throw '已保存 Key，但 Dashboard 在等待时间内没有完成首次同步；请稍后刷新页面。'
