@echo off
REM ============================================================
REM  xq_postmarket_loop.bat - run postmarket analysis and publish
REM  (called by Windows Task Scheduler at 22:00 / 06:30)
REM
REM  Usage: xq_postmarket_loop.bat <evening|morning>
REM
REM  Steps: prep (gather five data sources -> input md)
REM         report (Gemini -> prediction md)
REM         render dashboard 4th tab -> xq_dashboard.html -> GitHub Pages
REM
REM  Every run is appended to logs\postmarket_YYYYMMDD.log so scheduled-run
REM  failures (e.g. Gemini 503 overload) can be diagnosed afterwards.
REM ============================================================
chcp 65001 >nul
set SLOT=%~1
if "%SLOT%"=="" set SLOT=evening
cd /d "%~dp0"

set LOGDIR=%~dp0logs
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
set LOGFILE=%LOGDIR%\postmarket_%date:~0,4%%date:~5,2%%date:~8,2%.log

echo ===== [postmarket] slot=%SLOT% start: %date% %time% ===== >> "%LOGFILE%"

REM ---- Step 0: audit today's forecast performance (evening only, after close) ----
if "%SLOT%"=="evening" (
  echo [step0] predict_audit >> "%LOGFILE%"
  python "%~dp0routines\predict_audit.py" >> "%LOGFILE%" 2>&1
)

REM ---- Step 1: gather five data sources into input md ----
echo [step1] prep >> "%LOGFILE%"
python "%~dp0routines\postmarket_prep.py" --slot %SLOT% >> "%LOGFILE%" 2>&1
if errorlevel 1 goto :fail

REM ---- Step 2: Gemini prediction report ----
echo [step2] report >> "%LOGFILE%"
python "%~dp0routines\postmarket_report.py" --slot %SLOT% >> "%LOGFILE%" 2>&1
if errorlevel 1 goto :fail

REM ---- Step 3: rebuild dashboard (4th tab embeds latest report) ----
echo [step3] render >> "%LOGFILE%"
python "%~dp0routines\render_html.py" --dashboard >> "%LOGFILE%" 2>&1
if errorlevel 1 goto :fail

REM ---- Step 4: publish to GitHub Pages (xq-dashboard repo) ----
echo [step4] deploy >> "%LOGFILE%"
python "%~dp0publisher\deploy.py" >> "%LOGFILE%" 2>&1
if errorlevel 1 goto :fail

echo [postmarket] done: %date% %time% >> "%LOGFILE%"
exit /b 0

:fail
echo [postmarket] FAILED at step (errorlevel=1). See log above. >> "%LOGFILE%"
exit /b 1
