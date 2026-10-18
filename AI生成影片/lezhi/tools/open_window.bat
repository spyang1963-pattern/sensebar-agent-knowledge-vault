@echo off
setlocal
cd /d "%~dp0"
title Yaren Design - Content Window

set "PYEXE=C:\Users\hpspy\AppData\Local\Programs\Python\Python312\python.exe"
if not exist "%PYEXE%" set "PYEXE="
if not defined PYEXE for /f "delims=" %%i in ('where python 2^>nul') do if not defined PYEXE set "PYEXE=%%i"
if not defined PYEXE for /f "delims=" %%i in ('where py 2^>nul') do if not defined PYEXE set "PYEXE=%%i"

if not defined PYEXE (
  echo [ERROR] Python not found. Edit this file and set PYEXE to your python.exe path.
  pause
  exit /b 1
)

echo Starting content window with: %PYEXE%
echo Close this window to stop the server.
echo.
"%PYEXE%" -X utf8 window_server.py
echo.
echo Server stopped.
pause
