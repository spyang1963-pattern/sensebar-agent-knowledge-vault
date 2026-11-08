@echo off
rem Daily 22:50 (PC1): publish KB outputs into outbox.
rem S3 2026-11-08: prefer NAS exchange\pc1\outbox; fall back to local shared\pc1\outbox.
rem Ledgers are separate: NAS uses _outbox_published_nas.json, local uses the default one.
rem NOTE: keep this file ASCII-only before chcp; UTF-8 CJK bytes can contain & | and break cmd parsing.
chcp 65001 >nul
cd /d D:\AI-Agent-Workspace
if not exist logs mkdir logs
set "NAS_OUTBOX=\\192.168.1.121\exchange\pc1\outbox"
set "NAS_LEDGER=working\_outbox_published_nas.json"
echo [%date% %time%] publish start >> logs\publish_outbox.log
if not exist "%NAS_OUTBOX%\." goto local

echo [%date% %time%] target = NAS >> logs\publish_outbox.log
python -X utf8 publish_outbox.py --outbox "%NAS_OUTBOX%" --ledger "%NAS_LEDGER%" >> logs\publish_outbox.log 2>&1
if not errorlevel 1 goto done
echo [%date% %time%] NAS publish failed rc=%ERRORLEVEL% - local fallback >> logs\publish_outbox.log

:local
echo [%date% %time%] target = LOCAL >> logs\publish_outbox.log
python -X utf8 publish_outbox.py >> logs\publish_outbox.log 2>&1

:done
echo [%date% %time%] publish rc=%ERRORLEVEL% >> logs\publish_outbox.log
