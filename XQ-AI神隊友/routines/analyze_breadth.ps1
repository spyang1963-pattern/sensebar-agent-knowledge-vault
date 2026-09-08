# ============================================================
#  analyze_breadth.ps1 ─ 作法二：齊漲／齊跌／內部分歧／個別獨走 判定
#  問題：這個族群是整組在動，還是只有一檔在動？
#
#  用法：powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<路徑>\routines\analyze_breadth.ps1"
#    不帶參數    → 自動抓 snapshots\ 裡最新的 breadth_*.csv
#    -File <csv> → 指定某一份快照（例如 ..\範例報告\範例快照\breadth_20260820_134100.csv）
#
#  口徑：剔除 TSE／OTC 後取成交值前 $Universe 名（預設 200）。族群成員常散在中後段，
#        只看前 50 名會誤判整齊度；想用全樣本就把 $Universe 改大（例如 9999）。
#  輸出：給 AI 讀的純文字資料，不是報告。報告由 Claude Code 依 CLAUDE.md 撰寫。
# ============================================================
param([string]$File = '')
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# ---------- 判定門檻（想改就改這裡；改了要在報告裡註明，跨日結果才可比較） ----------
$Universe      = 200    # 分析範圍：成交值前幾名
$MinMembers    = 3      # 族群至少幾檔才判定整齊度（不足 ＝ 樣本不足 THIN）
$AlignRatio    = 0.75   # 齊漲／齊跌：上漲（下跌）檔數 ÷ 樣本數 ≥ 此值，且檔數 ≥ MinMembers
$SplitPct      = 3      # 內部分歧：同時存在 ≥ +SplitPct% 與 ≤ −SplitPct% 的成員
$SoloStrongPct = 5      # 個別表現：僅 1 檔 ≥ +SoloStrongPct%，其餘全落在 ±SoloRestPct% 內
$SoloRestPct   = 2
$LimitPct      = 9.5    # 漲停鎖死：漲幅 ≥ +LimitPct 且委賣 = 0；跌停鎖死：≤ −LimitPct 且委買 = 0
$HotTurn       = 10     # 換手異常：換手率 ≥ HotTurn %
$FakeDev       = -1.5   # 假強勢：漲幅 > 0 但 dev ≤ FakeDev（收在均價下方，開高走低）
$HiddenDev     = 1.5    # 隱藏買盤：漲幅 < 0 但 dev ≥ HiddenDev（收在均價上方，低開走高）
$WeakTop       = 30     # 量大走弱：成交值前 WeakTop 名且漲幅 ≤ WeakPct
$WeakPct       = -2

. (Join-Path $PSScriptRoot 'groups.ps1')

$dir = Join-Path $PSScriptRoot 'snapshots'
if ($File) { $snapFile = Get-Item $File }
else {
    $snapFile = Get-ChildItem $dir -Filter 'breadth_*.csv' -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
    if (-not $snapFile) { throw "snapshots\ 裡沒有 breadth_*.csv。請先執行 snapshot.ps1 -Kind breadth 抓快照。" }
}
$all = @(Import-Csv $snapFile.FullName | Where-Object { $_.Code -ne "TSE" -and $_.Code -ne "OTC" })
foreach ($r in $all) {
    $r.Close = [double]$r.Close; $r.Chg = [double]$r.Chg; $r.Vol = [double]$r.Vol
    $r.Turn = [double]$r.Turn; $r.Dev = [double]$r.Dev; $r.IO = [double]$r.IO
    $r.BidQ = [double]$r.BidQ; $r.AskQ = [double]$r.AskQ; $r.Val = [double]$r.Val
}
$top = $all | Sort-Object Val -Descending | Select-Object -First $Universe
$rank = @{}; for ($i = 0; $i -lt $top.Count; $i++) { $rank[$top[$i].Code] = $i + 1 }

"FILE=$($snapFile.Name)  UNIVERSE=$($top.Count)  CUT$Universe=$($top[-1].Val) ($($top[-1].Code) $($top[-1].Name))"
"BREADTH_TOP$Universe up=$(@($top | Where-Object { $_.Chg -gt 0 }).Count) down=$(@($top | Where-Object { $_.Chg -lt 0 }).Count) flat=$(@($top | Where-Object { $_.Chg -eq 0 }).Count)"
"BREADTH_ALL total=$($all.Count) up=$(@($all | Where-Object { $_.Chg -gt 0 }).Count) down=$(@($all | Where-Object { $_.Chg -lt 0 }).Count)"
""

