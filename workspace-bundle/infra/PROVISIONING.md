# 任務環境建置盤點（Provisioning Inventory）

> 範圍：三條任務線（finance / video / stock）＋五項共同能力（視覺、生圖、通知、LLM 連線、GitHub 發佈）＋基礎（Tailscale 連線、外部工具）。
> 依據：2026-09 對 `D:\AI-Agent-Workspace` 全部 `.py` import 掃描＋既有 `workspace-bundle` 檔案實地核對。
> 角色（2026-09-20 更新）：**每台機器各自具備執行「全部現有任務」的能力，非分工管線**——PC1/PC2/PC3/Notebook 皆為完整副本，任一台可獨立承接 finance / video / stock / XQ。多台共存＝容錯備援＋彈性（可同時跑不同任務）；受「單一寫入者」約束（同排程同時僅一台在跑，切換先停舊再啟新）。Notebook＝套件集中區／開發樣板。

## 一、三條任務線 ─ 各自需求

| 項目 | Finance 線 | Video 線（三機） | Stock 線 |
|---|---|---|---|
| 入口目錄 | `financial_news/` | root（`channel_watcher.py`、`extract_videos.py`、`download_all_subs.py`、`file_processors.py`、`process_tasks_pc_v4.py`、`scheduler.py`、`watchdog.py`） | `stock-monitor/` |
| Python | 3.10+（collect 也可 3.8，但 analyze/報告需 3.10+） | 3.10+ | 3.10+ |
| 關鍵外部工具 | git（publisher push）、（選）Edge/Python http.server 待 dashboard | git、**ffmpeg**（yt-dlp 合併）、**VLC**（燒字幕，寫死 `C:\Program Files\VideoLAN\VLC\vlc.exe`）、**tesseract**（OCR，`file_processors.py: pytesseract`） | git、python |
| Python 套件 | google-genai、groq、feedparser、requests、PyYAML、markdown、python-docx、pywin32、flask、（base 皆含） | yt-dlp、openai-whisper、groq、requests、PyYAML、watchdog、plyer、psutil、PIL、beautifulsoup4、pymupdf、pypdf、pytesseract、python-docx、google-genai、auto-editor、openai、python-dotenv | requests、pandas、PyYAML、beautifulsoup4 |
| Key / 設定 | `~/.gemini_api_key`（每個案獨立）、`~/.groq_api_key`、`~/.telegram_env`（BOT_TOKEN/CHAT_ID）、（選）`~/.openrouter_api_key` | `~/.groq_api_key`（轉錄）、`~/.gemini_api_key`（摘要/整理）、`notify_config.yaml`（LINE/Email） | `stock-monitor/config.yaml`（email/webhook/LINE 通知） |
| 資料檔 | `finance.db`（app 唯一真源）、`publisher/repo/` | `shared/watched_channels_state.json`、`knowledge-base/`、`videos/`、`raw/`、`output/`、`working/` | `output/cache/`（法人/融資券/K線，.gitignore） |
| 排程 | `FinanceNews_<機>_Pipeline`（30min）、Morning（07:00）、Evening（19:00）、（PC3）`Autonomy_finance-*`、`Autonomy_Guard` | `ChannelWatcherDaily`（22:00）、三機 `sync_shared`（5min）、worker/supervisor | `StockMonitor_Fetch`（21:30）、自選股/GUI 排程 |
| 驗證命令 | `python pipeline.py --report --no-push`、`publisher/build.py` | `python worker.py --test`、`python channel_watcher.py --once` | `python run_stock_analysis.py --fetch-only --no-notify` |

## 二、共同能力（Cross-cutting capabilities）

### 1. 視覺能力（Vision Sidecar）
- 目的：讓純文字模型讀 PNG/PDF/PPTX/DOCX → Markdown（`infra/skills/image-vision-sidecar/vision.py`）
- 套件：groq、pymupdf、python-pptx、python-docx、pillow（= `skills/image-vision-sidecar/requirements.txt`）
- Key：Groq（`~/.groq_api_key`，模型 `qwen/qwen3.6-27b`）
- 現況：requirements.txt 齊；health_check 已檢查

### 2. 生圖能力（Draw Free）
- 目的：免費 AI 生圖＋中文對話框疊字（`infra/skills/draw-free/draw_free.py`、`overlay-text.py`）
- 套件：pillow（draw_free 用 urllib，無需 key）
- 現況：**無 requirements.txt**、health_check 已檢查

### 3. 通知能力
| 通道 | 位置 | 需要 | 運用 |
|---|---|---|---|
| Telegram | `financial_news/notifier.py` read `~/.telegram_env`（或 env） | `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID` | 排程停擺/資料停滯告警 |
| LINE＋Email | root `watchdog.py`（`notify_line_and_email`）串 `notify_config.yaml` | LINE_TOKEN、email SMTP 設定 | 三機任務狀態通知 |
| 桌面通知 | `plyer` | 套件 | worker 任務完成/錯誤 |

### 4. LLM 連線能力
| Provider | Key 位置 | 用途 | 策略 |
|---|---|---|---|
| Gemini | `~/.gemini_api_key` / env `GEMINI_API_KEY` | finance analyze＋verify 主模型、deep_report、影片摘要 | **每台獨立**（500 次/日/專案；analyze 現走 multi-provider） |
| Groq | `~/.groq_api_key` / env `GROQ_API_KEY` | 轉錄 whisper、verify 第二意見、vision sidecar | 共用 |
| OpenRouter | `~/.openrouter_api_key`（選） | finance analyze 第三 provider | 共用（沒 key 自動跳過） |

