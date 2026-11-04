<#
.SYNOPSIS
  PC1 / PC2 / PC3 / notebook 部署單一入口。

.DESCRIPTION
  1. 驗證機器身份（讀 repo 根目錄 config.py，與 health_check 同一個來源）
  2. 執行 setup_new_pc.bat（-SkipSetup 可跳過）
  3. 印出健檢摘要（只列 ❌ / 待補項目）
  4. 可選註冊排程（-RegisterTasks，預設不註冊）

.PARAMETER Machine
  這台機器「應該」是哪一台。與 config.py 偵測結果不符會直接中止，
  避免在錯的機器上建立任務或覆蓋設定。

.PARAMETER ProjectDir
  預設 D:\AI-Agent-Workspace（三機統一）；未指定時優先用腳本所在 repo。

.PARAMETER DryRun
  只印步驟，不安裝、不寫入、不註冊排程。

.PARAMETER SkipSetup
  跳過 setup_new_pc.bat，只做身份檢查 + 健檢（已裝好時用）。

.PARAMETER RegisterTasks
  註冊排程（FinanceNews_Pipeline / MorningReport / EveningReport / ChannelWatcherDaily）。
  排程是「單一寫入者」：確認其他機器已停用同名任務再加這個參數。

.PARAMETER UnregisterTasks
  移除上述 4 個排程（切換機器時在舊機執行）。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File workspace-bundle\infra\setup\deploy.ps1 -Machine pc1 -DryRun

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File workspace-bundle\infra\setup\deploy.ps1 -Machine pc1

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File workspace-bundle\infra\setup\deploy.ps1 -SkipSetup -RegisterTasks
#>
param(
    [ValidateSet("notebook", "pc1", "pc2", "pc3")]
    [string]$Machine,

    [string]$ProjectDir,

    [switch]$DryRun,
    [switch]$SkipSetup,
    [switch]$RegisterTasks,
    [switch]$UnregisterTasks
)

$ErrorActionPreference = "Stop"

# ── 排程定義（與 ONBOARDING 第 8 步一致）──
$TaskDefs = @(
    @{ Name = "FinanceNews_Pipeline";       Script = "pipeline.py";       Args = @("--full", "--batch", "150", "--time-budget", "480"); Kind = "interval"; Minutes = 30;  Desc = "金融新聞 pipeline（每 30 分）" }
    @{ Name = "FinanceNews_MorningReport";  Script = "pipeline.py";       Args = @("--report", "--deep", "--slot", "morning");           Kind = "daily";    At = "07:00"; Desc = "金融早報（每天 07:00）" }
    @{ Name = "FinanceNews_EveningReport";  Script = "pipeline.py";       Args = @("--report", "--deep", "--slot", "evening");           Kind = "daily";    At = "19:00"; Desc = "金融晚報（每天 19:00）" }
    @{ Name = "ChannelWatcherDaily";        Script = "channel_watcher.py"; Args = @("--once");                                           Kind = "daily";    At = "22:30"; Desc = "頻道監控（每天 22:30）" }
)

function Write-Section($Title) {
    Write-Host ""
    Write-Host ("=" * 56)
    Write-Host "  $Title"
    Write-Host ("=" * 56)
}

function Resolve-ProjectDir {
    param([string]$Requested)

    $candidates = @()
    if ($Requested) { $candidates += $Requested }
    $candidates += (Join-Path $PSScriptRoot "..\..\..")
    $candidates += "D:\AI-Agent-Workspace"

    foreach ($c in $candidates) {
        try {
            $p = (Resolve-Path $c -ErrorAction Stop).Path
        } catch { continue }
        if (Test-Path (Join-Path $p "config.py")) { return $p }
    }

    if ($Requested) { throw "找不到 $Requested\config.py" }
    throw "找不到專案根目錄（含 config.py）；請用 -ProjectDir 指定，例如 -ProjectDir D:\AI-Agent-Workspace"
}

function Get-PythonExe {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $cmd) { throw "找不到 python；請先安裝 Python 3.10+ 並重開終端" }
    return $cmd.Source
}

