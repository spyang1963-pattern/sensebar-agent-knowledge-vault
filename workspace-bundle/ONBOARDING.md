# 機器佈署／接手手冊（Onboarding & Takeover Runbook）

> 目標：任何新機器或接手機（PC1/PC2/新電腦）能在最短時間內，達成與現役機一致的完整能力。
> 原則：能腳本化的全部腳本化；只有「金鑰、資料同步、GitHub 認證」三項必須人工。
> 本手冊由 2026-08 PC3 實際佈署過程固化而來。

## 架構角色

| 角色 | 職責 | 現役 |
|---|---|---|
| harvester | 金融收集/分析/報告/發佈＋頻道監控→逐字稿→KB | PC3 |
| 開發/管理站 | 改程式、git push、agent session | Notebook |
| collector | 純新聞收集（無分析，Python 3.8 限制） | NAS（角色待定） |

單一寫入者原則：同一種排程任務全時間只能有一台機器在跑，切換時先停舊再啟新。

## 第 1 步：取得程式碼

```powershell
git clone https://github.com/spyang1963-pattern/sensebar-agent-knowledge-vault.git D:\sensebar-agent-knowledge-vault
```
（已 clone 過則 `git pull`。之後所有路徑以 `<REPO>` 代表 repo 根目錄）

## 第 2 步：Python 套件一鍵安裝

```powershell
$env:WORKSPACE_ROOT = "<REPO>"
python <REPO>\workspace-bundle\infra\update.py
```
（安裝 requirements-base.txt：requests/PyYAML/feedparser/watchdog/paramiko/groq/pymupdf/python-pptx/python-docx/pillow/openpyxl/markitdown/reportlab/matplotlib/qrcode/youtube-transcript-api/yt-dlp 等）

金融/KB 管線額外需要（部分已含於 base）：
```powershell
python -m pip install google-genai markdown yt-dlp pyyaml
```

## 第 3 步：外部工具一鍵安裝

```powershell
powershell -ExecutionPolicy Bypass -File <REPO>\workspace-bundle\infra\setup\external_tools.ps1
```
安裝 ffmpeg、VLC、Obsidian。**裝完必須重開終端**讓 PATH 生效。

## 第 4 步：API Keys（人工，位置固定）

| Key | 位置 | 策略 |
|---|---|---|
| Gemini | `C:\Users\<user>\.gemini_api_key` | **每台獨立**（Google AI Studio 另建專案，各自 500 次/天/模型額度池，避免互搶） |
| Groq | `C:\Users\<user>\.groq_api_key` | 共用（轉錄用量低） |

## 第 5 步：資料同步（人工，AnyDesk，來源＝現役主力機）

| 資料 | 來源路徑 | 備註 |
|---|---|---|
| 金融 DB | `<REPO>\financial_news\finance.db` | 主力機為準 |
| KB 影音庫 | `<REPO>\knowledge-base\`（含 kb_query.py 等散檔） | 跳過接收端已有的衝突項 |
| 頻道狀態檔 | `<REPO>\shared\watched_channels_state.json` | **必須最新版**——過期會把舊影片當新片重抓重轉 |

## 第 6 步：註冊機器身份

`<REPO>\config.py`：
- `MACHINE_ALIASES` 加 `"hostname小寫": "pcN"`
- `MACHINE_PATHS` 加該機路徑
- `MACHINE_ROLES` 加角色

改完 commit + push（所有機器同步這份設定）。驗證：
```powershell
python -X utf8 -c "import sys; sys.path.insert(0, r'<REPO>'); import config; print(config.MACHINE, config.get_machine_role())"
```

## 第 7 步：環境健檢

```powershell
python <REPO>\workspace-bundle\infra\health_check.py
```

## 第 8 步：排程（切換日才啟用！）

| 任務名稱 | 觸發 | 指令 |
|---|---|---|
| FinanceNews_<機>_Pipeline | 每 30 分 | `python pipeline.py --full --batch 150 --time-budget 480` |
| FinanceNews_<機>_MorningReport | 每天 07:00 | `python pipeline.py --report --deep --slot morning` |
| FinanceNews_<機>_EveningReport | 每天 19:00 | `python pipeline.py --report --deep --slot evening` |
| ChannelWatcherDaily | 每天 22:00 | `python channel_watcher.py --once` |

**切換日順序**：
1. 同步最新 watched_channels_state.json → 新機
2. 舊機：停用上述同名任務
3. 新機：建立並啟用任務
4. 若涉及報告發佈：先確認新機 `publisher\repo\` 的 remote 指向 `financial-reports.git`（誤指主 repo 會污染程式庫；不確定就刪掉 `publisher\repo\` 讓 build.py 重建）
5. 觀察一天確認正常後，舊機任務可刪除

## 已知陷阱（踩過的坑）

1. **多 Python／舊 shell PATH 假象**：套件裝了但 import 失敗 → 重開終端再驗證
2. **watched_channels_state.json 過期** → 歷史影片全被重下載重轉錄，燒 Groq 額度
3. **publisher repo remote 指錯** → push 會污染主 vault repo
4. **run_pipeline.py 寫死 VLC 路徑** `C:\Program Files\VideoLAN\VLC\vlc.exe` → VLC 必裝預設路徑
5. **Gemini 免費層額度**：每專案每日 500 次/模型，台灣時間約 15:00 重置；分析積壓事件會快速燒完
6. **NAS Python 3.8** 裝不了 google-genai → 只能純收集
