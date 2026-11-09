@echo off
rem Daily 22:30 (pc1/pc2/pc3): scan watched channels, THEN publish the KB output.
rem Chained on purpose: publishing while the scan is still writing would pack
rem half-written KB files, and the harvester keeps the first version it sees
rem (later content differences become conflicts). Scan first, publish after.
rem NOTE: keep this file ASCII-only before chcp; UTF-8 CJK bytes can contain & | and break cmd parsing.
chcp 65001 >nul
cd /d D:\AI-Agent-Workspace
if not exist logs mkdir logs
echo [%date% %time%] ==== channel_watcher --once start ==== >> logs\channel_watcher.log
python -X utf8 channel_watcher.py --once >> logs\channel_watcher.log 2>&1
set "SCAN_RC=%ERRORLEVEL%"
echo [%date% %time%] ==== channel_watcher --once rc=%SCAN_RC% ==== >> logs\channel_watcher.log
call publish_daily.bat
echo [%date% %time%] ==== chain done scan_rc=%SCAN_RC% publish_rc=%ERRORLEVEL% ==== >> logs\channel_watcher.log
