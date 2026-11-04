@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

:: ============================================
::  One-click setup for PC1 / PC2 / PC3
::  Usage:
::    setup_new_pc.bat              install
::    setup_new_pc.bat --dry-run    print actions only (no changes)
::  Optional: set PROJECT_DIR=D:\xxx before running
::  NOTE: keep this file ASCII-only. Chinese text in a .bat breaks
::        depending on console codepage (cp950 vs 65001).
::        Docs: workspace-bundle\ONBOARDING.md (Chinese)
:: ============================================

set "DRY="
if /i "%~1"=="--dry-run" set "DRY=1"
if /i "%~1"=="-n" set "DRY=1"

if not defined PROJECT_DIR set "PROJECT_DIR=D:\AI-Agent-Workspace"
set "REPO_URL=https://github.com/spyang1963-pattern/sensebar-agent-knowledge-vault.git"
set "INFRA=%PROJECT_DIR%\workspace-bundle\infra"

echo ==========================================
echo   New PC setup - one click
echo ==========================================
echo   Project dir: %PROJECT_DIR%
if defined DRY echo   [DRY-RUN] nothing will be installed or written
echo.

:: ---------- 1/10 Git ----------
echo [1/10] Git...
where git >nul 2>&1
if errorlevel 1 (
    echo   [INFO] not found, installing with winget...
    if defined DRY (
        echo   [dry] winget install --id Git.Git -e --accept-package-agreements --accept-source-agreements
    ) else (
        winget install --id Git.Git -e --accept-package-agreements --accept-source-agreements
    )
    where git >nul 2>&1
    if errorlevel 1 (
        echo   [ERR] Git still unavailable. Close this window, open a NEW terminal and run again.
        if not defined DRY (pause & exit /b 1)
    )
) else (
    echo   [OK] already installed
)
echo.

:: ---------- 2/10 Python ----------
echo [2/10] Python 3.10+...
python --version >nul 2>&1
if errorlevel 1 (
    echo   [INFO] not found, installing Python 3.12 with winget...
    if defined DRY (
        echo   [dry] winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
    ) else (
        winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
    )
    python --version >nul 2>&1
    if errorlevel 1 (
        echo   [ERR] Python still unavailable. Close this window, open a NEW terminal and run again.
        if not defined DRY (pause & exit /b 1)
    )
) else (
    echo   [OK] already installed
)
if not defined DRY python --version
echo.

:: ---------- 3/10 Repo ----------
echo [3/10] Project directory...
if exist "%PROJECT_DIR%\.git" (
    echo   [INFO] git repo exists, running git pull --ff-only...
    if defined DRY (
        echo   [dry] git -C "%PROJECT_DIR%" pull --ff-only
    ) else (
        git -C "%PROJECT_DIR%" pull --ff-only
    )
) else (
    if exist "%PROJECT_DIR%" (
        echo   [ERR] %PROJECT_DIR% exists but is not a git repo
        echo   Move or rename it first, then run this script again.
        if not defined DRY (pause & exit /b 1)
    ) else (
        echo   [INFO] cloning...
        if defined DRY (
            echo   [dry] git clone "%REPO_URL%" "%PROJECT_DIR%"
        ) else (
            git clone "%REPO_URL%" "%PROJECT_DIR%"
        )
    )
)
if exist "%PROJECT_DIR%" cd /d "%PROJECT_DIR%"
echo.

:: ---------- 4/10 External tools ----------
echo [4/10] External tools (ffmpeg / VLC / Obsidian / Tesseract)...
if exist "%INFRA%\setup\external_tools.ps1" (
    if defined DRY (
        echo   [dry] powershell -ExecutionPolicy Bypass -File "%INFRA%\setup\external_tools.ps1"
    ) else (
        powershell -ExecutionPolicy Bypass -File "%INFRA%\setup\external_tools.ps1"
    )
) else (
    echo   [WARN] external_tools.ps1 not found, skipped - finish step 3 first
)
echo.

