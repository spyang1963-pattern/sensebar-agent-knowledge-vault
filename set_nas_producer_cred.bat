@echo off
chcp 65001 >nul
setlocal
title NAS producer 認證設定（PC1 / PC2 / PC3 用）
echo ============================================================
echo  在「產出機」（PC1/PC2/PC3）執行一次即可。
echo  用途：讓 publish_outbox.py 能把包推到 NAS 的 exchange。
echo  （notebook 不要跑這支，notebook 用的是 harvest 帳號）
echo ============================================================
echo.

set /p NASIP=NAS IP [直接 Enter = 192.168.1.121]:
if "%NASIP%"=="" set NASIP=192.168.1.121

set /p NP=請貼上 producer 密碼（在 notebook 的 %%USERPROFILE%%\.nas_accounts.json）:
if "%NP%"=="" (
  echo 沒輸入密碼，結束。
  pause
  exit /b 1
)

echo.
echo [1/3] 寫入 Windows 認證管理員（重開機仍有效）
cmdkey /add:%NASIP% /user:producer /pass:%NP%

echo.
echo [2/3] 清掉舊的 SMB session，避免沿用別的身份
net use \\%NASIP%\exchange /delete /y >nul 2>&1
net use \\%NASIP%\backup   /delete /y >nul 2>&1
net use \\%NASIP%\archive  /delete /y >nul 2>&1

echo.
echo [3/3] 驗證：讀 exchange、寫自己那格 outbox
net use \\%NASIP%\exchange /user:producer %NP% >nul 2>&1
dir \\%NASIP%\exchange
set MACHINE=%COMPUTERNAME%
echo.
echo 提示：exchange 底下應有 pc1 / pc2 / pc3 三個資料夾。
echo       本機是 %MACHINE%，publish_outbox.py 會寫入 exchange\%MACHINE%\outbox。
echo.
echo 若下一步要測寫入，請先確認你那一格存在（不存在就請 agent 建）。
echo 完成後可以關閉這個視窗。
echo.
pause
endlocal
