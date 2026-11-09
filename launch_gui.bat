@echo off
setlocal
rem Launch the task manager GUI (pythonw, no console window).
rem Works on every machine: no absolute paths, no Chinese in this file.
rem WHY THESE LINES:
rem  - PYTHONIOENCODING=utf-8 : the GUI reads worker/yt-dlp/auto-editor output with
rem    subprocess(..., encoding="utf-8"); without this the reader threads die on cp950 CJK.
rem  - pythonw first, then pyw, then python as a last resort (a console stays visible).
set "PYTHONIOENCODING=utf-8"
cd /d "%~dp0"

for %%I in (pythonw.exe) do if not "%%~$PATH:I"=="" (
  start "" "%%~$PATH:I" "task_manager_gui.py"
  exit /b 0
)
for %%I in (pyw.exe) do if not "%%~$PATH:I"=="" (
  start "" "%%~$PATH:I" "task_manager_gui.py"
  exit /b 0
)

echo [WARN] pythonw.exe / pyw.exe not found in PATH; starting with python.exe instead.
echo        If the window still does not appear, see the message box or
echo        working\task_manager_gui_error.log
for %%I in (python.exe) do if not "%%~$PATH:I"=="" (
  "%%~$PATH:I" "task_manager_gui.py"
  exit /b %ERRORLEVEL%
)

echo [ERR] Python not found in PATH. Run deploy.ps1 first (or add Python to PATH).
pause
exit /b 1