function Get-MachineInfo {
    param([string]$Python, [string]$Root)

    # 注意：傳給原生 python 的參數不能用雙引號（PowerShell 會吃掉），
    # 因此改用環境變數傳路徑。變數在 python 端用單引號取值。
    $env:DEPLOY_ROOT = $Root
    $code = 'import json, os, sys; sys.path.insert(0, os.environ.get(''DEPLOY_ROOT'', ''.'')); import config; print(json.dumps(config.get_machine_info(), ensure_ascii=False))'

    $prev = [Console]::OutputEncoding
    try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
    $raw = & $Python -X utf8 -c $code
    [Console]::OutputEncoding = $prev

    if (-not $raw) { throw "無法讀取 config.get_machine_info()" }
    return ($raw | Out-String | ConvertFrom-Json)
}

function Get-HealthReport {
    param([string]$Python, [string]$Root)

    $hc = Join-Path $Root "workspace-bundle\infra\health_check.py"
    if (-not (Test-Path $hc)) { throw "找不到 health_check.py：$hc" }

    $prev = [Console]::OutputEncoding
    try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch {}
    # 有些機器上的套件（fitz / win32com 等）會在 import 時把 warning 印到 stdout，
    # 混在 JSON 前面會讓 ConvertFrom-Json 失敗。這裡只取 JSON 區段。
    $raw = & $Python -X utf8 $hc --json 2>$null
    [Console]::OutputEncoding = $prev

    $text = ($raw | Out-String)
    $start = $text.IndexOf("{")
    $end = $text.LastIndexOf("}")
    if ($start -lt 0 -or $end -le $start) {
        throw "健檢沒有回傳 JSON。原始輸出：`n$($text.Trim())"
    }

    $stray = $text.Substring(0, $start).Trim()
    if ($stray) {
        $first = ($stray -split "`r?`n")[0]
        Write-Host "  （健檢附帶輸出，已忽略：$first）" -ForegroundColor DarkGray
    }

    return ($text.Substring($start, $end - $start + 1) | ConvertFrom-Json)
}

