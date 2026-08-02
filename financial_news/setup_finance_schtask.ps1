# Setup scheduled tasks for the financial news pipeline.
# Run this once per machine:  powershell -ExecutionPolicy Bypass -File setup_finance_schtask.ps1

$py = "C:\Users\hpspy\AppData\Local\Programs\Python\Python312\python.exe"
$pipeline = "D:\AI-Agent-Workspace\financial_news\pipeline.py"

# 1) Every 30 minutes: collect + filter + analyze
$act30 = New-ScheduledTaskAction -Execute $py -Argument "-X utf8 `"$pipeline`" --full --batch 8"
$trg30 = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)
$set30 = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
$prin  = New-ScheduledTaskPrincipal -UserId "hpspy" -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName "FinanceNews_Pipeline" -Action $act30 -Trigger $trg30 -Settings $set30 -Principal $prin -Description "金融新聞收集+分析(每30分鐘)" -Force

# 2) Daily 18:30: full report generation (fresh run)
$actR = New-ScheduledTaskAction -Execute $py -Argument "-X utf8 `"$pipeline`" --report"
$trgR = New-ScheduledTaskTrigger -Daily -At 18:30
Register-ScheduledTask -TaskName "FinanceNews_DailyReport" -Action $actR -Trigger $trgR -Settings $set30 -Principal $prin -Description "每日金融重點報告(18:30)" -Force

Write-Output "scheduled tasks registered OK"
