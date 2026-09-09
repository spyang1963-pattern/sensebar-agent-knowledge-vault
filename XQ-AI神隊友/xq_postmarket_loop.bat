@echo off
REM ============================================================
REM  xq_postmarket_loop.bat - run postmarket analysis and publish
REM  (called by Windows Task Scheduler at 22:00 / 08:35)
REM
REM  Usage: xq_postmarket_loop.bat <evening|morning>
REM
REM  Steps: prep (gather five data sources -> input md)
REM         report (Gemini -> prediction md)
REM         render dashboard 4th tab -> xq_dashboard.html -> GitHub Pages
REM ============================================================
chcp 65001 >nul
set SLOT=%~1
if "%SLOT%"=="" set SLOT=evening
cd /d "%~dp0"

echo [postmarket] slot=%SLOT% start: %date% %time%

REM ---- Step 1: gather five data sources into input md ----
python "%~dp0routines\postmarket_prep.py" --slot %SLOT%
if errorlevel 1 goto :fail

REM ---- Step 2: Gemini prediction report ----
python "%~dp0routines\postmarket_report.py" --slot %SLOT%
if errorlevel 1 goto :fail

REM ---- Step 3: rebuild dashboard (4th tab embeds latest report) ----
python "%~dp0routines\render_html.py" --dashboard
if errorlevel 1 goto :fail

REM ---- Step 4: publish to GitHub Pages (xq-dashboard repo) ----
python "%~dp0publisher\deploy.py"
if errorlevel 1 goto :fail

echo [postmarket] done: %date% %time%
exit /b 0

:fail
echo [postmarket] FAILED at step. See messages above.
exit /b 1