function Show-HealthSummary {
    param($Report)

    $fails = @()
    $warns = @()
    $infos = @()

    # health_check 會標記哪些檢查項「不是程式缺漏」（資料／憑證／該機專屬）。
    # 那些缺少時只列在 ℹ️，不算 ❌，避免新機被誤判成安裝失敗。
    $lineNotes = @{}
    if ($Report.PSObject.Properties["line_notes"] -and $Report.line_notes) {
        foreach ($p in $Report.line_notes.PSObject.Properties) {
            $lineNotes[$p.Name] = $p.Value
        }
    }

    foreach ($b in $Report.bundles.PSObject.Properties) {
        $info = $b.Value
        if ($info.packages_missing.Count -gt 0) {
            $warns += "套件（$($info.name)）缺：$($info.packages_missing -join ', ')"
        }
    }

    foreach ($c in $Report.config) {
        if (-not $c.exists) { $warns += "設定檔缺：$($c.file)（$($c.desc)）" }
    }

    $svcMissing = @($Report.services | Where-Object { -not $_.exists } | ForEach-Object { $_.name })
    if ($svcMissing.Count -gt 0) {
        $warns += "排程未註冊：$($svcMissing -join ', ')（切換日才啟用）"
    }

    $capMaps = @(
        @{ Title = "視覺能力"; Map = $Report.vision },
        @{ Title = "生圖能力"; Map = $Report.draw },
        @{ Title = "知識庫管線"; Map = $Report.kb }
    )
    foreach ($cap in $capMaps) {
        foreach ($p in $cap.Map.PSObject.Properties) {
            if ($p.Value -is [bool] -and -not $p.Value) {
                $fails += "$($cap.Title)：$($p.Name)"
            }
        }
    }

    foreach ($ln in $Report.lines.PSObject.Properties) {
        $info = $ln.Value
        $notes = $lineNotes[$ln.Name]
        foreach ($p in $info.PSObject.Properties) {
            if ($p.Name -eq "name") { continue }
            if (-not ($p.Value -is [bool]) -or $p.Value) { continue }
            $note = $null
            if ($notes -and $notes.PSObject.Properties[$p.Name]) {
                $note = $notes.PSObject.Properties[$p.Name].Value
            }
            if ($note) {
                $infos += "$($info.name)：$($p.Name) — $note"
            } else {
                $fails += "任務線 $($info.name)：$($p.Name)"
            }
        }
        $lp = $Report.line_packages.($ln.Name)
        if ($lp -and $lp.missing.Count -gt 0) {
            $warns += "任務線 $($info.name) 套件缺：$($lp.missing -join ', ')"
        }
    }

    Write-Host ""
    Write-Host "  機器：$($Report.machine_name) ($($Report.machine))  角色：$($Report.machine_role -join ', ')"
    Write-Host "  主機名：$($Report.hostname)  Tailscale：$(if ($Report.machine_ip) { $Report.machine_ip } else { '未設定' })"
    Write-Host "  Python：$($Report.python)  Git：$($Report.git.repo_version)"

    if ($fails.Count -eq 0 -and $warns.Count -eq 0 -and $infos.Count -eq 0) {
        Write-Host ""
        Write-Host "  ✅ 四條任務線與能力檢查全綠" -ForegroundColor Green
        return 0
    }

    if ($fails.Count -gt 0) {
        Write-Host ""
        Write-Host "  ❌ 待補（$($fails.Count) 項）" -ForegroundColor Red
        foreach ($f in $fails) { Write-Host "    - $f" }
    }
    if ($warns.Count -gt 0) {
        Write-Host ""
        Write-Host "  ⚠️  提醒（$($warns.Count) 項）" -ForegroundColor Yellow
        foreach ($w in $warns) { Write-Host "    - $w" }
    }
    if ($infos.Count -gt 0) {
        Write-Host ""
        Write-Host "  ℹ️  資料與環境（$($infos.Count) 項，不算安裝失敗）" -ForegroundColor DarkGray
        foreach ($i in $infos) { Write-Host "    - $i" -ForegroundColor DarkGray }
    }

    return ($fails.Count + $warns.Count)
}

function Ensure-RuntimeDirs {
    # git 不追蹤空目錄，新機 clone 後不會有這些執行期目錄
    param([string]$Root)
    $made = @()
    foreach ($d in @("working", "output", "videos")) {
        $p = Join-Path $Root $d
        if (-not (Test-Path -LiteralPath $p)) {
            New-Item -ItemType Directory -Force -Path $p | Out-Null
            $made += $d
        }
    }
    return $made
}

