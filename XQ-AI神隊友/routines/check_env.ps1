# ============================================================
#  check_env.ps1 ─ 安裝檢查：Excel 報價表有沒有開、欄位齊不齊、分類表讀不讀得到
#  用法：雙擊上一層的「安裝檢查.bat」，或
#        powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File "<路徑>\routines\check_env.ps1"
# ============================================================
$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$root = Split-Path $PSScriptRoot -Parent
$ok = $true

Write-Host ""
Write-Host "===== XQ-AI神隊友 安裝檢查 ====="
Write-Host "資料夾：$root"
Write-Host ("PowerShell：{0}   執行緒模式：{1}" -f $PSVersionTable.PSVersion, [Threading.Thread]::CurrentThread.GetApartmentState())
if ($PSVersionTable.PSVersion.Major -lt 5) { Write-Host "  [NG] 需要 PowerShell 5.1 以上"; $ok = $false } else { Write-Host "  [OK] PowerShell 版本可用" }
if ([Threading.Thread]::CurrentThread.GetApartmentState() -ne 'STA') { Write-Host "  [!]  不是 STA 模式，掛 Excel 可能失敗；請用 -STA 啟動（安裝檢查.bat 已經幫你加了）" }

# ---------- 1. 資料夾 ----------
foreach ($d in 'snapshots', 'outputs') {
    $p = Join-Path $PSScriptRoot $d
    if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p -Force | Out-Null; Write-Host "  [OK] 已建立 routines\$d" }
    else { Write-Host "  [OK] routines\$d 存在" }
}

# ---------- 2. 族群分類表 ----------
try {
    . (Join-Path $PSScriptRoot 'groups.ps1')
    $gc = @($Global:StockGroups.Values | Sort-Object -Unique).Count
    Write-Host ("  [OK] 族群分類表載入成功：{0} 檔、{1} 個族群（routines\groups.ps1）" -f $Global:StockGroups.Count, $gc)
} catch {
    Write-Host "  [NG] 族群分類表載入失敗：$($_.Exception.Message)"
    Write-Host "       常見原因：用記事本改過後存成非 UTF-8（含 BOM），或少了引號／等號"
    $ok = $false
}

# ---------- 3. Excel ----------
$procs = @(Get-Process EXCEL -ErrorAction SilentlyContinue)
if ($procs.Count -eq 0) {
    Write-Host "  [NG] 沒有執行中的 Excel。請先在 XQ 用「輸出欄位 → DDE 伺服器 → 確定」把報價表貼到 Excel（不用存檔）。"
    $ok = $false
} else {
    foreach ($p in $procs) {
        $st = ''; try { $st = $p.StartTime.ToString('MM/dd HH:mm') } catch {}
        Write-Host ("  ・Excel PID {0}  啟動 {1}  視窗「{2}」" -f $p.Id, $st, $p.MainWindowTitle)
    }
    if (-not ($procs | Where-Object { $_.MainWindowTitle })) {
        Write-Host "  [NG] Excel 在跑，但沒有開著的活頁簿（常見於前一天殘留的 Excel）。請重新把 XQ 報價表貼到 Excel。"
        $ok = $false
    } else {
        # ---------- 4. 掛上報價表、檢查欄位 ----------
        try {
            . (Join-Path $PSScriptRoot '_excel.ps1')
            $conn = Connect-XQSheet -Retries 5 -DelayMs 1200
            $m = $conn.Hit.Map
            Write-Host ("  [OK] 找到報價工作表：活頁簿「{0}」，{1} 列 × {2} 欄" -f $conn.Workbook, $conn.Hit.Rows, $conn.Hit.Cols)
            $need = @('代碼', '商品', '成交', '漲幅%', '總量', '委買', '委賣', '均價', '股本', '成交值')
            $missing = @($need | Where-Object { -not $m.ContainsKey($_) })
            $hasIO = $m.ContainsKey('內外盤比圖') -or $m.ContainsKey('內外盤比')
            if ($missing.Count -eq 0) { Write-Host "  [OK] 需要的欄位都在（代碼、商品、成交、漲幅%、總量、委買、委賣、均價、股本、成交值）" }
            else { Write-Host ("  [NG] 報價表缺少欄位：{0}  → 回 XQ「輸出欄位」把它們勾起來再貼一次" -f ($missing -join '、')); $ok = $false }
            if (-not $hasIO) { Write-Host "  [!]  沒有「內外盤比」欄位（非必要，但報告會少一個訊號）" }
            Write-Host ("  ・實際讀到的標題：{0}" -f (($m.Keys | Sort-Object { $m[$_] }) -join ' | '))
            Disconnect-XQSheet
        } catch {
            Write-Host "  [NG] 掛不上報價表：$($_.Exception.Message)"
            $ok = $false
        }
    }
}

Write-Host ""
if ($ok) { Write-Host "===== 全部 OK。打開 Claude Code、切到這個資料夾，跟它說「跑族群資金排行」就可以開始 =====" }
else     { Write-Host "===== 有項目要處理（看上面 [NG] 的說明），處理完再跑一次這個檢查 =====" }
Write-Host ""
exit 0
