@echo off
chcp 65001 >nul
cd /d "D:\!!AI agent 專案夾\三師爸的 AI agent 學習 AI agent"

echo [%date% %time%] 開始同步...

REM 拉取最新版本
git pull

REM 檢查是否有變更
git status --porcelain >nul 2>&1
if %errorlevel%==0 (
    REM 有變更就提交並推送
    git add .
    git commit -m "auto-sync: %date% %time%"
    git push
    echo [%date% %time%] 同步完成：已推送變更
) else (
    echo [%date% %time%] 同步完成：無變更
)