:: ---------- 5/10 Python packages ----------
echo [5/10] Python packages (base + task lines)...
if exist "%INFRA%\update.py" (
    if defined DRY (
        echo   [dry] python -X utf8 "%INFRA%\update.py"
    ) else (
        python -X utf8 "%INFRA%\update.py"
    )
) else (
    echo   [WARN] update.py not found, skipped base packages
)
for %%L in (video finance stock) do (
    if exist "%INFRA%\requirements-%%L.txt" (
        if defined DRY (
            echo   [dry] python -m pip install -r "%INFRA%\requirements-%%L.txt"
        ) else (
            echo   [INFO] installing %%L line packages - first run may take a while...
            python -m pip install -r "%INFRA%\requirements-%%L.txt" -q
        )
    )
)
echo.

:: ---------- 6/10 API keys ----------
echo [6/10] API key (Groq, required for transcription)...
if exist "%USERPROFILE%\.groq_api_key" (
    echo   [OK] .groq_api_key already exists
) else (
    if defined DRY (
        echo   [dry] prompt for Groq API key and write %%USERPROFILE%%\.groq_api_key
    ) else (
        echo   Create a free key at https://console.groq.com
        set /p "GROQ_KEY=Paste Groq API key (Enter to skip): "
        if not "!GROQ_KEY!"=="" (
            >"%USERPROFILE%\.groq_api_key" echo !GROQ_KEY!
            echo   [OK] saved
        ) else (
            echo   [WARN] skipped; create %USERPROFILE%\.groq_api_key later
        )
    )
)
echo.

:: ---------- 7/10 GitHub CLI (optional) ----------
echo [7/10] GitHub CLI (optional)...
where gh >nul 2>&1
if errorlevel 1 (
    if defined DRY (
        echo   [dry] winget install --id GitHub.cli -e --accept-package-agreements --accept-source-agreements
    ) else (
        winget install --id GitHub.cli -e --accept-package-agreements --accept-source-agreements
    )
) else (
    echo   [OK] already installed
)
echo.

:: ---------- 8/10 opencode ----------
echo [8/10] opencode...
where opencode >nul 2>&1
if errorlevel 1 (
    echo   [INFO] not installed. See https://opencode.ai - npm i -g opencode-ai or official installer
    echo   [SKIP] not auto-installed - Node versions differ per machine
) else (
    echo   [OK] already installed
)
echo.

:: ---------- 9/10 Git credential ----------
echo [9/10] Git credential (for push)...
if defined DRY (
    echo   [dry] git config --global credential.helper store
) else (
    git config --global credential.helper store
    echo   [OK] credential.helper = store - first push asks for username + GitHub token
)
echo.

:: ---------- 10/10 Health check + machine identity ----------
echo [10/10] Health check and machine identity...
if exist "%INFRA%\health_check.py" (
    if defined DRY (
        echo   [dry] python -X utf8 "%INFRA%\health_check.py"
    ) else (
        python -X utf8 "%INFRA%\health_check.py"
    )
) else (
    echo   [WARN] health_check.py not found
)
if defined DRY (
    echo   [dry] read config.MACHINE / machine role
) else (
    python -X utf8 -c "import sys; sys.path.insert(0, r'%PROJECT_DIR%'); import config; print('  MACHINE =', config.MACHINE, '| ROLE =', config.get_machine_role())"
    python -X utf8 -c "import sys; sys.path.insert(0, r'%PROJECT_DIR%'); import config; sys.exit(0 if not config.MACHINE.startswith('unknown-') else 1)"
    if errorlevel 1 echo   [WARN] hostname not registered; add it to config.py MACHINE_ALIASES (ONBOARDING step 6)
)
echo.

echo ==========================================
echo   Done. Manual steps still required:
echo ==========================================
echo   1. Gemini key : %USERPROFILE%\.gemini_api_key  (per machine, do NOT share)
echo   2. Telegram   : %USERPROFILE%\.telegram_env    (BOT_TOKEN / CHAT_ID, shared)
echo   3. Data sync  : finance.db, knowledge-base\, shared\watched_channels_state.json
echo   4. Schedules  : only ONE writer per task; see ONBOARDING step 8
echo   5. PATH       : open a NEW terminal after installing external tools
echo.
echo   Docs: workspace-bundle\ONBOARDING.md
echo   Plan: workspace-bundle\HANDOFF-3MACHINE-DEPLOY.md
echo.
if not defined DRY pause
endlocal
