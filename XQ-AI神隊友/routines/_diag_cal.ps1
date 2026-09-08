$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
. (Join-Path $PSScriptRoot '_excel.ps1')
$conn = Connect-XQSheet
$hit = $conn.Hit
$ws = $hit.WS; $cols = $hit.Cols; $m = $hit.Map
$iL = $m["成交值"]; $iC = $m["代碼"]; $iN = $m["商品"]
foreach ($row in @(2,3,4,5,6)) {
    $code = $ws.Cells.Item($row,$iC).Value2
    $nm = $ws.Cells.Item($row,$iN).Value2
    $lv = $ws.Cells.Item($row,$iL).Value2
    $t = if ($null -eq $lv) { "NULL" } else { $lv.GetType().FullName }
    Write-Output ("row {0} {1} {2}  val=[{3}] type={4}" -f $row, $code, $nm, $lv, $t)
}
Disconnect-XQSheet
