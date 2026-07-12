@echo off
chcp 65001 >nul
echo ==========================================
echo   新電腦環境設定 — 一鍵安裝
echo ==========================================
echo.
echo 此腳本會在新電腦上設定完整的工作環境
echo 包含：Git、Python、ffmpeg、VLC、opencode、專案同步
echo.

:: ============================================
:: Step 1: 安裝 Git
:: ============================================
echo [1/8] 檢查 Git...
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Git 未安裝，嘗試用 winget 安裝...
    winget install --id Git.Git --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo [ERR] Git 安裝失敗，請手動安裝
        echo 下載：https://git-scm.com/download/win
        pause
        exit /b 1
    )
    echo [OK] Git 安裝完成
) else (
    echo [OK] Git 已安裝
)
echo.

:: ============================================
:: Step 2: 安裝 Python
:: ============================================
echo [2/8] 檢查 Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Python 未安裝，嘗試用 winget 安裝...
    winget install --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo [ERR] Python 安裝失敗，請手動安裝 Python 3.10+
        echo 下載：https://www.python.org/downloads/
        pause
        exit /b 1
    )
    echo [OK] Python 安裝完成
) else (
    echo [OK] Python 已安裝
)
python --version
echo.

:: ============================================
:: Step 3: 安裝 ffmpeg
:: ============================================
echo [3/8] 檢查 ffmpeg...
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] ffmpeg 未安裝，嘗試用 winget 安裝...
    winget install --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo [WARN] ffmpeg 安裝失敗，請手動安裝
        echo 下載：https://www.gyan.dev/ffmpeg/builds/
    )
)
ffmpeg -version >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] ffmpeg 已安裝
) else (
    echo [WARN] ffmpeg 可能需要重啟後才可用
)
echo.

:: ============================================
:: Step 4: 安裝 VLC（可選）
:: ============================================
echo [4/8] 檢查 VLC...
if exist "C:\Program Files\VideoLAN\VLC\vlc.exe" (
    echo [OK] VLC 已安裝
) else (
    echo [INFO] VLC 未安裝，嘗試用 winget 安裝...
    winget install --id VideoLAN.VLC --accept-package-agreements --accept-source-agreements
    echo [OK] VLC 安裝完成
)
echo.

:: ============================================
:: Step 5: 安裝 Python 套件
:: ============================================
echo [5/8] 安裝 Python 套件...
pip install auto-editor groq openai python-dotenv yt-dlp pyyaml plyer --quiet
if %errorlevel% neq 0 (
    echo [WARN] 部分套件安裝失敗，請手動檢查
) else (
    echo [OK] Python 套件安裝完成
)
echo.

:: ============================================
:: Step 6: 設定 Groq API Key
:: ============================================
echo [6/8] 設定 Groq API Key...
if exist "%USERPROFILE%\.groq_api_key" (
    echo [OK] API Key 已存在
) else (
    echo [INFO] 請先到 https://console.groq.com 建立 API Key
    set /p KEY="請貼上你的 Groq API Key（按 Enter 跳過）: "
    if "!KEY!"=="" (
        echo [WARN] 未輸入 Key，之後需手動設定
    ) else (
        echo !KEY!> "%USERPROFILE%\.groq_api_key"
        echo [OK] API Key 已儲存
    )
)
echo.

:: ============================================
:: Step 7: 克隆或更新專案
:: ============================================
echo [7/8] 設定專案目錄...
set "PROJECT_DIR=D:\!!AI agent 專案夾\三師爸的 AI agent 學習 AI agent"

if exist "%PROJECT_DIR%\.git" (
    echo [INFO] 專案目錄已存在，執行 git pull...
    cd /d "%PROJECT_DIR%"
    git pull
) else (
    echo [INFO] 專案目錄不存在，請手動克隆：
    echo   cd "D:\!!AI agent 專案夾"
    echo   git clone 你的遠端倉庫URL "三師爸的 AI agent 學習 AI agent"
    echo.
    echo 或者從這台筆電的 Git 倉庫設定遠端：
    echo   在這台筆電上執行：
    echo   cd "%PROJECT_DIR%"
    echo   git remote add pc1 ssh://PC1的IP/D:/!!AI agent 專案夾/三師爸的 AI agent 學習 AI agent
    echo   git remote add pc2 ssh://PC2的IP/D:/!!AI agent 專案夾/三師爸的 AI agent 學習 AI agent
)
echo.

:: ============================================
:: Step 8: 設定 opencode
:: ============================================
echo [8/8] 檢查 opencode...
opencode --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] opencode 未安裝
    echo 請安裝 opencode：https://opencode.ai
    echo 或執行：npm install -g opencode
) else (
    echo [OK] opencode 已安裝
)
echo.

:: ============================================
:: 完成
:: ============================================
echo ==========================================
echo   設定完成！
echo ==========================================
echo.
echo 接下來：
echo   1. 如果專案還沒克隆，請手動執行 git clone
echo   2. 執行 cd "%PROJECT_DIR%"
echo   3. 執行 opencode 開始使用
echo   4. 首次使用建議跑一次：
echo      python run_pipeline.py --help
echo.
echo 遠端連線（從這台筆電連到這台）：
echo   https://remotedesktop.google.com/access
echo   安裝 Chrome 遠端桌面元件後即可連線
echo.
pause