function Invoke-Setup {
    param([string]$Root, [bool]$Preview)

    $bat = Join-Path $Root "setup_new_pc.bat"
    if (-not (Test-Path $bat)) { throw "找不到 setup_new_pc.bat：$bat" }

    $cmdArgs = @("/c", "`"$bat`"")
    if ($Preview) { $cmdArgs += "--dry-run" }

    Write-Host "  > cmd $($cmdArgs -join ' ')"
    & cmd.exe @cmdArgs
    if ($LASTEXITCODE -ne 0) { throw "setup_new_pc.bat 失敗（exit $LASTEXITCODE）" }
}

function Show-RepoState {
    param([string]$Root)

    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Host "  ⚠️  找不到 git（setup 會嘗試安裝）"
        return
    }

    $branch = (& git -C $Root rev-parse --abbrev-ref HEAD 2>$null | Select-Object -First 1)
    $sha = (& git -C $Root rev-parse --short HEAD 2>$null | Select-Object -First 1)
    $dirty = @(& git -C $Root status --porcelain 2>$null).Count

    Write-Host "  分支：$branch  目前版本：$sha  未提交變更：$dirty 個檔案"

    $remoteSha = $null
    try {
        & git -C $Root fetch --quiet origin 2>$null | Out-Null
        $remoteSha = (& git -C $Root rev-parse --short "origin/$branch" 2>$null | Select-Object -First 1)
    } catch { }

    if ($dirty -gt 0) {
        Write-Host "  ⚠️  有 $dirty 個未提交變更：git pull --ff-only 會被拒絕，機器會留在舊版程式。" -ForegroundColor Yellow
        Write-Host "      部署前先處理（commit / stash / 還原），或在該機確認這些變更是預期的。"
    } elseif ($remoteSha -and $remoteSha -ne $sha) {
        Write-Host "  ⚠️  與 origin/$branch ($remoteSha) 不同：setup 會嘗試 git pull --ff-only。" -ForegroundColor Yellow
    } else {
        Write-Host "  ✅ 程式碼與遠端一致" -ForegroundColor Green
    }
}

function Register-DeployTasks {
    param([string]$Root, [string]$Python, [bool]$Preview)

    $existing = @()
    try {
        $existing = @(Get-ScheduledTask -ErrorAction Stop | ForEach-Object { $_.TaskName })
    } catch { }

    foreach ($d in $TaskDefs) {
        if ($Preview) {
            Write-Host "  [dry] 註冊排程 $($d.Name)（$($d.Desc)）"
            continue
        }

        $action = New-ScheduledTaskAction -Execute $Python `
            -Argument (('"{0}" {1}' -f (Join-Path $Root $d.Script), ($d.Args -join ' ')).Trim()) `
            -WorkingDirectory $Root

        if ($d.Kind -eq "interval") {
            $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
                -RepetitionInterval (New-TimeSpan -Minutes $d.Minutes) `
                -RepetitionDuration (New-TimeSpan -Days 9999)
        } else {
            $trigger = New-ScheduledTaskTrigger -Daily -At $d.At
        }

        $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable `
            -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -MultipleInstances IgnoreNew

        $desc = "$($d.Desc)；由 deploy.ps1 建立於 $(Get-Date -Format 'yyyy-MM-dd HH:mm')"

        if ($existing -contains $d.Name) {
            Write-Host "  ↻ 覆蓋既有排程 $($d.Name)"
        }

        try {
            Register-ScheduledTask -TaskName $d.Name -Action $action -Trigger $trigger `
                -Settings $settings -Description $desc -Force | Out-Null
            Write-Host "  ✅ $($d.Name)"
        } catch {
            Write-Warning "  ❌ $($d.Name) 註冊失敗：$($_.Exception.Message)"
            Write-Warning "     若為權限問題，請以「系統管理員」重開 PowerShell 再執行。"
        }
    }
}

function Unregister-DeployTasks {
    param([bool]$Preview)

    foreach ($d in $TaskDefs) {
        if ($Preview) {
            Write-Host "  [dry] 移除排程 $($d.Name)"
            continue
        }
        try {
            Unregister-ScheduledTask -TaskName $d.Name -Confirm:$false -ErrorAction Stop
            Write-Host "  ✅ 已移除 $($d.Name)"
        } catch {
            Write-Host "  - $($d.Name) 不存在或無法移除"
        }
    }
}

# ── 主流程 ──
$root = Resolve-ProjectDir -Requested $ProjectDir
$python = Get-PythonExe

Write-Section "三機部署 — deploy.ps1"
Write-Host "  專案目錄：$root"
Write-Host "  Python   ：$python"
if ($DryRun) { Write-Host "  模式     ：DRY-RUN（不安裝、不寫入、不註冊）" -ForegroundColor Yellow }

# 1. 機器身份
Write-Host ""
Write-Host "[1/5] 機器身份檢查..."
$info = Get-MachineInfo -Python $python -Root $root
$detected = $info.machine

Write-Host "  偵測到：$detected（主機名 $([System.Net.Dns]::GetHostName())）"
Write-Host "  角色  ：$($info.role)    Tailscale：$(if ($info.tailscale_ip) { $info.tailscale_ip } else { '未設定' })"

if ($detected -like "unknown-*") {
    Write-Host ""
    Write-Host "  ❌ 此主機名尚未註冊到 config.py 的 MACHINE_ALIASES" -ForegroundColor Red
    Write-Host "     請加入：`"$(([System.Net.Dns]::GetHostName()).ToLower())`": `"pc?`","
    Write-Host "     位置：$root\config.py"
    exit 1
}

