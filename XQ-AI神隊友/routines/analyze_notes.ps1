# ============================================================
#  analyze_notes.ps1 ─ 作法三：盤中觀察三段 的事實清單
#  問題：跟上一個時段比，盤面變了什麼？
#
#  用法：powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<路徑>\routines\analyze_notes.ps1"
#    不帶參數        → 自動抓 snapshots\ 裡最新的 notes_*.csv 當「本次」，次新的當「上一份」比較
#    -File <csv>     → 指定本次快照
#    -Prev <csv>     → 指定上一份快照（要跟哪一份比）
#
#  口徑：全樣本（快照裡所有個股，剔除 TSE／OTC 指數列），族群統計也是全樣本。
#  輸出：給 AI 讀的純文字資料（| 分隔），不是報告。三段文字由 Claude Code 依 CLAUDE.md 撰寫。
# ============================================================
param([string]$File = '', [string]$Prev = '')
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# ---------- 判定門檻（想改就改這裡） ----------
$MinMembers   = 3      # 族群至少幾檔才判定齊漲齊跌
$AlignRatio   = 0.75   # 齊漲／齊跌：上漲（下跌）比 ≥ 此值
$LimitPct     = 9.5    # 漲停鎖死：漲幅 ≥ +LimitPct 且委賣 = 0；跌停鎖死：≤ −LimitPct 且委買 = 0
$NearUpPct    = 8.0    # 接近漲停：漲幅 ≥ NearUpPct 但未鎖死
$NearDownPct  = -8.5   # 接近跌停：漲幅 ≤ NearDownPct
$HotTurn      = 10     # 換手率 ≥ HotTurn %
$FakeDev      = -1.5   # 假強勢：漲幅 > 0 但 dev ≤ FakeDev
$WeakPct      = -5     # 重挫：漲幅 ≤ WeakPct
$BigMovePct   = 2.5    # 大幅位移：與上一份相比漲幅變化絕對值 ≥ BigMovePct
$KeyCodes     = @('2330', '2454', '2317', '3037', '2408', '2492', '6173', '3653')   # 每次固定盯的個股

. (Join-Path $PSScriptRoot 'groups.ps1')

$dir = Join-Path $PSScriptRoot 'snapshots'
$files = @(Get-ChildItem $dir -Filter 'notes_*.csv' -ErrorAction SilentlyContinue | Sort-Object Name -Descending)
if ($File) { $csv = (Get-Item $File).FullName } else {
    if ($files.Count -lt 1) { throw "snapshots\ 裡沒有 notes_*.csv。請先執行 snapshot.ps1 -Kind notes 抓快照。" }
    $csv = $files[0].FullName
}
$prevCsv = $null
if ($Prev) { $prevCsv = (Get-Item $Prev).FullName }
elseif (-not $File -and $files.Count -ge 2) { $prevCsv = $files[1].FullName }
"### FILE cur=$(Split-Path $csv -Leaf) prev=$(if($prevCsv){Split-Path $prevCsv -Leaf}else{'none'})"

function Load($p) {
    $d = Import-Csv $p
    $s = @($d | Where-Object { $_.Code -ne 'TSE' -and $_.Code -ne 'OTC' })
    foreach ($x in $s) {
        $x | Add-Member -NotePropertyName G     -NotePropertyValue (Get-GroupOf $x.Code) -Force
        $x | Add-Member -NotePropertyName nChg  -NotePropertyValue ([double]$x.Chg)  -Force
        $x | Add-Member -NotePropertyName nVal  -NotePropertyValue ([double]$x.Val)  -Force
        $x | Add-Member -NotePropertyName nTurn -NotePropertyValue ([double]$x.Turn) -Force
        $x | Add-Member -NotePropertyName nDev  -NotePropertyValue ([double]$x.Dev)  -Force
        $x | Add-Member -NotePropertyName nIO   -NotePropertyValue ([double]$x.IO)   -Force
        $x | Add-Member -NotePropertyName nBid  -NotePropertyValue ([double]$x.BidQ) -Force
        $x | Add-Member -NotePropertyName nAsk  -NotePropertyValue ([double]$x.AskQ) -Force
        $x | Add-Member -NotePropertyName nVol  -NotePropertyValue ([double]$x.Vol)  -Force
    }
    return , $s
}

