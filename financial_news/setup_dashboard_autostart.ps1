# Setup dashboard auto-start at login.
# Run once:  powershell -ExecutionPolicy Bypass -File setup_dashboard_autostart.ps1

$wscript = "wscript.exe"
$bat = "D:\AI-Agent-Workspace\financial_news\start_dashboard.bat"
$action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$bat`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "hpspy"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "FinanceNews_Dashboard" -Action $action -Trigger $trigger -Settings $settings -Description "金融儀表板開機自動啟動" -Force
Write-Output "dashboard autostart OK"
