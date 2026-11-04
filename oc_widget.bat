@echo off
rem OpenCode quota widget - always-on-top window, zero token cost
rem Pure ASCII on purpose: Chinese text in a .bat breaks line parsing
rem between cp950 and UTF-8 code pages.
cd /d "%~dp0"
start "" pythonw "%~dp0oc_widget.py"
