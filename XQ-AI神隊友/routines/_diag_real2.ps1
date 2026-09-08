$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
. "D:\AI-Agent-Workspace\XQ-AI神隊友\routines\_excel.ps1"
$conn = Connect-XQSheet
$hit = $conn.Hit
$ws = $hit.WS; $rows = $hit.Rows; $cols = $hit.Cols; $m = $hit.Map
$iL = $m["成交值"]; $iC = $m["代碼"]; $iN = $m["商品"]; $iP = $m["成交"]; $iG = $m["漲幅%"]
$blockSize = 300
$total = 0; $real = 0; $notDash = 0; $bad = 0
$rowsReal = New-Object System.Collections.Generic.List[object]
for ($start = 2; $start -le $rows; $start += $blockSize) {
    $end = [Math]::Min($start + $blockSize - 1, $rows)
    $blkV = $ws.Range($ws.Cells.Item($start, 1), $ws.Cells.Item($end, $cols)).Value2
    $blkRows = $end - $start + 1
    for ($bi = 0; $bi -lt $blkRows; $bi++) {
        $br = $bi + 1
        $code = [string]$blkV[$br, $iC]
        if ($code -notmatch '^\d{4}$') { continue }
        $total++
        $lv = $blkV[$br, $iL]
        $badRow = $false
        if ($lv -is [int] -or $lv -is [double]) {
            if ([double]$lv -lt 0) { $bad++; $badRow = $true }
        }
        elseif ($null -eq $lv) { $bad++; $badRow = $true }
        elseif ([string]$lv -eq '--') { $notDash++; $badRow = $true }
        if ($badRow) { continue }
        $real++
        $nm = [string]$blkV[$br, $iN]; $cp = [string]$blkV[$br, $iP]; $cg = [string]$blkV[$br, $iG]
        $rowsReal.Add([pscustomobject]@{ Code=$code; Name=$nm; Val=$lv; Close=$cp; Chg=$cg })
    }
}
Write-Output ("total={0}  REAL(with quote)={1}  dash(--)={2}  err<int>={3}" -f $total,$real,$notDash,$bad)
Write-Output ("--- top 12 by Val ---")
$rowsReal | Sort-Object { if ($_.Val -match '([\d\.]+)') { [double]$matches[1] } else { 0 } } -Descending | Select-Object -First 12 | ForEach-Object { Write-Output ("$($_.Code) $($_.Name) val=$($_.Val) close=$($_.Close) chg=$($_.Chg)") }
Disconnect-XQSheet
