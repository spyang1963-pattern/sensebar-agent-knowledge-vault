@echo off
rem 每日把 notebook 的正本（knowledge-base / finance.db / shared）備份到 NAS backup\
rem 用法：雙擊，或由 Windows 工作排程呼叫（見 NAS-WHITEPAPER.md N-11）
chcp 65001 >nul
cd /d %~dp0
if not exist logs mkdir logs
echo [%date% %time%] nas backup start >> logs\backup_daily.log
python -X utf8 nas_backup.py >> logs\backup_daily.log 2>&1
echo [%date% %time%] nas backup rc=%ERRORLEVEL% >> logs\backup_daily.log