### 5. GitHub Pages 發佈能力
- 工具：git（credential store / gh CLI）、`financial_news/publisher/build.py`＋`deploy.py`
- 陷阱：`publisher/repo/` remote 必須指 `financial-reports.git`（誤指主 repo 會污染）；deploy 採 fetch→reset→clean→copy→push 防衝突
- repo：`spyang1963-pattern/financial-reports`（daily/deep）、`xq-dashboard`（儀表板）

### 6. 機器互連（Tailscale）
- 三機&PC3 以 Tailscale 互通；`setup_*.bat` 檢查；IPC 走 `shared/` 目錄
- 陷阱：Notebook 開啟「檔案共用」讓 PC1/PC2 可取 `\\100.111.44.63\AI-Agent-Workspace`

## 二之一、XQ 盤中儀表板＋XQ-AI神隊友線（`XQ-AI神隊友/`）

> 特點：這條線**不能純腳本佈署**——快照來源是「已登入的 XQ 軟體＋開著的 Excel 報價表（DDE）」。環境 = XQ 主機＋Excel COM 管線＋能跑 financial_news 的 Python 環境。

| 項目 | 內容 |
|---|---|
| 執行主機 | PC3（`D:\sensebar-agent-knowledge-vault\XQ-AI神隊友\`，git 從大倉 pull） |
| 人工前置（不可自動） | **XQ 已登入**（`輸出欄位→DDE` 把報價表貼進 Excel、不存檔）＋**Excel 開著**＋PC 不休眠＋權限表 |
| 快照 | `xq_snapshot_loop.bat`（排程 09:15–13:30 每 15 分）→ `routines\snapshot.ps1 -Kind rank/breadth/notes`（**PowerShell COM，需 `-STA`**，讀開著的 Excel 報價表分塊抓→存 `routines\snapshots\*.csv`，stale 去重） |
| 渲染＋發佈 | `routines\render_html.py --dashboard`（python，參考 `snapshots\`）→ `publisher\deploy.py`（git push **xq-dashboard repo**，Pages） |
| 盤後綜合分析 | `xq_postmarket_loop.bat`（22:00 evening／06:30 morning）→ `postmarket_prep.py`（**import financial_news 的 `db`/`calendar_engine`/`market_data`→ 依賴 finance.db**）→ `postmarket_report.py`（**google-genai/Gemini** 產明日預測）→ render→deploy |
| 稽核 | `predict_audit.py`（讀 snapshots＋收盤比對方向命中） |
| Python 套件 | 主要= **google-genai**；其餘靠 financial_news 環境（sqlite3/requests/feedparser/PyYAML/csv） |
| 外部工具 | Microsooft **Excel**（COM）＋**XQ 看盤軟體**；git |
| Key | `~/.gemini_api_key`（postmarket_report 分析） |
| 排程 | `XQ_Snapshot_Loop2`（09:15 起 15min，唯一啟動）、`XQ_Postmarket_Evening`（週日~四 22:00）、`XQ_Postmarket_Morning`（週一~五 06:30）；`setup_pc3_xq_all.ps1`（一般權限）一次註冊 |
| AI神隊友 VBA 工具 | `TextPrefixSuffix_Tool.xlsm`＋`splice_caption*.ps1`/`build_*.ps1`（Excel VBA 字幕/命名工具，非儀表板核心） |

## 三、需求矩陣 → 目前覆蓋缺口（Gap）

| 需求 | 現有自動化 | 缺口 |
|---|---|---|
| 基礎套件（財務+影片交集） | `infra/requirements-base.txt` | **缺 google-genai、markdown、pandas、beautifulsoup4、psutil、flask、pytesseract** |
| Finance 專屬 | ONBOARDING 第 2 步手動補 `google-genai markdown yt-dlp pyyaml` | **缺 pywin32**（deep_report win32com）；未訂成檔案 |
| Video 專屬 | `setup_pc.bat`（whisper/yt-dlp/requests/pyyaml/plyer/watchdog）＋`setup_new_pc.bat` | **缺 pandas、bs4**（HANDOFF:130 已知）；未併入 bundle；whisper 大小、auto-editor/openai/dotenv 在另一腳本 |
| Stock 專屬 | `stock-monitor/requirements.txt`（requests/pandas/pyyaml） | bs4 未列入（實際 PC3 有手動裝） |
| 外部工具 | `external_tools.ps1`（ffmpeg/VLC/Obsidian） | **缺 tesseract**（OCR 用）；yt-dlp 走 pip |
| Key 盤點 | ONBOARDING 表 | Telegram/OpenRouter 未列入表格 |
| 建置驗證 | `health_check.py` | **缺 finance 線檢查**（db/publisher/gemini key）、**缺 video 線檢查**（whisper/tesseract/auto-editor）、排程清單過時（只 2 個） |
| XQ 線前置 | 無（人工 SOP） | health_check 可加 `Get-Process EXCEL`＋`snapshots\` 新鮮度檢查；ONBOARDING 無 XQ 段（XQ 登入＋DDE 貼表不可自動，需寫成人工作業卡）；確認 `render_html.py --dashboard` 可 import financial_news 模組 |

## 四、既定原則
1. 能腳本化全腳本化；只有「金鑰、資料同步、GitHub 認證」人工（ONBOARDING 原則）。
2. 金鑰策略：Gemini 每台獨立、Groq/OpenRouter/Telegram 共用。
3. 單一寫入者：同一排程全時間一台在跑，切換先停舊再啟新。
4. 一鍵的收尾＝自動健檢：`health_check.py` 對應任務線回報缺項，不是「保證裝好」，是「保證驗得到」。