@echo off
chcp 65001 >nul
echo ==========================================
echo   AI Agent 影片生產線 — 一鍵安裝
echo ==========================================
echo.

:: 1. 檢查 Python
echo [1/5] 檢查 Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERR] 找不到 Python，請先安裝 Python 3.10+
    echo 下載：https://www.python.org/downloads/
    pause
    exit /b 1
)
python --version
echo [OK] Python 已安裝
echo.

:: 2. 安裝 Python 套件
echo [2/5] 安裝 Python 套件...
pip install auto-editor groq openai python-dotenv --quiet
if %errorlevel% neq 0 (
    echo [ERR] pip install 失敗
    pause
    exit /b 1
)
echo [OK] Python 套件安裝完成
echo.

:: 3. 安裝 ffmpeg
echo [3/5] 檢查 ffmpeg...
ffmpeg -version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] ffmpeg 未安裝，嘗試用 winget 安裝...
    winget install --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
    if %errorlevel% neq 0 (
        echo [WARN] winget 安裝失敗，請手动安裝 ffmpeg
        echo 下載：https://www.gyan.dev/ffmpeg/builds/
    )
)
ffmpeg -version >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] ffmpeg 已安裝
) else (
    echo [WARN] ffmpeg 可能需要手動加入 PATH
)
echo.

:: 4. 安裝 VLC（可選）
echo [4/5] 檢查 VLC...
if exist "C:\Program Files\VideoLAN\VLC\vlc.exe" (
    echo [OK] VLC 已安裝
) else (
    echo [INFO] VLC 未安裝，嘗試用 winget 安裝...
    winget install --id VideoLAN.VLC --accept-package-agreements --accept-source-agreements
    echo [OK] VLC 安裝完成
)
echo.

:: 5. 設定 Groq API Key
echo [5/5] 設定 Groq API Key...
if exist "%USERPROFILE%\.groq_api_key" (
    echo [OK] API Key 已存在
) else (
    echo [INFO] 請先到 https://console.groq.com 建立 API Key
    set /p KEY="請貼上你的 Groq API Key: "
    if "!KEY!"=="" (
        echo [WARN] 未輸入 Key，之後需手動設定
    ) else (
        echo !KEY!> "%USERPROFILE%\.groq_api_key"
        echo [OK] API Key 已儲存
    )
)
echo.

echo ==========================================
echo   安裝完成！
echo ==========================================
echo.
echo 使用方式：
echo   python run_pipeline.py raw/課程/原始.mp4
echo.
pause
