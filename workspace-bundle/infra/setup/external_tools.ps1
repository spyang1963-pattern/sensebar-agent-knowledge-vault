# External tools one-click installer (idempotent, safe to re-run)
# Usage: powershell -ExecutionPolicy Bypass -File external_tools.ps1
# After install, open a NEW terminal so updated PATH takes effect.

$ErrorActionPreference = "Continue"

$tools = @(
    @{ Id = "Gyan.FFmpeg";       Name = "ffmpeg (media processing / yt-dlp merge)" },
    @{ Id = "VideoLAN.VLC";      Name = "VLC (subtitle burning; must be default path)" },
    @{ Id = "Obsidian.Obsidian"; Name = "Obsidian (knowledge base browsing)" },
    @{ Id = "UB-Mannheim.TesseractOCR"; Name = "Tesseract OCR (file_processors.py pytesseract)" },
    # 2026-11-06 事故：沒有 JS runtime 時 yt-dlp 抓 metadata 正常、真正下載影片一律 403。
    # 這一項不是選配，缺了 YouTube 任務會全部失敗（PC1 曾 66 支全滅）。
    @{ Id = "DenoLand.Deno";     Name = "Deno (yt-dlp JS runtime; without it YouTube downloads return 403)" },
    # 2026-11-08：PC 與 NAS 不同網段時，靠 Tailscale 走 tailnet 連 NAS。登入仍需人工（tailscale up）。
    @{ Id = "Tailscale.Tailscale"; Name = "Tailscale (tailnet access to NAS; run 'tailscale up' after install)" }
)

foreach ($t in $tools) {
    Write-Host ""
    Write-Host "==> Installing $($t.Name) [$($t.Id)]..."
    winget install --id $t.Id -e --accept-source-agreements --accept-package-agreements
}

# 2026-11-08 PC2 實踩：Tesseract 的 winget 套件不會把自己加進 PATH，
# 檔案存在但 pytesseract 仍拋 TesseractNotFoundError。這裡補進使用者 PATH（只加一次）。
$tessDir = "C:\Program Files\Tesseract-OCR"
if (Test-Path (Join-Path $tessDir "tesseract.exe")) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($userPath -notlike "*$tessDir*") {
        [Environment]::SetEnvironmentVariable("Path", ($userPath.TrimEnd(';') + ";" + $tessDir), "User")
        Write-Host "  [OK] 已把 $tessDir 加入使用者 PATH（需開新終端）"
    } else {
        Write-Host "  [OK] $tessDir 已在使用者 PATH"
    }
    if ($env:Path -notlike "*$tessDir*") { $env:Path = $env:Path + ";" + $tessDir }
} else {
    Write-Host "  [WARN] 找不到 $tessDir\tesseract.exe（OCR 會失敗）" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== Verify (in a NEW terminal) ==="
Write-Host "  ffmpeg -version"
Write-Host "  tesseract --version"
Write-Host "  deno --version            # yt-dlp needs it, otherwise YouTube downloads return 403"
Write-Host "  tailscale version         # then: tailscale up  (browser login, one time)"
Write-Host "  Test-Path 'C:\Program Files\VideoLAN\VLC\vlc.exe'   # run_pipeline.py hardcodes this path"
