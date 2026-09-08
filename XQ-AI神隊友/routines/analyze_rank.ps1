# ============================================================
#  analyze_rank.ps1 ─ 作法一：族群資金排行
#  問題：成交值前 N 名各屬什麼族群？哪個族群資金流入最多？
#
#  用法：powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<路徑>\routines\analyze_rank.ps1"
#    不帶參數      → 自動抓 snapshots\ 裡最新的 rank_*.csv
#    -File <csv>   → 指定某一份快照（例如 ..\範例報告\範例快照\rank_20260820_133652.csv）
#    -TopN 50      → 取成交值前幾名（預設 50）
#
#  口徑：剔除 TSE／OTC 兩列指數後取成交值前 TopN 名；族群佔比 ＝ 族群合計 ÷ 前 TopN 合計
#  輸出：給 AI 讀的純文字資料（| 分隔），不是報告。報告由 Claude Code 依 CLAUDE.md 撰寫。
# ============================================================
param([string]$File = '', [int]$TopN = 50)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
. (Join-Path $PSScriptRoot 'groups.ps1')

$dir = Join-Path $PSScriptRoot 'snapshots'
if ($File) { $f = Get-Item $File }
else {
    $f = Get-ChildItem $dir -Filter 'rank_*.csv' -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
    if (-not $f) { throw "snapshots\ 裡沒有 rank_*.csv。請先執行 snapshot.ps1 -Kind rank 抓快照。" }
}
"### file=$($f.Name)"

$d = Import-Csv $f.FullName | Where-Object { $_.Code -ne 'TSE' -and $_.Code -ne 'OTC' }
foreach ($r in $d) {
    $r | Add-Member -NotePropertyName ValN  -NotePropertyValue ([double]$r.Val)  -Force
    $r | Add-Member -NotePropertyName ChgN  -NotePropertyValue ([double]$r.Chg)  -Force
    $r | Add-Member -NotePropertyName DevN  -NotePropertyValue ([double]$r.Dev)  -Force
    $r | Add-Member -NotePropertyName ION   -NotePropertyValue ([double]$r.IO)   -Force
    $r | Add-Member -NotePropertyName TurnN -NotePropertyValue ([double]$r.Turn) -Force
    $g = Get-GroupOf $r.Code; if (-not $g) { $g = '未分類' }
    $r | Add-Member -NotePropertyName Grp -NotePropertyValue $g -Force
}

$top = $d | Sort-Object ValN -Descending | Select-Object -First $TopN
$rk = 1; foreach ($x in $top) { $x | Add-Member -NotePropertyName Rk -NotePropertyValue $rk -Force; $rk++ }
$tot = ($top | Measure-Object ValN -Sum).Sum
"### top${TopN}_total_yi=$([math]::Round($tot,1))"

"=== TOP$TopN ==="
"rk|code|name|grp|close|chg%|val_yi|turn%|dev%|io"
$top | ForEach-Object { "$($_.Rk)|$($_.Code)|$($_.Name)|$($_.Grp)|$($_.Close)|$($_.ChgN)|$($_.ValN)|$($_.TurnN)|$($_.DevN)|$($_.ION)" }

"=== GROUPS ==="
"grp|n|val_yi|pct|avgchg|up|dn|members"
$top | Group-Object Grp | ForEach-Object {
    $s  = ($_.Group | Measure-Object ValN -Sum).Sum
    $a  = ($_.Group | Measure-Object ChgN -Average).Average
    $up = @($_.Group | Where-Object { $_.ChgN -gt 0 }).Count
    $dn = @($_.Group | Where-Object { $_.ChgN -lt 0 }).Count
    $mem = ($_.Group | Sort-Object ValN -Descending | ForEach-Object { "$($_.Name)($($_.ValN)億,$($_.ChgN)%)" }) -join ' '
    [pscustomobject]@{ G = $_.Name; N = $_.Count; S = [math]::Round($s, 1); P = [math]::Round($s / $tot * 100, 1); A = [math]::Round($a, 2); U = $up; D = $dn; M = $mem }
} | Sort-Object S -Descending | ForEach-Object { "$($_.G)|$($_.N)|$($_.S)|$($_.P)|$($_.A)|$($_.U)|$($_.D)|$($_.M)" }

"=== UNCLASSIFIED_TOP$TopN ==="
$top | Where-Object { $_.Grp -eq '未分類' } | ForEach-Object { "$($_.Code) $($_.Name) $($_.ValN)億 $($_.ChgN)%" }

"=== INDEX ==="
Import-Csv $f.FullName | Where-Object { $_.Code -eq 'TSE' -or $_.Code -eq 'OTC' } | ForEach-Object { "$($_.Code)|$($_.Close)|$($_.Chg)|$($_.Val)|$($_.IO)" }

"=== BREADTH_ALL ==="
$au = @($d | Where-Object { [double]$_.Chg -gt 0 }).Count
$ad = @($d | Where-Object { [double]$_.Chg -lt 0 }).Count
"total=$($d.Count) up=$au dn=$ad"