# ---------- 族群歸類 ----------
$grp = @{}
$unclassified = New-Object System.Collections.Generic.List[object]
foreach ($r in $top) {
    $g = Get-GroupOf $r.Code
    if (-not $g) { $unclassified.Add($r); continue }
    if (-not $grp.ContainsKey($g)) { $grp[$g] = New-Object System.Collections.Generic.List[object] }
    $grp[$g].Add($r)
}

$rows = New-Object System.Collections.Generic.List[object]
foreach ($g in $grp.Keys) {
    $mem  = @($grp[$g] | Sort-Object Chg -Descending)
    $n    = $mem.Count
    $up   = @($mem | Where-Object { $_.Chg -gt 0 }).Count
    $dn   = @($mem | Where-Object { $_.Chg -lt 0 }).Count
    $val  = [math]::Round((($mem | Measure-Object Val -Sum).Sum), 1)
    $lu   = @($mem | Where-Object { $_.Chg -ge $LimitPct -and $_.AskQ -eq 0 }).Count
    $ld   = @($mem | Where-Object { $_.Chg -le (0 - $LimitPct) -and $_.BidQ -eq 0 }).Count
    $hi   = ($mem | Measure-Object Chg -Maximum).Maximum
    $lo   = ($mem | Measure-Object Chg -Minimum).Minimum
    $tags = @()
    if ($n -ge $MinMembers) {
        if ($up / $n -ge $AlignRatio -and $up -ge $MinMembers) { $tags += 'RALLY' }
        if ($dn / $n -ge $AlignRatio -and $dn -ge $MinMembers) { $tags += 'SELLOFF' }
        if ($hi -ge $SplitPct -and $lo -le (0 - $SplitPct))  { $tags += 'SPLIT' }
        $strong = @($mem | Where-Object { $_.Chg -ge $SoloStrongPct })
        $rest   = @($mem | Where-Object { $_.Chg -lt $SoloStrongPct })
        if ($strong.Count -eq 1 -and @($rest | Where-Object { [math]::Abs($_.Chg) -gt $SoloRestPct }).Count -eq 0) { $tags += 'SOLO' }
    } else { $tags += 'THIN' }
    $rows.Add([pscustomobject]@{
        G = $g; N = $n; Up = $up; Dn = $dn; Val = $val; LU = $lu; LD = $ld
        Hi = $hi; Lo = $lo; Tags = ($tags -join ','); Ratio = [math]::Round([double]$up / $n, 3)
        Detail = (($mem | ForEach-Object { "$($_.Name)$(if($_.Chg -ge 0){'+'})$($_.Chg)%" }) -join ' ')
    })
}

"===== 族群總表（依成交值） ====="
$rows | Sort-Object Val -Descending | ForEach-Object {
    "{0,-14} n={1,-3} up={2,-3} dn={3,-3} val={4,-7} LU={5} LD={6} hi={7} lo={8} [{9}]`n    {10}" -f $_.G, $_.N, $_.Up, $_.Dn, $_.Val, $_.LU, $_.LD, $_.Hi, $_.Lo, $_.Tags, $_.Detail
}
""
"===== 齊漲（RALLY，上漲比 ≥ $AlignRatio 且 ≥ $MinMembers 檔；依整齊度→成交值） ====="
$rows | Where-Object { $_.Tags -like '*RALLY*' } | Sort-Object @{e = 'Ratio'; d = $true }, @{e = 'Val'; d = $true } | ForEach-Object {
    "{0,-14} {1}/{2} 上漲 val={3}億 LU={4} | {5}" -f $_.G, $_.Up, $_.N, $_.Val, $_.LU, $_.Detail }
""
"===== 齊跌（SELLOFF，下跌比 ≥ $AlignRatio 且 ≥ $MinMembers 檔） ====="
$rows | Where-Object { $_.Tags -like '*SELLOFF*' } | Sort-Object @{e = 'Ratio'; d = $false }, @{e = 'Val'; d = $true } | ForEach-Object {
    "{0,-14} {1}/{2} 下跌 val={3}億 LD={4} | {5}" -f $_.G, $_.Dn, $_.N, $_.Val, $_.LD, $_.Detail }
