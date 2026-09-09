# ============================================================
#  setup_xq_postmarket_task.ps1 ─ 建立盤後綜合分析排程
#
#  建立兩個任務：
#    XQ_Postmarket_Evening  週一至週五 22:00  前一晚初版（含當日法人/融資券/晚報）
#    XQ_Postmarket_Morning  週一至週五 08:35  開盤前更新版（含隔夜美股/早報/當日行事曆）
#
#  共同流程：xq_postmarket_loop.bat <slot>
#    prep（五路資料彙整）→ report（Gemini 明日預測）→ 重建 dashboard（第四頁籤）→ deploy push
#
#  注意：需要系統排程權限，請用「系統管理員」PowerShell 執行本腳本。
# ============================================================
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$batPath = Join-Path $scriptDir 'xq_postmarket_loop.bat'
if (-not (Test-Path $batPath)) { throw "找不到 $batPath" }

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

# ---- 前一晚初版 22:00 ----
$trigEvening = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At 22:00
$actEvening = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$batPath`" evening"
Register-ScheduledTask -TaskName 'XQ_Postmarket_Evening' `
    -Action $actEvening -Trigger $trigEvening -Settings $settings `
    -Description '盤後綜合分析：前一晚 22:00 初版' -Force

# ---- 開盤前更新版 08:35 ----
$trigMorning = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At 08:35
$actMorning = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument "/c `"$batPath`" morning"
Register-ScheduledTask -TaskName 'XQ_Postmarket_Morning' `
    -Action $actMorning -Trigger $trigMorning -Settings $settings `
    -Description '盤後綜合分析：開盤前 08:35 更新版' -Force

# ---- 驗證 ----
foreach ($name in 'XQ_Postmarket_Evening', 'XQ_Postmarket_Morning') {
    $reg = Get-ScheduledTask -TaskName $name
    Write-Output "已建立任務：$($reg.TaskName)  （狀態：$($reg.State)）"
    ($reg.Triggers) | ForEach-Object {
        Write-Output "  每天 $($_.StartBoundary)  星期：$($_.DaysOfWeek -join ', ')"
    }
    Write-Output "  下次執行：$((($reg | Get-ScheduledTaskInfo).NextRunTime))"
}