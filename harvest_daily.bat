@echo off
rem Daily 23:10 (notebook): harvest all producer outboxes into knowledge-base.
rem S3 2026-11-08: pc1 reads NAS exchange\pc1\outbox first; if NAS unreachable, fall back to PC1 direct (Tailscale).
rem Then fix YouTube link format (fix_youtube_links.py, idempotent).
rem NOTE: keep this file ASCII-only before chcp; UTF-8 CJK bytes can contain & | and break cmd parsing.
chcp 65001 >nul
cd /d D:\AI-Agent-Workspace
if not exist logs mkdir logs
set "NAS_PC1=\\192.168.1.121\exchange\pc1\outbox"
echo [%date% %time%] harvest start >> logs\harvest_pc.log
if not exist "%NAS_PC1%\." goto pc1direct

echo [%date% %time%] pc1 source = NAS >> logs\harvest_pc.log
python -X utf8 harvest_pc.py --machine pc1 --root "%NAS_PC1%" >> logs\harvest_pc.log 2>&1
goto pc1done

:pc1direct
echo [%date% %time%] pc1 source = PC1 direct (NAS unreachable) >> logs\harvest_pc.log
python -X utf8 harvest_pc.py --machine pc1 >> logs\harvest_pc.log 2>&1

:pc1done
echo [%date% %time%] harvest pc1 rc=%ERRORLEVEL% >> logs\harvest_pc.log
python -X utf8 harvest_pc.py --machine pc2 --machine pc3 >> logs\harvest_pc.log 2>&1
echo [%date% %time%] harvest pc2/pc3 rc=%ERRORLEVEL% >> logs\harvest_pc.log
python -X utf8 fix_youtube_links.py --apply >> logs\harvest_pc.log 2>&1
echo [%date% %time%] links rc=%ERRORLEVEL% >> logs\harvest_pc.log
