# missionctl.ps1 - Autonomy Layer: register/manage Windows scheduled tasks
# from mission manifest JSON files.
#
# Usage (run on the TARGET machine, must be its own local python/shell):
#   .\missionctl.ps1 -Action guard                         # install Autonomy_Guard (every 30min)
#   .\missionctl.ps1 -Action install -Mission missions\finance-pipeline.json
#   .\missionctl.ps1 -Action list
#   .\missionctl.ps1 -Action run    -Mission finance-pipeline   # run now (test)
#   .\missionctl.ps1 -Action remove -Mission finance-pipeline
#   .\missionctl.ps1 -Action selfheal                       # run watchdog once (console, test)
#
# For "run whether user is logged on or not", it uses the same Password
# principal pattern as financial_news\fix_finance_tasks.ps1 (prompts once for
# the Windows password). If you cancel the prompt, tasks register as
# Interactive (still fine while the user stays logged in).

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("guard", "install", "remove", "list", "run", "selfheal")]
    [string]$Action,
    [string]$Mission,
    [string]$WorkdirOverride = ""
)

$self = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = ""
if ($WorkdirOverride) {
    # Allow installing against a copied autonomy folder on another machine.
    $self = $WorkdirOverride
}
$cmd = Get-Command python -ErrorAction SilentlyContinue
if ($cmd) { $py = $cmd.Source } else { Write-Error "找不到 python，請先確認已安裝並在 PATH"; exit 1 }

function New-Principal {
    param([string]$User = $env:USERNAME)
    $tryPassword = $false
    try {
        $cred = Get-Credential -UserName $User -Message "輸入 Windows 登入密碼（讓任務在未登入時也能執行）"
        $tryPassword = $true
    } catch { $tryPassword = $false }
    if ($tryPassword) {
        return ,(New-ScheduledTaskPrincipal -UserId $User -LogonType Password -RunLevel Highest)
    }
    return ,(New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Highest)
}

function New-TriggerFromJson {
    param($Sched)
    if ($Sched.kind -eq "daily") {
        $h, $m = ($Sched.start -split ":")
        return New-ScheduledTaskTrigger -Daily -At (New-TimeSpan -Hours ([int]$h) -Minutes ([int]$m))
    }
    # interval
    $mins = [int]$Sched.minutes
    $sh, $sm = "0", "0"
    if ($Sched.start -and ($Sched.start -match ":")) { $sh, $sm = ($Sched.start -split ":") }
    $at = Get-Date -Hour ([int]$sh) -Minute ([int]$sm) -Second 0
    if ($at -lt (Get-Date)) { $at = $at.AddDays(1) }
    return New-ScheduledTaskTrigger -Once -At $at -RepetitionInterval (New-TimeSpan -Minutes $mins) -RepetitionDuration (New-TimeSpan -Days 3650)
}

switch ($Action) {

    "guard" {
        $tname = "Autonomy_Guard"
        $act = New-ScheduledTaskAction -Execute $py -Argument "-X utf8 `"$self\self_heal.py`"" -WorkingDirectory $self
        $trg = New-ScheduledTaskTrigger -Once -At (Get-Date -Hour 0 -Minute 0 -Second 0) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)
        $set = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
        $prin = New-Principal
        Register-ScheduledTask -TaskName $tname -Action $act -Trigger $trg -Settings $set -Principal $prin -Description "Autonomy 看門狗（自動 pull/自癒/通知）" -Force | Out-Null
        Write-Output "OK: $tname installed"
    }

    "install" {
        if (-not $Mission) { Write-Error "-Mission 需要 mission.json 路徑"; exit 1 }
        $m = Get-Content -Raw -Encoding UTF8 $Mission | ConvertFrom-Json
        $tname = "Autonomy_" + $m.name
        $tmin = [math]::Max(10, [int]$m.timeout_min * 2)
        $act = New-ScheduledTaskAction -Execute $py -Argument "-X utf8 `"$self\runner.py`" `"$Mission`" --reason schedule" -WorkingDirectory $self
        $trg = New-TriggerFromJson $m.schedule
        $set = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes $tmin)
        $prin = New-Principal
        Register-ScheduledTask -TaskName $tname -Action $act -Trigger $trg -Settings $set -Principal $prin -Description $m.description -Force | Out-Null
        Write-Output "OK: $tname installed from $Mission"
        Write-Output "    手動即時測試: .\$($MyInvocation.MyCommand.Name) -Action run -Mission $($m.name)"
    }

    "remove" {
        if (-not $Mission) { Write-Error "-Mission 需要任務名稱"; exit 1 }
        $tname = "Autonomy_" + $Mission.TrimEnd(".json")
        Unregister-ScheduledTask -TaskName $tname -Confirm:$false
        Write-Output "OK: $tname removed"
    }

    "run" {
        if (-not $Mission) { Write-Error "-Mission 需要任務名稱"; exit 1 }
        $tname = "Autonomy_" + $Mission.TrimEnd(".json")
        Start-ScheduledTask -TaskName $tname
        Write-Output "OK: $tname triggered（稍後看 state\$($Mission.TrimEnd('.json')).json 或任務 log）"
    }

    "list" {
        Write-Output "=== 已安裝 Autonomy 任務 ==="
        Get-ScheduledTask | Where-Object { $_.TaskName -like "Autonomy*" } | ForEach-Object { Write-Output ("{0}  [{1}]  {2}" -f $_.TaskName, $_.State, $_.Description) }
        Write-Output ""
        Write-Output "=== missions 目錄 ==="
        Get-ChildItem "$self\missions\*.json" | ForEach-Object { Write-Output ("- {0}  {1}" -f $_.Name, $_.LastWriteTime) }
    }

    "selfheal" {
        & $py -X utf8 "$self\self_heal.py"
    }
}