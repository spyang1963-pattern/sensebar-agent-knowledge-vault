$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
. (Join-Path $PSScriptRoot '_excel.ps1')
$conn = Connect-XQSheet
$hit = $conn.Hit
$ws = $hit.WS; $m = $hit.Map
$iL = $m["成交值"]; $iC = $m["代碼"]
# row 299 之前已知是 err; row 2 是 "--" ; 找一個 was -2146826246 的列
foreach ($row in @(2, 299, 303, 500, 930)) {
    $lv = $ws.Cells.Item($row,$iL).Value2
    $code = $ws.Cells.Item($row,$iC).Value2
    $t = if ($null -eq $lv) { "NULL" } else { $lv.GetType().FullName }
    Write-Output ("row {0} code=[{1}] val=[{2}] type={3}" -f $row, $code, $lv, $t)
}
Disconnect-XQSheet