""
"===== 內部分歧（SPLIT，同時有 ≥ +$SplitPct% 與 ≤ -$SplitPct% 的成員） ====="
$rows | Where-Object { $_.Tags -like '*SPLIT*' } | Sort-Object Val -Descending | ForEach-Object {
    "{0,-14} n={1} val={2}億 hi={3} lo={4} | {5}" -f $_.G, $_.N, $_.Val, $_.Hi, $_.Lo, $_.Detail }
""
"===== 個別表現（SOLO，僅 1 檔 ≥ +$SoloStrongPct%，其餘在 ±$SoloRestPct% 內） ====="
$rows | Where-Object { $_.Tags -like '*SOLO*' } | Sort-Object Val -Descending | ForEach-Object {
    "{0,-14} n={1} val={2}億 | {3}" -f $_.G, $_.N, $_.Val, $_.Detail }
""
"===== 樣本不足（THIN, n<$MinMembers） ====="
($rows | Where-Object { $_.Tags -like '*THIN*' } | Sort-Object Val -Descending | ForEach-Object { "$($_.G)(n=$($_.N))" }) -join '  '
""
"===== 個股訊號 ====="
"-- 漲停鎖死 (chg>=$LimitPct & askQ=0) --"
$top | Where-Object { $_.Chg -ge $LimitPct -and $_.AskQ -eq 0 } | Sort-Object Val -Descending | ForEach-Object {
    "  $($_.Code) $($_.Name) +$($_.Chg)% turn=$($_.Turn)% val=$($_.Val)億 bid=$($_.BidQ) grp=$(Get-GroupOf $_.Code)" }
"-- 跌停鎖死 (chg<=-$LimitPct & bidQ=0) --"
$top | Where-Object { $_.Chg -le (0 - $LimitPct) -and $_.BidQ -eq 0 } | Sort-Object Val -Descending | ForEach-Object {
    "  $($_.Code) $($_.Name) $($_.Chg)% turn=$($_.Turn)% val=$($_.Val)億 ask=$($_.AskQ) grp=$(Get-GroupOf $_.Code)" }
"-- 換手異常 (turn>=$HotTurn%) --"
$top | Where-Object { $_.Turn -ge $HotTurn } | Sort-Object Turn -Descending | ForEach-Object {
    "  $($_.Code) $($_.Name) turn=$($_.Turn)% chg=$($_.Chg)% val=$($_.Val)億 dev=$($_.Dev)% grp=$(Get-GroupOf $_.Code)" }
"-- 假強勢 (chg>0 & dev<=$FakeDev) --"
$top | Where-Object { $_.Chg -gt 0 -and $_.Dev -le $FakeDev } | Sort-Object Val -Descending | ForEach-Object {
    "  $($_.Code) $($_.Name) +$($_.Chg)% dev=$($_.Dev)% val=$($_.Val)億 io=$($_.IO) grp=$(Get-GroupOf $_.Code)" }
"-- 隱藏買盤 (chg<0 & dev>=$HiddenDev) --"
$top | Where-Object { $_.Chg -lt 0 -and $_.Dev -ge $HiddenDev } | Sort-Object Val -Descending | ForEach-Object {
    "  $($_.Code) $($_.Name) $($_.Chg)% dev=+$($_.Dev)% val=$($_.Val)億 io=$($_.IO) grp=$(Get-GroupOf $_.Code)" }
"-- 量大走弱 (成交值前$WeakTop & chg<=$WeakPct) --"
$top | Select-Object -First $WeakTop | Where-Object { $_.Chg -le $WeakPct } | ForEach-Object {
    "  #$($rank[$_.Code]) $($_.Code) $($_.Name) $($_.Chg)% val=$($_.Val)億 dev=$($_.Dev)% io=$($_.IO) grp=$(Get-GroupOf $_.Code)" }
""
"===== 未分類（前$($Universe)名內, 依成交值）— 請補進 groups.ps1 ====="
($unclassified | ForEach-Object { "$($_.Code)$($_.Name)($($_.Chg)%,$($_.Val)億)" }) -join '  '
