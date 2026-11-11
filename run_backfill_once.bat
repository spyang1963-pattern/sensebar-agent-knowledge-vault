@echo off
rem One-shot: backfill ALL missing course notes/summaries in KB (user-directed, --no-quota),
rem then fix YouTube links + video .lnk links for the newly created products.
rem Log: logs\backfill_once.log  (delete this task after completion if desired)
cd /d D:\AI-Agent-Workspace
python -X utf8 backfill_products.py --no-quota >> logs\backfill_once.log 2>&1
echo [%date% %time%] backfill rc=%ERRORLEVEL% >> logs\backfill_once.log
python -X utf8 fix_youtube_links.py --apply >> logs\backfill_once.log 2>&1
echo [%date% %time%] ytlinks rc=%ERRORLEVEL% >> logs\backfill_once.log
python -X utf8 fix_video_links.py >> logs\backfill_once.log 2>&1
echo [%date% %time%] vidlinks rc=%ERRORLEVEL% >> logs\backfill_once.log
echo done >> logs\backfill_once.log