if ($Machine -and $detected -ne $Machine) {
    Write-Host ""
    Write-Host "  ❌ 身份不符：預期 $Machine，實際 $detected" -ForegroundColor Red
    Write-Host "     為了避免在錯的機器覆蓋設定，已中止。"
    Write-Host "     若這台是新機，請先在 config.py 的 MACHINE_ALIASES 加入："
    Write-Host "       `"$(([System.Net.Dns]::GetHostName()).ToLower())`": `"$Machine`","
    exit 1
}

Write-Host "  ✅ 身份確認：$detected" -ForegroundColor Green

# 2. 程式碼狀態（PC1/PC2 可能已有本地變更，會讓 git pull 失敗）
Write-Host ""
Write-Host "[2/5] 程式碼狀態..."
Show-RepoState -Root $root

# 3. 安裝
Write-Host ""
if ($SkipSetup) {
    Write-Host "[3/5] 安裝與執行期目錄 — 安裝已用 -SkipSetup 跳過"
} else {
    Write-Host "[3/5] 安裝與執行期目錄（setup_new_pc.bat）..."
    Invoke-Setup -Root $root -Preview $DryRun.IsPresent
}

# git 不追蹤空目錄，新機 clone 後不會有 working/output/videos，這裡補上
if ($DryRun) {
    Write-Host "  [dry] 建立執行期目錄：working、output、videos"
} else {
    $made = Ensure-RuntimeDirs -Root $root
    if ($made.Count -gt 0) {
        Write-Host "  已建立目錄：$($made -join '、')"
    } else {
        Write-Host "  執行期目錄已存在"
    }
}

# 4. 健檢
Write-Host ""
Write-Host "[4/5] 健檢..."
$pending = 0
$healthOk = $false
try {
    $report = Get-HealthReport -Python $python -Root $root
    $pending = Show-HealthSummary -Report $report
    $healthOk = $true
} catch {
    Write-Warning "  健檢失敗：$($_.Exception.Message)"
}

# 5. 排程
Write-Host ""
if ($UnregisterTasks) {
    Write-Host "[5/5] 移除排程（切換日舊機用）..."
    Unregister-DeployTasks -Preview $DryRun.IsPresent
} elseif ($RegisterTasks) {
    Write-Host "[5/5] 註冊排程..."
    Write-Host "  ⚠️  排程是單一寫入者：請確認其他機器的同名任務已停用。" -ForegroundColor Yellow
    Register-DeployTasks -Root $root -Python $python -Preview $DryRun.IsPresent
} else {
    Write-Host "[5/5] 排程 — 未指定 -RegisterTasks，維持不註冊（預設）"
    Write-Host "      切換日再執行：deploy.ps1 -SkipSetup -RegisterTasks"
}

# 收尾
Write-Section "完成"
Write-Host "  機器：$detected"
if ($healthOk) {
    Write-Host "  待補＋提醒：$pending 項（詳見上方 ❌ / ⚠️；ℹ️ 資料項不計入）"
} else {
    Write-Host "  待補項目：未知 — 健檢沒有完成，請看上方警告並手動執行：" -ForegroundColor Yellow
    Write-Host "    python -X utf8 workspace-bundle\infra\health_check.py"
}
Write-Host ""
Write-Host "  仍須人工處理："
Write-Host "    1. Gemini key：$env:USERPROFILE\.gemini_api_key（每台獨立）"
Write-Host "    2. Telegram  ：$env:USERPROFILE\.telegram_env（BOT_TOKEN / CHAT_ID）"
Write-Host "    3. 資料同步  ：finance.db、knowledge-base\、shared\watched_channels_state.json"
Write-Host "    4. PATH      ：外部工具安裝後需「重開終端」"
Write-Host ""
Write-Host "  文件：workspace-bundle\ONBOARDING.md"
Write-Host "  進度：workspace-bundle\HANDOFF-3MACHINE-DEPLOY.md"
Write-Host ""

if ($DryRun) { exit 0 }
exit 0
