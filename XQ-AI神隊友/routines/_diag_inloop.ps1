$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
. "D:\AI-Agent-Workspace\XQ-AI神隊友\routines\_excel.ps1"
$conn = Connect-XQSheet
$hit = $conn.Hit
$ws = $hit.WS; $rows = $hit.Rows; $m = $hit.Map; $cols = $hit.Cols
Write-Output ("WB=" + $conn.Workbook + " rows=" + $rows + " cols=" + $cols + " mapOK=" + $m.ContainsKey("代碼"))
$start = 2; $end = [Math]::Min($start + 300 - 1, $rows)
$blkV = $ws.Range($ws.Cells.Item($start, 1), $ws.Cells.Item($end, $cols)).Value2
Write-Output ("blkV type=" + $blkV.GetType().FullName + " dim0=" + $blkV.GetLength(0))
Write-Output ("br1 code=[" + $blkV[1,1] + "] close=[" + $blkV[1,5] + "]")
Write-Output ("br2 code=[" + $blkV[2,1] + "] close=[" + $blkV[2,5] + "]")
Disconnect-XQSheet
