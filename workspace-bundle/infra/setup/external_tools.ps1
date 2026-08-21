# External tools one-click installer (idempotent, safe to re-run)
# Usage: powershell -ExecutionPolicy Bypass -File external_tools.ps1
# After install, open a NEW terminal so updated PATH takes effect.

$ErrorActionPreference = "Continue"

$tools = @(
    @{ Id = "Gyan.FFmpeg";       Name = "ffmpeg (media processing / yt-dlp merge)" },
    @{ Id = "VideoLAN.VLC";      Name = "VLC (subtitle burning; must be default path)" },
    @{ Id = "Obsidian.Obsidian"; Name = "Obsidian (knowledge base browsing)" }
)

foreach ($t in $tools) {
    Write-Host ""
    Write-Host "==> Installing $($t.Name) [$($t.Id)]..."
    winget install --id $t.Id -e --accept-source-agreements --accept-package-agreements
}

Write-Host ""
Write-Host "=== Verify (in a NEW terminal) ==="
Write-Host "  ffmpeg -version"
Write-Host "  Test-Path 'C:\Program Files\VideoLAN\VLC\vlc.exe'   # run_pipeline.py hardcodes this path"
