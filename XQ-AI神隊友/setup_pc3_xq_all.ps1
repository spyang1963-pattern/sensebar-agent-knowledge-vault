# ============================================================
#  setup_pc3_xq_all.ps1 ─ PC3 一次性把 XQ 三件事全部設好
#
#  需用「系統管理員」PowerShell 執行：
#    1. 同步最新程式碼（git pull 大倉）
#    2. 重註冊 snapshot 任務（時段 09:15–13:30、每 15 分）
#    3. 註冊盤後綜合分析任務（22:00 初版 + 08:35 更新版）
#    4. 啟用被停用的 XQ_Snapshot_Loop
#
#  用法（在 PC3 上、管理員 PowerShell）：
#    cd /d "D:\sensebar-agent-knowledge-vault"
#    powershell -ExecutionPolicy Bypass -File "XQ-AI神隊友\setup_pc3_xq_all.ps1"
#
#  備註：snapshot 守門（snapshot.ps1:40）= 09:15–13:30；
#        PC3 需開 XQ + Excel（含權限表）才能抓到快照，否則會 SKIP/stale。
# ============================================================
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $scriptDir
Set-Location $root
Write-Output "== 工作目錄：$root =="

# ---- 1. 同步最新程式碼（若為 git 倉庫）----
if (Test-Path (Join-Path $root '.git')) {
    Write-Output "== [1/4] git pull 大倉最新 =="
    git pull origin master
    if ($LASTEXITCODE -ne 0) { Write-Output '!! git pull 失敗，先手動解決再繼續（或省略此步）'; }
} else {
    Write-Output "== [1/4] 非 git 倉庫，跳過 pull =="
}

# ---- 2. 重註冊 snapshot 任務 ----
Write-Output "== [2/4] 重註冊 XQ_Snapshot_Loop（09:15–13:30 每 15 分）=="
& (Join-Path $scriptDir 'setup_xq_snapshot_task.ps1')

# ---- 3. 註冊盤後綜合分析任務 ----
Write-Output "== [3/4] 註冊 XQ_Postmarket_Evening / Morning =="
& (Join-Path $scriptDir 'setup_xq_postmarket_task.ps1')

# ---- 4. 啟用被停用的快照任務 ----
Write-Output "== [4/4] 確保 XQ_Snapshot_Loop 為啟用 =="
$t = Get-ScheduledTask -TaskName 'XQ_Snapshot_Loop' -ErrorAction SilentlyContinue
if ($t) {
    Enable-ScheduledTask -TaskName 'XQ_Snapshot_Loop' | Out-Null
    Write-Output "XQ_Snapshot_Loop -> $($t.State)"
}
$post = Get-ScheduledTask -TaskName 'XQ_Postmarket_Evening','XQ_Postmarket_Morning' -ErrorAction SilentlyContinue
foreach ($pt in $post) { Write-Output "$($pt.TaskName) -> $($pt.State)" }

Write-Output ""
Write-Output "== 完成。建議下次開盤前確認： =="
Write-Output "  1. XQ + Excel（含權限表）已開，用一般權限 PS 待命"
Write-Output "  2. Get-ScheduledTask XQ_Snapshot_Loop,XQ_Postmarket_Evening,XQ_Postmarket_Morning 全為 Ready"