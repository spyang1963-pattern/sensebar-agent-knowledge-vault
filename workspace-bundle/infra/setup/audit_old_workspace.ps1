# audit_old_workspace.ps1 — 舊工作區「唯讀」盤點（不刪、不改任何東西）
#
# 用途：PC1/PC2 早期測試留下的舊工作區，在刪除或封存前先確認三件事
#   1. 有沒有「未推送」的 commit（刪了就救不回來）
#   2. 有沒有排程任務還在指著這個路徑（刪了會讓排程失敗）
#   3. 有沒有獨有資料（finance.db / knowledge-base / shared 狀態 / output 成品）
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File workspace-bundle\infra\setup\audit_old_workspace.ps1
#   powershell -ExecutionPolicy Bypass -File ... -Path "D:\old1","D:\old2"
#   powershell -ExecutionPolicy Bypass -File ... -Report out.txt

param(
    [string[]]$Path,
    [string]$Report
)

$ErrorActionPreference = "Continue"
$NewRoot = "D:\AI-Agent-Workspace"

if (-not $Path -or $Path.Count -eq 0) {
    $Path = @(
        "D:\!!AI agent 專案夾\三師爸的 AI agent 學習 AI agent",
        "D:\sensebar-agent-knowledge-vault"
    )
}

$lines = New-Object System.Collections.Generic.List[string]

function Emit {
    param([string]$Text)
    Write-Host $Text
    $script:lines.Add($Text)
}

function Size-Of {
    param([string]$Dir)
    $m = Get-ChildItem -LiteralPath $Dir -Recurse -File -Force -ErrorAction SilentlyContinue |
         Measure-Object -Property Length -Sum
    $mb = [math]::Round(($m.Sum / 1MB), 0)
    return @{ MB = $mb; Files = $m.Count }
}

function Git-Info {
    param([string]$Dir)
    $info = @{ Remote = ""; Branch = ""; Head = ""; Ahead = ""; Dirty = ""; Ok = $false }
    $gitDir = Join-Path $Dir ".git"
    if (-not (Test-Path -LiteralPath $gitDir)) { return $info }
    $info.Ok = $true
    $info.Remote = (& git -C $Dir remote get-url origin 2>$null | Select-Object -First 1)
    $info.Branch = (& git -C $Dir rev-parse --abbrev-ref HEAD 2>$null | Select-Object -First 1)
    $info.Head = (& git -C $Dir rev-parse --short HEAD 2>$null | Select-Object -First 1)
    $unpushed = & git -C $Dir rev-list --count HEAD --not --remotes 2>$null
    $info.Ahead = if ($unpushed) { "$unpushed" } else { "?" }
    $dirty = & git -C $Dir status --porcelain 2>$null
    $info.Dirty = if ($dirty) { "$(@($dirty).Count)" } else { "0" }
    return $info
}

function Tasks-Using {
    param([string]$Dir)
    $hits = @()
    try {
        $all = Get-ScheduledTask -ErrorAction Stop
    } catch {
        return @("(無法讀取排程：$($_.Exception.Message))")
    }
    foreach ($t in $all) {
        foreach ($a in $t.Actions) {
            $blob = "$($a.Execute) $($a.Arguments) $($a.WorkingDirectory)"
            if ($blob -and $blob.IndexOf($Dir, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
                $hits += "$($t.TaskPath)$($t.TaskName)  [$($t.State)]"
            }
        }
    }
    return $hits
}

Emit ""
Emit ("=" * 62)
Emit "  舊工作區盤點（唯讀）  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Emit ("  新工作區：$NewRoot")
Emit ("=" * 62)

foreach ($p in $Path) {
    Emit ""
    Emit ("-" * 62)
    Emit "  路徑：$p"
    Emit ("-" * 62)

    if (-not (Test-Path -LiteralPath $p)) {
        Emit "  狀態：不存在（已清掉或路徑不同）"
        continue
    }

    $sz = Size-Of $p
    $last = (Get-Item -LiteralPath $p).LastWriteTime
    Emit "  大小      ：$($sz.MB) MB（$($sz.Files) 個檔案）"
    Emit "  最後寫入  ：$($last.ToString('yyyy-MM-dd HH:mm'))"

    $g = Git-Info $p
    if ($g.Ok) {
        Emit "  Git       ：$($g.Branch) @ $($g.Head)"
        Emit "  遠端      ：$($g.Remote)"
        Emit "  未推送    ：$($g.Ahead) 個 commit   未提交變更：$($g.Dirty) 個檔案"
    } else {
        Emit "  Git       ：無 .git"
    }

    $db = Join-Path $p "financial_news\finance.db"
    if (Test-Path -LiteralPath $db) {
        $dbi = Get-Item -LiteralPath $db
        Emit ("  finance.db：{0:N1} MB（{1}）" -f ($dbi.Length / 1MB), $dbi.LastWriteTime.ToString('yyyy-MM-dd'))
    } else {
        Emit "  finance.db：無"
    }

    $kb = Join-Path $p "knowledge-base"
    if (Test-Path -LiteralPath $kb) {
        $md = @(Get-ChildItem -LiteralPath $kb -Recurse -File -Force -Filter *.md -ErrorAction SilentlyContinue)
        $kbsz = Size-Of $kb
        Emit "  KB        ：$($md.Count) 個 .md／$($kbsz.MB) MB"
    } else {
        Emit "  KB        ：無"
    }

    $st = Join-Path $p "shared\watched_channels_state.json"
    if (Test-Path -LiteralPath $st) {
        Emit "  監控狀態  ：有（$((Get-Item -LiteralPath $st).LastWriteTime.ToString('yyyy-MM-dd HH:mm'))）"
    } else {
        Emit "  監控狀態  ：無"
    }

    foreach ($sub in @("output", "working")) {
        $d = Join-Path $p $sub
        if (Test-Path -LiteralPath $d) {
            $s = Size-Of $d
            Emit ("  {0,-10}：{1} MB／{2} 個檔案" -f $sub, $s.MB, $s.Files)
        }
    }

    $vids = Join-Path $p "videos"
    if (Test-Path -LiteralPath $vids) {
        $s = Size-Of $vids
        Emit ("  videos    ：{0} MB／{1} 個檔案" -f $s.MB, $s.Files)
    }

    $tasks = Tasks-Using $p
    if ($tasks.Count -gt 0) {
        Emit "  ⚠ 排程仍指向此路徑："
        foreach ($t in $tasks) { Emit "      - $t" }
    } else {
        Emit "  排程      ：無任務指向此路徑"
    }
}

Emit ""
Emit ("=" * 62)
Emit "  判斷原則"
Emit ("=" * 62)
Emit "  1) 未推送 > 0   → 先 push 或整包壓縮留存，不要直接刪"
Emit "  2) 排程指向它   → 先改排程或停用，再刪"
Emit "  3) finance.db / KB 有內容但新工作區沒有 → 先複製需要的部分"
Emit "  4) 以上都沒有   → 可整包壓縮後刪除（建議留一份 zip 到 NAS／外接硬碟）"
Emit ""
Emit "  唯讀腳本：本工具不會刪除或修改任何檔案。"
Emit ""

if ($Report) {
    $lines -join [Environment]::NewLine | Set-Content -LiteralPath $Report -Encoding UTF8
    Write-Host "  報告已寫入：$Report"
}
