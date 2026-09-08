$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
. (Join-Path $PSScriptRoot '_excel.ps1')
$conn = Connect-XQSheet
$hit = $conn.Hit
$ws = $hit.WS; $rows = $hit.Rows; $cols = $hit.Cols; $m = $hit.Map
$iL = $m["成交值"]; $iC = $m["代碼"]; $iN = $m["商品"]; $iP = $m["成交"]; $iG = $m["漲幅%"]; $iV = $m["總量"]
$blockSize = 300
$total = 0; $valOK = 0; $valEmpty = 0
$rowsWithVal = New-Object System.Collections.Generic.List[object]
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
        if ($null -ne $lv -and ([string]$lv) -match '\d') {
            $valOK++
            $nm = [string]$blkV[$br, $iN]; $cp = [string]$blkV[$br, $iP]; $cg = [string]$blkV[$br, $iG]; $cv = [string]$blkV[$br, $iV]
            $rowsWithVal.Add([pscustomobject]@{ Code=$code; Name=$nm; Val=$lv; Close=$cp; Chg=$cg; Vol=$cv })
        } else { $valEmpty++ }
    }
}
Write-Output ("valid={0}  valOK={1}  valEmpty={2}" -f $total,$valOK,$valEmpty)
Write-Output ("--- top 8 by Val (raw string) ---")
$rowsWithVal | Sort-Object { $v = $_.Val; if ($v -match '([\d\.]+)') { [double]$matches[1] } else { 0 } } -Descending | Select-Object -First 8 | ForEach-Object { Write-Output ("$($_.Code) $($_.Name) val=$($_.Val) close=$($_.Close) chg=$($_.Chg) vol=$($_.Vol)") }
Disconnect-XQSheet
