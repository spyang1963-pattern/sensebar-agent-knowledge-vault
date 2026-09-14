# ============================================================
#  setup_stock_fetch_task.ps1 - register stock-monitor fetch task
#  Runs Mon-Fri 21:30 -> fetch margin/institutional/TDCC/K-line
#  (--fetch-only: write cache only, no dashboard/notify/deploy)
#  Supplies postmarket analysis (22:00) with fresh data.
#  Run with regular (non-admin) PowerShell.
# ============================================================
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python -ErrorAction Stop).Source

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable -DontStopOnIdleEnd -AllowStartIfOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

$trigger = New-ScheduledTaskTrigger -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday -At 21:30

$action = New-ScheduledTaskAction -Execute $py `
    -Argument "-X utf8 `"$scriptDir\run_stock_analysis.py`" --fetch-only --no-notify" `
    -WorkingDirectory $scriptDir

if (Get-ScheduledTask -TaskName 'StockMonitor_Fetch' -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName 'StockMonitor_Fetch' -Confirm:$false -ErrorAction SilentlyContinue
}
Register-ScheduledTask -TaskName 'StockMonitor_Fetch' `
    -Action $action -Trigger $trigger -Settings $settings `
    -Description 'stock-monitor fetch (cache only) for postmarket analysis' -Force

$reg = Get-ScheduledTask -TaskName 'StockMonitor_Fetch'
Write-Output "Task registered: $($reg.TaskName)  (State: $($reg.State))"
Write-Output "  Next run: $((($reg | Get-ScheduledTaskInfo).NextRunTime))"
