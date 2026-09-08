@echo off
rem XQ-AI helper : environment check (double-click me)
cd /d "%~dp0"
powershell.exe -STA -NoProfile -ExecutionPolicy Bypass -File "%~dp0routines\check_env.ps1"
echo.
pause
