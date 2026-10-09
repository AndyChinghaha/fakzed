# List snapshot timestamps for all restored libs files, oldest first.
$ErrorActionPreference = 'Stop'
$historyRoot = 'C:\Users\Cheng_minjing\AppData\Roaming\Qoder\User\History'
$entriesFiles = [System.IO.Directory]::GetFiles($historyRoot, 'entries.json', 'AllDirectories')
$rows = @()
foreach ($ef in $entriesFiles) {
    $meta = Get-Content $ef -Raw -Encoding UTF8 | ConvertFrom-Json
    $res = [string]$meta.resource
    if ($res -notmatch 'new_agent_devframe/libs/fakzed') { continue }
    $p = $res -replace '^file:///', ''
    $p = [System.Uri]::UnescapeDataString($p)
    $p = $p -replace '/', '\'
    $best = 0
    foreach ($e in $meta.entries) { if ([long]$e.timestamp -gt $best) { $best = [long]$e.timestamp } }
    $dt = [DateTimeOffset]::FromUnixTimeMilliseconds($best).LocalDateTime.ToString('MM-dd HH:mm')
    $rows += [PSCustomObject]@{ Time = $dt; Ts = $best; Path = $p }
}
$rows | Sort-Object Ts | ForEach-Object { "{0}  {1}" -f $_.Time, $_.Path }
