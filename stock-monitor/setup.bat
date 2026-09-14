@echo off
chcp 65001 >nul
echo ============================================
echo   台股融資券分析看板 - 一鍵安裝
echo ============================================
echo.

echo [1/3] 安裝 Python 套件...
pip install requests beautifulsoup4 pandas pyyaml
if %errorlevel% neq 0 (
    echo 安裝失敗，請確認 Python 已安裝
    pause
    exit /b 1
)

echo.
echo [2/3] 建立目錄...
if not exist output\dashboard mkdir output\dashboard
if not exist data mkdir data

echo.
echo [3/3] 測試資料抓取...
python run_stock_analysis.py

echo.
echo ============================================
echo   安裝完成！
echo ============================================
echo.
echo 使用方式：
echo   python run_stock_analysis.py
echo.
echo 設定檔位置：config.yaml
echo   - 調整分析門檻
echo   - 設定 LINE / Email 通知
echo.
pause
