$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
. "D:\AI-Agent-Workspace\XQ-AI神隊友\routines\_excel.ps1"
$conn = Connect-XQSheet
$hit = $conn.Hit
$ws = $hit.WS
foreach ($row in @(1,2,3,299,300,301,302,303,400,500,1000,1940)) {
    $a = $ws.Cells.Item($row,1).Value2
    $e = $ws.Cells.Item($row,5).Value2
    Write-Output ("row {0}: A=[{1}] E=[{2}]" -f $row, $a, $e)
}
Disconnect-XQSheet