$d = Import-Csv $csv
$idx = @($d | Where-Object { $_.Code -eq 'TSE' -or $_.Code -eq 'OTC' })
$s = Load $csv
$pv = $null
if ($prevCsv) { $pv = Load $prevCsv }
$pmap = @{}
if ($pv) { foreach ($x in $pv) { $pmap[$x.Code] = $x } }

"### INDEX"
foreach ($i in $idx) { "$($i.Code)|$($i.Name)|close=$($i.Close)|chg=$($i.Chg)|val=$($i.Val)|io=$($i.IO)" }

$allUp = @($s | Where-Object { $_.nChg -gt 0 }).Count
$allDn = @($s | Where-Object { $_.nChg -lt 0 }).Count
$allFl = @($s | Where-Object { $_.nChg -eq 0 }).Count
$totVal = [math]::Round((($s | Measure-Object nVal -Sum).Sum), 1)
"### BREADTH total=$($s.Count) up=$allUp dn=$allDn flat=$allFl totalVal=$totVal"
if ($pv) {
    $pUp = @($pv | Where-Object { $_.nChg -gt 0 }).Count
    $pDn = @($pv | Where-Object { $_.nChg -lt 0 }).Count
    $pTot = [math]::Round((($pv | Measure-Object nVal -Sum).Sum), 1)
    "### BREADTH_PREV up=$pUp dn=$pDn totalVal=$pTot"
}
""
"### GROUPS (val desc)  group|n|val_yi|pct|up|dn|flat|avgChg|medChg|dVal|dAvgChg"
$gs = $s | Where-Object { $_.G } | Group-Object G
$rows = foreach ($g in $gs) {
    $v = [math]::Round((($g.Group | Measure-Object nVal -Sum).Sum), 2)
    $u = @($g.Group | Where-Object { $_.nChg -gt 0 }).Count
    $dn = @($g.Group | Where-Object { $_.nChg -lt 0 }).Count
    $fl = @($g.Group | Where-Object { $_.nChg -eq 0 }).Count
    $av = [math]::Round((($g.Group | Measure-Object nChg -Average).Average), 2)
    $sorted = @($g.Group | Sort-Object nChg)
    $md = [math]::Round($sorted[[int]([math]::Floor($sorted.Count / 2))].nChg, 2)
    $pvv = 0.0; $pav = 0.0
    if ($pv) {
        $pg = @($pv | Where-Object { $_.G -eq $g.Name })
        if ($pg.Count -gt 0) {
            $pvv = [math]::Round((($pg | Measure-Object nVal -Sum).Sum), 2)
            $pav = [math]::Round((($pg | Measure-Object nChg -Average).Average), 2)
        }
    }
    [pscustomobject]@{G = $g.Name; N = $g.Count; V = $v; U = $u; D = $dn; F = $fl; A = $av; M = $md; DV = [math]::Round($v - $pvv, 2); DA = [math]::Round($av - $pav, 2) }
}
$rows | Sort-Object V -Descending | ForEach-Object {
    $p = [math]::Round(($_.V / $totVal) * 100, 2)
    "$($_.G)|$($_.N)|$($_.V)|$($p)|$($_.U)|$($_.D)|$($_.F)|$($_.A)|$($_.M)|$($_.DV)|$($_.DA)"
}
""
"### ALIGNED UP (n>=$MinMembers, up ratio>=$AlignRatio)"
$rows | Where-Object { $_.N -ge $MinMembers -and (($_.U / $_.N) -ge $AlignRatio) } | Sort-Object A -Descending | ForEach-Object { "$($_.G)|n=$($_.N)|up=$($_.U)|dn=$($_.D)|avg=$($_.A)|val=$($_.V)|dVal=$($_.DV)" }
""
"### ALIGNED DOWN (n>=$MinMembers, dn ratio>=$AlignRatio)"
$rows | Where-Object { $_.N -ge $MinMembers -and (($_.D / $_.N) -ge $AlignRatio) } | Sort-Object A | ForEach-Object { "$($_.G)|n=$($_.N)|up=$($_.U)|dn=$($_.D)|avg=$($_.A)|val=$($_.V)|dVal=$($_.DV)" }
""
"### UNGROUPED top15 by val  — 請補進 groups.ps1"
$s | Where-Object { -not $_.G } | Sort-Object nVal -Descending | Select-Object -First 15 | ForEach-Object { "$($_.Code)|$($_.Name)|chg=$($_.Chg)|val=$($_.Val)|turn=$($_.Turn)" }
""
"### LIMIT-UP LOCKED (chg>=$LimitPct & askQ=0)"
$s | Where-Object { $_.nChg -ge $LimitPct -and $_.nAsk -eq 0 } | Sort-Object nVal -Descending | ForEach-Object {
    $was = ''; if ($pmap.ContainsKey($_.Code)) { $p = $pmap[$_.Code]; $was = "prevChg=$($p.Chg) prevAsk=$($p.AskQ) prevVol=$($p.Vol)" } else { $was = 'NEW-IN-LIST' }
    "$($_.Code)|$($_.Name)|$($_.G)|chg=$($_.Chg)|bidQ=$($_.BidQ)|turn=$($_.Turn)|val=$($_.Val)|io=$($_.IO)|$was"
}
""
"### NEAR LIMIT-UP (chg>=$NearUpPct, not locked)"
$s | Where-Object { $_.nChg -ge $NearUpPct -and $_.nAsk -gt 0 } | Sort-Object nChg -Descending | ForEach-Object {
    $was = ''; if ($pmap.ContainsKey($_.Code)) { $p = $pmap[$_.Code]; $was = "prevChg=$($p.Chg)" }
    "$($_.Code)|$($_.Name)|$($_.G)|chg=$($_.Chg)|bidQ=$($_.BidQ)|askQ=$($_.AskQ)|turn=$($_.Turn)|val=$($_.Val)|io=$($_.IO)|$was"
}
""
"### LIMIT-DOWN LOCKED (chg<=-$LimitPct & bidQ=0)"
$s | Where-Object { $_.nChg -le (0 - $LimitPct) -and $_.nBid -eq 0 } | ForEach-Object {
    $was = ''; if ($pmap.ContainsKey($_.Code)) { $p = $pmap[$_.Code]; $was = "prevChg=$($p.Chg)" }
    "$($_.Code)|$($_.Name)|$($_.G)|chg=$($_.Chg)|askQ=$($_.AskQ)|turn=$($_.Turn)|val=$($_.Val)|$was"
}
""
"### NEAR LIMIT-DOWN (chg<=$NearDownPct)"
$s | Where-Object { $_.nChg -le $NearDownPct } | Sort-Object nChg | ForEach-Object {
    $was = ''; if ($pmap.ContainsKey($_.Code)) { $p = $pmap[$_.Code]; $was = "prevChg=$($p.Chg)" }
    "$($_.Code)|$($_.Name)|$($_.G)|chg=$($_.Chg)|bidQ=$($_.BidQ)|askQ=$($_.AskQ)|turn=$($_.Turn)|val=$($_.Val)|io=$($_.IO)|$was"
}
""
"### TURNOVER >=$HotTurn%"
$s | Where-Object { $_.nTurn -ge $HotTurn } | Sort-Object nTurn -Descending | ForEach-Object {
    $was = ''; if ($pmap.ContainsKey($_.Code)) { $p = $pmap[$_.Code]; $was = "prevTurn=$($p.Turn) prevChg=$($p.Chg)" }
    "$($_.Code)|$($_.Name)|$($_.G)|turn=$($_.Turn)|chg=$($_.Chg)|val=$($_.Val)|dev=$($_.Dev)|io=$($_.IO)|$was"
}
""
"### FAKE STRONG (chg>0 & dev<=$FakeDev)"
$s | Where-Object { $_.nChg -gt 0 -and $_.nDev -le $FakeDev } | Sort-Object nVal -Descending | Select-Object -First 20 | ForEach-Object { "$($_.Code)|$($_.Name)|$($_.G)|chg=$($_.Chg)|dev=$($_.Dev)|turn=$($_.Turn)|val=$($_.Val)|io=$($_.IO)" }
""
"### WEAK <=$WeakPct (top by val)"
$s | Where-Object { $_.nChg -le $WeakPct } | Sort-Object nVal -Descending | Select-Object -First 25 | ForEach-Object {
    $was = ''; if ($pmap.ContainsKey($_.Code)) { $p = $pmap[$_.Code]; $was = "prevChg=$($p.Chg)" }
    "$($_.Code)|$($_.Name)|$($_.G)|chg=$($_.Chg)|val=$($_.Val)|turn=$($_.Turn)|dev=$($_.Dev)|io=$($_.IO)|$was"
}
""
"### FLIPPED TO RED (prevChg>0 now chg<0, top15 by val)"
$s | Where-Object { $_.nChg -lt 0 -and $pmap.ContainsKey($_.Code) -and ([double]$pmap[$_.Code].Chg) -gt 0 } | Sort-Object nVal -Descending | Select-Object -First 15 | ForEach-Object {
    "$($_.Code)|$($_.Name)|$($_.G)|prevChg=$($pmap[$_.Code].Chg)|nowChg=$($_.Chg)|val=$($_.Val)|dev=$($_.Dev)"
}
""
"### FLIPPED TO GREEN (prevChg<0 now chg>0, top15 by val)"
$s | Where-Object { $_.nChg -gt 0 -and $pmap.ContainsKey($_.Code) -and ([double]$pmap[$_.Code].Chg) -lt 0 } | Sort-Object nVal -Descending | Select-Object -First 15 | ForEach-Object {
    "$($_.Code)|$($_.Name)|$($_.G)|prevChg=$($pmap[$_.Code].Chg)|nowChg=$($_.Chg)|val=$($_.Val)|dev=$($_.Dev)"
}
""
"### BIG MOVERS vs PREV (abs chg delta >=$BigMovePct, top20 by val)"
$s | Where-Object { $pmap.ContainsKey($_.Code) -and ([math]::Abs($_.nChg - [double]$pmap[$_.Code].Chg) -ge $BigMovePct) } | Sort-Object nVal -Descending | Select-Object -First 20 | ForEach-Object {
    $dd = [math]::Round($_.nChg - [double]$pmap[$_.Code].Chg, 2)
    "$($_.Code)|$($_.Name)|$($_.G)|prevChg=$($pmap[$_.Code].Chg)|nowChg=$($_.Chg)|d=$dd|val=$($_.Val)|turn=$($_.Turn)"
}
""
"### KEY SINGLES"
foreach ($c in $KeyCodes) {
    $x = $s | Where-Object { $_.Code -eq $c }
    if ($x) {
        $was = ''; if ($pmap.ContainsKey($c)) { $was = "prevChg=$($pmap[$c].Chg) prevVol=$($pmap[$c].Vol)" }
        "$($x.Code)|$($x.Name)|chg=$($x.Chg)|close=$($x.Close)|turn=$($x.Turn)|val=$($x.Val)|dev=$($x.Dev)|io=$($x.IO)|vol=$($x.Vol)|$was"
    }
}
