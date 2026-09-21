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
REM
REM  Every round is appended to logs\snapshot_YYYYMMDD.log so that missed
REM  rounds (Excel DDE not feeding -> stale/SKIP) can be audited later.
REM  A stale/SKIP kind is retried once after 20s before giving up.
REM ============================================================
chcp 65001 >nul

cd /d "%~dp0"

set LOGDIR=%~dp0logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set LOGFILE=%LOGDIR%\snapshot_%date:~0,4%%date:~5,2%%date:~8,2%.log
set TMPOUT=%TEMP%\xq_snap_%RANDOM%_%RANDOM%.txt

echo ===== round %date% %time% ===== >> "%LOGFILE%"

call :cap rank
call :cap breadth
call :cap notes

echo [snapshot] render dashboard >> "%LOGFILE%"
python "%~dp0routines\render_html.py" --dashboard >> "%LOGFILE%" 2>&1
echo [snapshot] deploy >> "%LOGFILE%"
python "%~dp0publisher\deploy.py" >> "%LOGFILE%" 2>&1

echo [xq_snapshot_loop] done: %date% %time% >> "%LOGFILE%"
del "%TMPOUT%" 2>nul
exit /b 0

REM ---- capture one kind; retry once if stale/SKIP ----
:cap
powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File "%~dp0routines\snapshot.ps1" -Kind %1 > "%TMPOUT%" 2>&1
type "%TMPOUT%" >> "%LOGFILE%"
findstr /C:"stale=1" /C:"SKIP=1" "%TMPOUT%" >nul
if not errorlevel 1 (
  echo [snapshot] %1 stale/SKIP - retry once in 20s >> "%LOGFILE%"
  powershell.exe -NoProfile -Command "Start-Sleep -Seconds 20" >nul 2>&1
  powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File "%~dp0routines\snapshot.ps1" -Kind %1 > "%TMPOUT%" 2>&1
  type "%TMPOUT%" >> "%LOGFILE%"
)
exit /b 0
