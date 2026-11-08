@echo off
rem Daily 22:50 (pc1/pc2/pc3): publish KB outputs into outbox.
rem S3 2026-11-08: prefer NAS exchange\<machine>\outbox; fall back to local shared\<machine>\outbox.
rem Machine comes from config.py, so the same file works on every producer (no editing per PC).
rem NAS host: LAN 192.168.1.121 first, then tailnet 100.65.113.20 (PC2 cannot reach the LAN IP).
rem NOTE: keep this file ASCII-only before chcp; UTF-8 CJK bytes can contain & | and break cmd parsing.
chcp 65001 >nul
cd /d D:\AI-Agent-Workspace
if not exist logs mkdir logs
for /f "usebackq delims=" %%m in (`python -X utf8 -c "import config;print(config.MACHINE)"`) do set "MACHINE=%%m"
set "NAS_OUTBOX=\\192.168.1.121\exchange\%MACHINE%\outbox"
if not exist "%NAS_OUTBOX%\." set "NAS_OUTBOX=\\100.65.113.20\exchange\%MACHINE%\outbox"
set "NAS_LEDGER=working\_outbox_published_nas.json"
echo [%date% %time%] publish start machine=%MACHINE% >> logs\publish_outbox.log
if not exist "%NAS_OUTBOX%\." goto local

echo [%date% %time%] target = NAS %NAS_OUTBOX% >> logs\publish_outbox.log
python -X utf8 publish_outbox.py --outbox "%NAS_OUTBOX%" --ledger "%NAS_LEDGER%" >> logs\publish_outbox.log 2>&1
if not errorlevel 1 goto done
echo [%date% %time%] NAS publish failed rc=%ERRORLEVEL% - local fallback >> logs\publish_outbox.log

:local
echo [%date% %time%] target = LOCAL >> logs\publish_outbox.log
python -X utf8 publish_outbox.py >> logs\publish_outbox.log 2>&1

:done
echo [%date% %time%] publish rc=%ERRORLEVEL% >> logs\publish_outbox.log
