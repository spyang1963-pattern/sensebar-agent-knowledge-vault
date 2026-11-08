@echo off
rem Daily 23:10 (notebook): harvest all producer outboxes into knowledge-base.
rem S3 2026-11-08: prefer NAS exchange\<machine>\outbox for every producer;
rem if that NAS slot is empty/unreachable, fall back to reading the machine directly (Tailscale).
rem Then fix YouTube link format (fix_youtube_links.py, idempotent).
rem NOTE: keep this file ASCII-only before chcp; UTF-8 CJK bytes can contain & | and break cmd parsing.
chcp 65001 >nul
cd /d D:\AI-Agent-Workspace
if not exist logs mkdir logs
echo [%date% %time%] harvest start >> logs\harvest_pc.log
python -X utf8 harvest_pc.py --prefer-nas >> logs\harvest_pc.log 2>&1
echo [%date% %time%] harvest rc=%ERRORLEVEL% >> logs\harvest_pc.log
python -X utf8 fix_youtube_links.py --apply >> logs\harvest_pc.log 2>&1
echo [%date% %time%] links rc=%ERRORLEVEL% >> logs\harvest_pc.log
