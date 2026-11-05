@echo off
chcp 65001 >nul
cd /d "D:\AI-Agent-Workspace"
python auto_update.py
rem 排程呼叫時帶 --no-pause，避免 cmd 卡在 pause 讓工作一直顯示「執行中」
if /i not "%~1"=="--no-pause" pause
