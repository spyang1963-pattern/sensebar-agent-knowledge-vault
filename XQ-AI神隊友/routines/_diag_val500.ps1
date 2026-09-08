$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
. (Join-Path $PSScriptRoot '_excel.ps1')
$conn = Connect-XQSheet
$hit = $conn.Hit
$ws = $hit.WS; $rows = $hit.Rows; $cols = $hit.Cols; $m = $hit.Map
$iL = $m["成交值"]; $iC = $m["代碼"]; $iN = $m["商品"]; $iP = $m["成交"]
$blockSize = 300
$total = 0; $valOK = 0; $valEmpty = 0; $closeOK = 0
$samples = New-Object System.Collections.Generic.List[object]
for ($start = 2; $start -le $rows; $start += $blockSize) {
    $end = [Math]::Min($start + $blockSize - 1, $rows)
    $blkV = $ws.Range($ws.Cells.Item($start, 1), $ws.Cells.Item($end, $cols)).Value2
    $blkRows = $end - $start + 1
    for ($bi = 0; $bi -lt $blkRows; $bi++) {
        $br = $bi + 1
        $code = [string]$blkV[$br, $iC]
        if ($code -notmatch '^\d{4}$') { continue }
        $total++
        $lv = $blkV[$br, $iL]; $cp = $blkV[$br, $iP]
        $lvS = [string]$lv
        if ($null -ne $lv -and $lvS -match '\d') { $valOK++ } else { $valEmpty++ }
        if ($null -ne $cp -and ([string]$cp) -match '\d') { $closeOK++ }
        if ($samples.Count -lt 12) { $samples.Add("$code/$([string]$blkV[$br,$iN])/val=$lvS/chg=$($blkV[$br,$m['漲幅%']])") }
    }
}
Write-Output ("valid={0}  valOK={1}  valEmpty={2}  closeOK={3}" -f $total,$valOK,$valEmpty,$closeOK)
Write-Output "--- samples ---"
$samples | ForEach-Object { Write-Output $_ }
Disconnect-XQSheet
