$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
. (Join-Path $PSScriptRoot '_excel.ps1')
$conn = Connect-XQSheet
$hit = $conn.Hit
$ws = $hit.WS; $rows = $hit.Rows; $cols = $hit.Cols
Write-Output ("rows={0} cols={1}" -f $rows, $cols)
$start = 2; $end = [Math]::Min($start + 300 - 1, $rows)
$rng = $ws.Range($ws.Cells.Item($start, 1), $ws.Cells.Item($end, $cols))
$blkV = $rng.Value2
Write-Output ("blkV type=" + $blkV.GetType().FullName)
if ($blkV -is [object[,]]) { Write-Output ("2D, dim0=" + $blkV.GetLength(0) + " dim1=" + $blkV.GetLength(1)) }
Disconnect-XQSheet
