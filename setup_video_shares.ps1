<#
setup_video_shares.ps1 — 把「影片資料夾」以唯讀 SMB 分享給 notebook（點播用）

為什麼要跑這支
--------------
2026-11-12 起，知識庫每一條影片行都標「（在 哪一台）」並附可點 .lnk。
若該台沒有把影片資料夾分享出來，notebook 只能標機器名、無法一鍵點播
（video_links.py 會把這些列進 working\video_links_report.txt 的 no-share 區）。

在「影片所在的機器」以【系統管理員】開 PowerShell 執行：

    powershell -ExecutionPolicy Bypass -File D:\AI-Agent-Workspace\setup_video_shares.ps1 -DryRun
    powershell -ExecutionPolicy Bypass -File D:\AI-Agent-Workspace\setup_video_shares.ps1

- 只建立「資料夾真的存在」的分享，已存在的同名分享不會動。
- 優先授權給本機 `harvest` 帳號（唯讀）；沒有這個帳號才退回 Everyone（仍唯讀）。
- 分享名稱 = 資料夾名稱（video_links 就是用 `\\<ip>\<資料夾名>\...` 對應）。
- 跑完回 notebook 重跑 `python -X utf8 video_links.py`，原本「沒分享」的條目就會變成可點。

安全性：只給讀取（ReadAccess／RX），不給寫入。不要改成 Change／Full。
#>
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$roots = @(
    "D:\YouTube_Videos",
    "D:\XQ直播_Videos",
    "D:\CMoney_直播",
    "D:\!!!!!理周學院老師"
)

$isAdmin = ([Security.Principal.WindowsPrincipal] `
    [Security.Principal.WindowsIdentity]::GetCurrent()
).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host "✗ 請用【系統管理員】開啟 PowerShell 再執行（New-SmbShare 需要提權）。" -ForegroundColor Red
    exit 1
}

$harvest = $null
try { $harvest = Get-LocalUser -Name "harvest" -ErrorAction SilentlyContinue } catch { }
$access = if ($harvest) { "harvest" } else { "Everyone" }
Write-Host "授權對象：$access（唯讀）" -ForegroundColor Cyan

$done = 0
foreach ($root in $roots) {
    if (-not (Test-Path -LiteralPath $root)) {
        Write-Host "－ 跳過（資料夾不存在）：$root" -ForegroundColor DarkGray
        continue
    }
    $name = Split-Path -Leaf $root
    $existing = Get-SmbShare -Name $name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "－ 已存在分享：$name → $($existing.Path)（不動）" -ForegroundColor Yellow
        continue
    }
    if ($DryRun) {
        Write-Host "[DryRun] 會建立：$name → $root（唯讀：$access）"
        continue
    }
    New-SmbShare -Name $name -Path $root -ReadAccess $access `
        -Description "影片唯讀分享（notebook 點播用）" | Out-Null
    if ($harvest) {
        icacls $root /grant "$($harvest.Name):(OI)(CI)(RX)" /T /C /Q | Out-Null
    }
    Write-Host "✓ 已建立：$name → $root（唯讀：$access）" -ForegroundColor Green
    $done++
}

Write-Host ""
Write-Host "完成：新增 $done 個分享。" -ForegroundColor Cyan
Get-SmbShare | Where-Object { $_.Name -in ($roots | ForEach-Object { Split-Path -Leaf $_ }) } |
    Format-Table Name, Path, Description -AutoSize

Write-Host "下一步：回 notebook 執行  python -X utf8 video_links.py" -ForegroundColor Cyan
