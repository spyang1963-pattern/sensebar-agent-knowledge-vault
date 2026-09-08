@echo off
REM ============================================================
REM  xq_snapshot_loop.bat - capture three kinds of snapshots each round
REM  (called by Windows Task Scheduler every 15 min)
REM
REM  Captures rank / breadth / notes snapshots into routines\snapshots\
REM  then rebuilds xq_dashboard.html and publishes it to GitHub Pages
REM  (spyang1963-pattern/xq-dashboard).
REM
REM  Prerequisite: Excel must be open (contains quote sheet pasted from XQ)
REM                and PC must not sleep, otherwise it prints SKIP / stale.
REM ============================================================
chcp 65001 >nul

cd /d "%~dp0"

REM ---- capture three kinds of snapshots (-STA is required for COM) ----
powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File "%~dp0routines\snapshot.ps1" -Kind rank
powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File "%~dp0routines\snapshot.ps1" -Kind breadth
powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File "%~dp0routines\snapshot.ps1" -Kind notes

echo.
REM ---- rebuild single-page dashboard (all kinds + history) ----
python "%~dp0routines\render_html.py" --dashboard

echo.
REM ---- publish to GitHub Pages (xq-dashboard repo) ----
python "%~dp0publisher\deploy.py"

echo.
echo [xq_snapshot_loop] done: %date% %time%