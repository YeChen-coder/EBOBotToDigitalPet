param([string]$BuildDir=$PSScriptRoot)
$manifest = Get-Content -LiteralPath (Join-Path $BuildDir 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$taskWord = New-Object -ComObject Word.Application
$taskWord.Visible = $false
$taskWord.DisplayAlerts = 0
try {
    foreach ($file in $manifest.outputs) {
        $taskDoc = $taskWord.Documents.Open($file,$false,$false)
        try {
            $taskDoc.Repaginate()
            $taskDoc.Fields.Update() | Out-Null
            $taskDoc.Repaginate()
            $taskDoc.Fields.Update() | Out-Null
            $taskDoc.Save()
            $pdfPath = Join-Path $BuildDir (([System.IO.Path]::GetFileNameWithoutExtension($file)) + '.pdf')
            $taskDoc.ExportAsFixedFormat($pdfPath,17)
            Write-Output ([System.IO.Path]::GetFileName($file) + ' pages=' + $taskDoc.ComputeStatistics(2))
        } finally { $taskDoc.Close(0) }
    }
} finally { $taskWord.Quit() }
