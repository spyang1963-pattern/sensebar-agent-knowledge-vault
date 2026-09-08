$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
. (Join-Path $PSScriptRoot '_excel.ps1')
$conn = Connect-XQSheet
$hit = $conn.Hit
$ws = $hit.WS; $rows = $hit.Rows; $cols = $hit.Cols
$blockSize = 300
$valid = New-Object System.Collections.Generic.List[object]
$blkCount = 0
for ($start = 2; $start -le $rows; $start += $blockSize) {
    $end = [Math]::Min($start + $blockSize - 1, $rows)
    $blkV = $ws.Range($ws.Cells.Item($start, 1), $ws.Cells.Item($end, 1)).Value2
    $blkRows = $end - $start + 1
    $blkCount++
    for ($bi = 0; $bi -lt $blkRows; $bi++) {
        $br = $bi + 1
        $code = [string]$blkV[$br, 1]
        if ($null -eq $blkV[$br,1]) { continue }
        if ($code -match '^\d{4}$') { $valid.Add([pscustomobject]@{ R = ($start + $bi); C = $code }) }
    }
}
Write-Output ("blocks=" + $blkCount + " valid codes=" + $valid.Count + " / totalRows=" + ($rows-1))
Write-Output ("minRow=" + ($valid | Measure-Object R -Minimum).Minimum + " maxRow=" + ($valid | Measure-Object R -Maximum).Maximum)
Disconnect-XQSheet
