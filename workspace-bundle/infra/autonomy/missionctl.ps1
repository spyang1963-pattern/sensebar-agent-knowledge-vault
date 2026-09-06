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
# Task logon strategy (PC3 has no known password):
#   1) If the user enters a password at the prompt, try Password logon
#      (runs even when logged out).
#   2) If cancelled, fall back to Interactive (runs while the user stays
#      logged on - the common AnyDesk setup).

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
    # Returns $null when the user cancelled (no password supplied) -
    # callers must treat that as "use Interactive logon".
    param([string]$User = $env:USERNAME)
    $cred = $null
    try {
        $cred = Get-Credential -UserName $User -Message "輸入 Windows 登入密碼（讓任務在未登入時也能執行）；取消＝僅登入時執行"
    } catch {
        $cred = $null
    }
    if ($null -ne $cred) {
        return ,(New-ScheduledTaskPrincipal -UserId $User -LogonType Password -RunLevel Highest)
    }
    return ,$null
}

function Register-TaskAny {
    # Register a task using any working logon mode. Tries Password when a
    # password was supplied, else Interactive. Never prints a false "OK"
    # on failure (ErrorAction Stop + real exit code).
    param(
        [string]$TaskName,
        $Action,
        $Trigger,
        $Settings,
        $Description
    )
    $prin = New-Principal
    if ($null -ne $prin) {
        try {
            Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
                -Settings $Settings -Principal $prin -Description $Description `
                -Force -ErrorAction Stop | Out-Null
            Write-Output "OK: $TaskName installed (Password, 未登入也執行)"
            return $true
        } catch {
            Write-Output "  密碼註冊失敗 ($($_.Exception.Message))，改用 Interactive…"
        }
    }
    try {
        $prinI = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger `
            -Settings $Settings -Principal $prinI -Description $Description `
            -Force -ErrorAction Stop | Out-Null
        Write-Output "OK: $TaskName installed (Interactive, 需登入才執行)"
        return $true
    } catch {
        Write-Error "FAILED: 無法註冊 $TaskName - $($_.Exception.Message)"
        exit 1
    }
}

function New-TriggerFromJson {
    param($Sched)
    if ($Sched.kind -eq "daily") {
        $at = $Sched.start
        if ($at -notmatch ":") { $at = "$at:00" }
        return New-ScheduledTaskTrigger -Daily -At $at
    }
    # interval
    $mins = [int]$Sched.minutes
    $sh, $sm = "0", "0"
    if ($Sched.start -and ($Sched.start -match ":")) { $sh, $sm = ($Sched.start -split ":") }
    # if start time already passed today, begin immediately
    # (rolling interval tasks must not be deferred a whole day).
    $at = Get-Date -Hour ([int]$sh) -Minute ([int]$sm) -Second 0
    if ($at -lt (Get-Date)) { $at = Get-Date }
    return New-ScheduledTaskTrigger -Once -At $at -RepetitionInterval (New-TimeSpan -Minutes $mins) -RepetitionDuration (New-TimeSpan -Days 3650)
}

switch ($Action) {

    "guard" {
        $tname = "Autonomy_Guard"
        $act = New-ScheduledTaskAction -Execute $py -Argument "-X utf8 `"$self\self_heal.py`"" -WorkingDirectory $self
        $trg = New-ScheduledTaskTrigger -Once -At (Get-Date -Hour 0 -Minute 0 -Second 0) -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Days 3650)
        $set = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
        Register-TaskAny -TaskName $tname -Action $act -Trigger $trg -Settings $set -Description "Autonomy 看門狗（自動 pull/自癒/通知）" | Out-Null
    }

    "install" {
        if (-not $Mission) { Write-Error "-Mission 需要 mission.json 路徑"; exit 1 }
        $m = Get-Content -Raw -Encoding UTF8 $Mission | ConvertFrom-Json
        $tname = "Autonomy_" + $m.name
        $tmin = [math]::Max(10, [int]$m.timeout_min * 2)
        $act = New-ScheduledTaskAction -Execute $py -Argument "-X utf8 `"$self\runner.py`" `"$Mission`" --reason schedule" -WorkingDirectory $self
        $trg = New-TriggerFromJson $m.schedule
        $set = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes $tmin)
        Register-TaskAny -TaskName $tname -Action $act -Trigger $trg -Settings $set -Description $m.description | Out-Null
        Write-Output "    手動即時測試: .\$($MyInvocation.MyCommand.Name) -Action run -Mission $($m.name)"
    }

    "remove" {
        if (-not $Mission) { Write-Error "-Mission 需要任務名稱"; exit 1 }
        $tname = "Autonomy_" + $Mission.TrimEnd(".json")
        Unregister-ScheduledTask -TaskName $tname -Confirm:$false -ErrorAction SilentlyContinue
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