$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
. "D:\AI-Agent-Workspace\XQ-AI神隊友\routines\_excel.ps1"
$conn = Connect-XQSheet
$hit = $conn.Hit
$ws = $hit.WS; $rows = $hit.Rows; $cols = $hit.Cols
$start = 2; $end = [Math]::Min($start + 300 - 1, $rows)
$blkV = $ws.Range($ws.Cells.Item($start, 1), $ws.Cells.Item($end, $cols)).Value2
Write-Output ("type=" + $blkV.GetType().FullName)
try { Write-Output ("direct [1,1]=" + $blkV[1,1]) } catch { Write-Output ("direct err: " + $_.Exception.Message) }
$bi = 0
try { Write-Output ("idx [($bi+1),1]=" + $blkV[$bi + 1, 1]) } catch { Write-Output ("idx err: " + $_.Exception.Message) }
try { $r = $bi + 1; Write-Output ("precomputed [$r,1]=" + $blkV[$r, 1]) } catch { Write-Output ("pre err: " + $_.Exception.Message) }
Disconnect-XQSheet
