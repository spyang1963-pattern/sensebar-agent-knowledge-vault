@echo off
rem 每日 22:50（PC1）把 KB 產出打包到 shared\<machine>\outbox
rem 由 Windows 排程呼叫；手動執行也可以（publish_daily.bat）
chcp 65001 >nul
cd /d D:\AI-Agent-Workspace
if not exist logs mkdir logs
echo [%date% %time%] publish start >> logs\publish_outbox.log
python -X utf8 publish_outbox.py >> logs\publish_outbox.log 2>&1
echo [%date% %time%] publish rc=%ERRORLEVEL% >> logs\publish_outbox.log
