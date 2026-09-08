# ============================================================
#  snapshot.ps1 ─ 從正在執行的 Excel（XQ 用 DDE 貼過來的報價表）抓一份即時快照，存成 CSV
#
#  用法（一定要用 -STA 啟動 PowerShell，COM 才掛得上）：
#    powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File "<路徑>\routines\snapshot.ps1" -Kind rank
#
#    -Kind   rank    → 作法一 族群資金排行 用（畫面印出成交值前 60 名）
#            breadth → 作法二 齊漲分歧診斷 用（印出前 200 名）
#            notes   → 作法三 盤中觀察三段 用（印出前 160 名）
#    -Force  盤中時段以外也硬跑（測試用；正常只在 09:25–13:55 執行，其餘時間印 SKIP=1 就結束）
#    -Top N  覆寫畫面印出的筆數（CSV 不受影響）
#    -KeepN N 只保留「成交值前 N 筆」存檔（預設 500；0 = 全部存）
#
#  快照一律存到本資料夾的 snapshots\{kind}_yyyyMMdd_HHmmss.csv
#  欄位：Code Name Close Chg Vol Turn Dev IO BidQ AskQ Cap Val
#        Turn = 當日換手率 % ＝ 總量 ÷ (股本億 × 100)
#        Dev  = 成交價相對均價乖離 % ＝ (成交 − 均價) ÷ 均價 × 100
#        Val  = 成交值（億元）
#
#  輸出第一行是給 AI 看的旗標：
#    SKIP=1  → 非盤中時段，沒抓
#    stale=1 → 和上一份同類快照完全一樣（休市／報價中斷／Excel 停住），沒存檔
#    stale=0 → 新資料，已存檔
# ============================================================
param(
    [ValidateSet('rank', 'breadth', 'notes')] [string] $Kind = 'rank',
    [switch] $Force,
    [int] $Top = 0,
    [int] $KeepN = 500
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$defaultTop = @{ rank = 60; breadth = 200; notes = 160 }
if ($Top -le 0) { $Top = $defaultTop[$Kind] }

# ---------- 盤中時段守門（09:25–13:55；改時段就改這兩個分鐘數） ----------
$now  = Get-Date
$mins = $now.Hour * 60 + $now.Minute
if (-not $Force -and ($mins -lt 565 -or $mins -gt 835)) {
    "### SKIP=1  現在 $($now.ToString('HH:mm')) 不在 09:25-13:55 盤中時段，本次不執行（要測試請加 -Force）"
    exit 0
}

. (Join-Path $PSScriptRoot '_excel.ps1')

$proc = Get-Process -Name EXCEL -ErrorAction SilentlyContinue
if (-not $proc) { throw "找不到執行中的 Excel。請先在 XQ 用「輸出欄位 → DDE」把報價表貼到 Excel（不用存檔）再執行。" }

# ---------- 掛上報價表 ----------
$conn   = Connect-XQSheet
$hit    = $conn.Hit
$wbName = $conn.Workbook
$ws = $hit.WS; $rows = $hit.Rows; $m = $hit.Map; $cols = $hit.Cols

function ColIndex($n) { if ($m.ContainsKey($n)) { return $m[$n] } else { return 0 } }
function AsNum($x) { if ($null -eq $x) { return 0.0 }; $d = [string]$x -as [double]; if ($null -eq $d) { return 0.0 } else { return $d } }

$iC = ColIndex '代碼'; $iN = ColIndex '商品'; $iP = ColIndex '成交'; $iG = ColIndex '漲幅%'; $iV = ColIndex '總量'
$iB = ColIndex '委買'; $iA = ColIndex '委賣'; $iO = ColIndex '內外盤比圖'; $iM = ColIndex '均價'; $iK = ColIndex '股本'; $iL = ColIndex '成交值'
if ($iO -eq 0) { $iO = ColIndex '內外盤比' }

# ---------- 分塊讀取報價表（避免一次抓超大 Range 讓 DDE 推播中的 Excel 撞 COM 錯誤） ----------
$out = New-Object System.Collections.Generic.List[object]
$blockSize = 300
for ($start = 2; $start -le $rows; $start += $blockSize) {
    $end = [Math]::Min($start + $blockSize - 1, $rows)
    $blkV = $ws.Range($ws.Cells.Item($start, 1), $ws.Cells.Item($end, $cols)).Value2
    $blkRows = $end - $start + 1
    for ($bi = 0; $bi -lt $blkRows; $bi++) {
        $br = $bi + 1   # block array row index（1-based；先存成變數再索引，PowerShell 對「索引內含運算式+逗號」會出錯）
        $r = $start + $bi
        $code = [string]$blkV[$br, 1]
        if ([string]::IsNullOrWhiteSpace($code)) { continue }
        $cur = [double[]]::new($cols + 1)
        for ($c = 1; $c -le $cols; $c++) { $cur[$c] = AsNum $blkV[$br, $c] }
        $p = $cur[$iP]; $vol = $cur[$iV]; $cap = $cur[$iK]; $avg = $cur[$iM]
        $turn = 0.0; if ($cap -gt 0) { $turn = [math]::Round($vol / ($cap * 100), 2) }
        $dev = 0.0;  if ($avg -gt 0 -and $p -gt 0) { $dev = [math]::Round((($p - $avg) / $avg) * 100, 2) }
        $val = 0.0
        if ($iL -gt 0) {
            $raw = [string]$blkV[$br, $iL]
            if ($raw -match '([\d\.]+)') {
                $val = [double]$matches[1]
                if ($raw -match '億') { $val = [math]::Round($val, 2) }
                elseif ($raw -match '萬') { $val = [math]::Round($val / 10000, 4) }
            }
        }
        $out.Add([pscustomobject]@{
            Code = $code.Trim(); Name = ([string]$blkV[$br, $iN]).Trim(); Close = $p; Chg = $cur[$iG]
            Vol = $vol; Turn = $turn; Dev = $dev; IO = $cur[$iO]; BidQ = $cur[$iB]; AskQ = $cur[$iA]
            Cap = $cap; Val = $val
        })
    }
    Start-Sleep -Milliseconds 200
}

# ---------- 存檔（同類上一份完全相同就不存，標 stale=1） ----------
# 依成交值排序保留前 KeepN（預設 500），讓大報價表只留下有成交量的股票
$outSorted = @($out | Sort-Object Val -Descending)
if ($KeepN -gt 0 -and $outSorted.Count -gt $KeepN) {
    $outSorted = @($outSorted | Select-Object -First $KeepN)
}
$dir = Join-Path $PSScriptRoot 'snapshots'
if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
$stamp = $Kind + '_' + $now.ToString('yyyyMMdd_HHmmss')
$sig = ($outSorted | ForEach-Object { "$($_.Code):$($_.Vol):$($_.Close)" }) -join ','
$stale = 0
$prev = Get-ChildItem $dir -Filter ($Kind + '_*.csv') -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
if ($prev) {
    $pd = Import-Csv $prev.FullName
    $psig = ($pd | ForEach-Object { "$($_.Code):$($_.Vol):$($_.Close)" }) -join ','
    if ($sig -eq $psig) { $stale = 1 }
}
$saved = ''
if ($stale -eq 0) {
    $saved = Join-Path $dir "$stamp.csv"
    $outSorted | Export-Csv -Path $saved -NoTypeInformation -Encoding UTF8
}

Disconnect-XQSheet

"### snapshot=$stamp  kind=$Kind  total=$($out.Count)  kept=$($outSorted.Count)  keepN=$KeepN  stale=$stale  prev=$(if($prev){$prev.Name}else{'none'})  wb=$wbName  saved=$(if($saved){$saved}else{'(none, stale)'})"
"code|name|close|chg%|vol|turn%|dev%|io|bidQ|askQ|val_yi"
$outSorted | Select-Object -First $Top | ForEach-Object {
    "$($_.Code)|$($_.Name)|$($_.Close)|$($_.Chg)|$($_.Vol)|$($_.Turn)|$($_.Dev)|$($_.IO)|$($_.BidQ)|$($_.AskQ)|$($_.Val)"
}
exit 0
