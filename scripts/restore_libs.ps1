# Restore libs/ from Qoder Local History (VSCode-style User\History snapshots).
$ErrorActionPreference = 'Stop'
$historyRoot = 'C:\Users\Cheng_minjing\AppData\Roaming\Qoder\User\History'
$workspace = 'd:\E\nlp_民工乐园\project_test\new_agent_devframe'

$entriesFiles = [System.IO.Directory]::GetFiles($historyRoot, 'entries.json', 'AllDirectories')
$restored = 0
$skipped = 0
$report = @()

foreach ($ef in $entriesFiles) {
    try {
        $meta = Get-Content $ef -Raw -Encoding UTF8 | ConvertFrom-Json
    } catch { $skipped++; continue }

    $res = [string]$meta.resource
    if ($res -notmatch 'new_agent_devframe/libs/fakzed') { continue }

    # URI-decode and normalize to Windows path.
    $p = $res -replace '^file:///', ''
    $p = [System.Uri]::UnescapeDataString($p)
    $p = $p -replace '/', '\'
    if ($p -notmatch '^[a-zA-Z]:') { $skipped++; continue }
    $target = $p

    # Pick the newest snapshot.
    $best = $null
    foreach ($e in $meta.entries) {
        if ($null -eq $best -or [long]$e.timestamp -gt [long]$best.timestamp) { $best = $e }
    }
    if ($null -eq $best) { $skipped++; continue }

    $snapshot = Join-Path (Split-Path $ef) ([string]$best.id)
    if (-not (Test-Path $snapshot)) { $skipped++; continue }

    $destDir = Split-Path $target
    if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
    Copy-Item $snapshot $target -Force
    $report += "RESTORED: $target"
    $restored++
}

"恢复文件数: $restored / 跳过: $skipped"
$report | Sort-Object | ForEach-Object { $_ }
