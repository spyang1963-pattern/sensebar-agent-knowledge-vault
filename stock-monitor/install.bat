@echo off
echo ========================================
echo   胚騰 AI 台股融資券分析系統 - 安裝程序
echo ========================================
echo.

echo [1/3] 安裝 Python 套件...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo 安裝失敗！請確認已安裝 Python 3.9+
    echo 下載位置: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo.
echo [2/3] 建立必要目錄...
if not exist "data" mkdir data
if not exist "output\dashboard" mkdir output\dashboard
if not exist "logs" mkdir logs

echo.
echo [3/3] 測試連線...
python -c "import requests; r = requests.get('https://www.twse.com.tw', timeout=10); print('連線成功！' if r.status_code == 200 else '連線失敗')"
if %errorlevel% neq 0 (
    echo.
    echo 連線測試失敗，請檢查網路連線
)

echo.
echo ========================================
echo   安裝完成！
echo ========================================
echo.
echo 接下來請：
echo 1. 編輯 config.yaml 設定你的 LINE Token
echo 2. 執行 python run_stock_analysis.py 測試
echo 3. 執行 setup_scheduler.bat 設定自動排程
echo.
echo 詳細說明請看 README.md
echo.
pause
