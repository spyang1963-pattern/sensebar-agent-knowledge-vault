# ============================================================
#  setup_xq_snapshot_task.ps1 ─ 建立「每 15 分抓三種快照」的 Windows 工作排程
#
#  建立 XQ_Snapshot_Loop 任務：
#    週一至週五 09:15 起，每 15 分鐘重複一次，直到 13:30。
#    執行 xq_snapshot_loop.bat（依序抓 rank/breadth/notes）。
#
#  注意：snapshot.ps1 內建「盤中時段守門（09:15–13:30）＋ stale 去重」，
#        所以排程多跑幾次無妨，時段外自動 SKIP、資料沒變不重存。
# ============================================================
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$batPath = Join-Path $scriptDir 'xq_snapshot_loop.bat'
if (-not (Test-Path $batPath)) { throw "找不到 $batPath" }

# ---- 觸發：週一~週五 每天 09:15，每 15 分重複至 13:30（收盤定格後；09:15+15×17） ----
$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At 09:15
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At 09:15 `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Minutes 255)).Repetition
$trigger.Repetition.StopAtDurationEnd = $true

# ---- 動作 ----
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$batPath`""

# ---- 設定：錯過補跑、允許開機後執行、不因睡眠停止 ----
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

# ---- 註冊（用最高權限以外的正常權限即可，不需要密碼）----
Register-ScheduledTask -TaskName 'XQ_Snapshot_Loop' `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description '盤中每 15 分抓 XQ 三種快照（rank/breadth/notes）到 routines\snapshots\' `
    -Force

# ---- 驗證 ----
$reg = Get-ScheduledTask -TaskName 'XQ_Snapshot_Loop'
Write-Output "已建立任務：$($reg.TaskName)"
Write-Output "狀態：$($reg.State)"
$info = $reg | Get-ScheduledTaskInfo
Write-Output "下次執行：$($info.NextRunTime)"
Write-Output "觸發器："
($reg.Triggers) | ForEach-Object {
    Write-Output "  每天 $($_.StartBoundary)"
    if ($_.Repetition) {
        Write-Output "    重複：每 $($_.Repetition.Interval) 分鐘，時長 $($_.Repetition.Duration)，到期停止=$($_.Repetition.StopAtDurationEnd)"
    }
    if ($_.DaysOfWeek) {
        Write-Output "    星期：$($_.DaysOfWeek -join ', ')"
    }
}
