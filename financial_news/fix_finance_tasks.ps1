# Fix scheduled tasks to run even when user is NOT logged in.
# Run as Administrator:  powershell -ExecutionPolicy Bypass -File fix_finance_tasks.ps1
# You will be prompted for your Windows password (hpspy) once.

$py = "C:\Users\hpspy\AppData\Local\Programs\Python\Python312\python.exe"
$pipeline = "D:\AI-Agent-Workspace\financial_news\pipeline.py"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Minutes 15)

# Build principal that can run without login (Password = stored credential)
$cred = Get-Credential -UserName "hpspy" -Message "Enter your Windows login password for auto-run tasks"
$prin = New-ScheduledTaskPrincipal -UserId "hpspy" -LogonType Password -RunLevel Highest

# 1) Pipeline: every 30 minutes
$act30 = New-ScheduledTaskAction -Execute $py -Argument "-X utf8 `"$pipeline`" --full --batch 8"
$trg30 = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)
$set30 = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName "FinanceNews_Pipeline" -Action $act30 -Trigger $trg30 -Settings $set30 -Principal $prin -Description "金融新聞收集+分析(每30分鐘)" -Force

# 2) Morning report: 07:00 daily
$actM = New-ScheduledTaskAction -Execute $py -Argument "-X utf8 morning_report.py"
$trgM = New-ScheduledTaskTrigger -Daily -At 07:00
Register-ScheduledTask -TaskName "FinanceNews_MorningReport" -Action $actM -Trigger $trgM -Settings $settings -Principal $prin -Description "早上7:00每日報告" -Force

# 3) Evening report: 19:00 daily  
$actE = New-ScheduledTaskAction -Execute $py -Argument "-X utf8 evening_report.py"
$trgE = New-ScheduledTaskTrigger -Daily -At 19:00
Register-ScheduledTask -TaskName "FinanceNews_EveningReport" -Action $actE -Trigger $trgE -Settings $settings -Principal $prin -Description "晚上7:00深度分析報告" -Force

# 4) Dashboard: on logon
$actD = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"D:\AI-Agent-Workspace\financial_news\start_dashboard.bat`""
$trgD = New-ScheduledTaskTrigger -AtLogOn -User "hpspy"
$prinD = New-ScheduledTaskPrincipal -UserId "hpspy" -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName "FinanceNews_Dashboard" -Action $actD -Trigger $trgD -Settings $settings -Principal $prinD -Description "金融儀表板開機自動啟動" -Force

Write-Output "OK - all tasks now use Password logon (pipeline/morning/evening will run regardless of login state)"
