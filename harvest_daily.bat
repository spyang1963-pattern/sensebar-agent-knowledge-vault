@echo off
rem 每日 23:10（notebook）從 PC1/PC2/PC3 的 outbox 收割到 knowledge-base
rem 收割後自動把 YouTube 連結修成可點格式（fix_youtube_links.py 是冪等的）
chcp 65001 >nul
cd /d D:\AI-Agent-Workspace
if not exist logs mkdir logs
echo [%date% %time%] harvest start >> logs\harvest_pc.log
python -X utf8 harvest_pc.py >> logs\harvest_pc.log 2>&1
echo [%date% %time%] harvest rc=%ERRORLEVEL% >> logs\harvest_pc.log
python -X utf8 fix_youtube_links.py --apply >> logs\harvest_pc.log 2>&1
echo [%date% %time%] links rc=%ERRORLEVEL% >> logs\harvest_pc.log
