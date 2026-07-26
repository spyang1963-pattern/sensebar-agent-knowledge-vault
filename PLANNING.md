# 知識庫建立規劃文件

## 願景

```
三師爸的 AI Agent 知識 → 學會如何與 AI 協作
          +
股市技術分析知識 → 驗證穩定策略 → AI 協助交易
          ↓
    有用的知識 → 寫成報告 → 分享
```

## 設備分工

```
[Notebook] 大腦：規劃 + 分配 + 整理 + 報告
     │
     ├── [PC1] 重體力活：Whisper 辨識、影片處理
     │
     └── [PC2] 備援 / 平行處理
```

### 設備狀態

| 設備 | 狀態 | 用途 | AnyDesk ID |
|------|------|------|------------|
| Notebook | ✅ 完成 | 規劃、分配、整理、報告（保持彈性，可移動） | - |
| PC1 | ✅ 環境 + 任務腳本 | Whisper 辨識、影片處理（24hr 待命） | 1663025808 |
| PC2 | ✅ 環境 + 任務腳本 | 備援 / 平行處理（24hr 待命） | 301180560 |

### PC1 環境

- 位置：可透過 AnyDesk 遠端控制
- AnyDesk ID：1663025808（已設定無人值守存取）
- 已安裝：Python 3.12.10、ffmpeg 8.1.2、Git、opencode、VLC
- Groq API Key：已設定
- 任務腳本：`D:\AI Agent\process_tasks_pc.py`（需連線到 Notebook 共享讀取影片）

### PC2 環境

- AnyDesk ID：301180560（建議勾選「下次自動登入」）
- 已安裝：Python 3.14.6、ffmpeg 8.1.2、groq 套件
- Groq API Key：已設定（與 Notebook 同一組）
- 任務腳本：`D:\AI Agent\process_tasks_pc.py`（需連線到 Notebook 共享讀取影片）
- 專案目錄：`D:\AI Agent`（已從 Notebook 複製，29.41 GB）

## 知識庫架構

```
knowledge-base/
├── ai-agent/                         ← 三師爸 AI Agent（已有 SRT）
│   ├── AI-Agent基本功/               ← EP01-EP05
│   ├── Claude基本功/                 ← EP01-EP13
│   ├── AntiGravity基本功/            ← EP01-EP08
│   ├── GoogleAI基本功/               ← EP01-EP06
│   ├── GPT-Codex基本功/              ← EP01-EP05
│   ├── OpenCode基本功/               ← EP02-EP05
│   └── 其他/
│
├── trading/                          ← 技術分析（按老師分）
│   ├── 察爾思/                       ← 最優先
│   ├── 廖崧沂/
│   ├── 奧丁-理周學院/
│   ├── 奧丁-獨立/
│   ├── 海龍王/
│   ├── 黃韋中/
│   ├── 陳霖/
│   ├── 黃毅夫/
│   ├── 林教授/
│   ├── 陳韋翰/
│   ├── 亮晶晶/
│   └── 不預測漲跌/
│
└── others/                           ← 其他探索
```

## 影片 Inventory

### 三師爸 AI Agent（已有 SRT）

| 系列 | 集數 | 狀態 |
|------|------|------|
| AI-Agent基本功 | EP01-EP05 | ✅ 已有 SRT |
| Claude基本功 | EP01-EP13 | ✅ 已有 SRT |
| AntiGravity基本功 | EP01-EP08 | ✅ 已有 SRT |
| GoogleAI基本功 | EP01-EP06 | ✅ 已有 SRT |
| GPT-Codex基本功 | EP01-EP05 | ✅ 已有 SRT |
| OpenCode基本功 | EP02-EP05 | ✅ 已有 SRT |
| 其他獨立影片 | ~10 部 | ✅ 已有 SRT |

### 技術分析（待處理）

| 老師 | 來源路徑 | 影片數 | 大小 | 優先順序 |
|------|----------|--------|------|----------|
| 察爾思 | D:\!!!!!理周學院老師\察爾思 | 340 | - | ⭐ 1 |
| 廖崧沂 | D:\!!!!!理周學院老師\廖崧沂 | 200 | - | ⭐ 2 |
| 奧丁 | D:\!!!!!理周學院老師\奧丁 | 131 | - | ⭐ 3 |
| 奧丁 | D:\!!奧丁(有字幕) | 110 | 30 GB | ⭐ 4 |
| 海龍王 | D:\!!海龍王線上教學錄影(有字幕) | 252 | 78 GB | ⭐ 5 |
| 黃韋中 | D:\!!黃韋中老師-潮汐推論與均線操作 | 326 | 53 GB | ⭐ 6 |
| 陳霖 | D:\!陳霖-期指操盤(有字幕) | 8 | 6 GB | ⭐ 7 |
| 黃毅夫 | D:\!!!!!理周學院老師\黃毅夫 | 152 | 91 GB | ⭐ 8 |
| 林教授 | D:\!!!!!理周學院老師\林教授 | 29 | 30 GB | ⭐ 9 |
| 陳韋翰 | D:\!!!!!理周學院老師\陳韋翰 | 38 | 7 GB | ⭐ 10 |
| 亮晶晶 | D:\!!!!!理周學院老師\亮晶晶 | 9 | 9 GB | ⭐ 11 |
| !不預測漲跌 | D:\!!!!!理周學院老師\!不預測漲跌 | 174 | 12 GB | ⭐ 12 |
| **合計** | | **~1,769** | **~316 GB** | |

## 工作流

### 影片處理流程

```
原始影片 + 剪映逐字稿(.txt)
       ↓
  [PC1/PC2] Whisper 辨識（Groq API）→ 產生 SRT
       ↓
  [PC1/PC2] 術語校正（apply_vocab）→ 知識庫 SRT
       ↓
  [Notebook] 轉成 .md 格式 → 放入知識庫對應目錄（Obsidian 可讀）
       ↓
  [Notebook] 消化知識、建立關聯、寫報告
```

### 重要：檔案格式

- **SRT**：時間碼字幕檔（用於搜尋跳轉）
- **MD**：逐字稿內容（Obsidian 顯示用）
- **每個影片需要兩個檔**：.srt + .md

### 注意事項

1. **有字幕的影片**：標示「有字幕」表示剪映已燒入影片，需重新用 Whisper 辨識
2. **剪映 .txt**：可作為參考，但精度不夠，需用 Whisper 重新辨識
3. **術語校正**：技術分析有大量專業術語，需建立 vocabulary.md
4. **時間碼**：Whisper 可產生 word-level 時間碼，方便搜尋跳轉

### 處理時間估算

- 每部影片 Whisper 辨識：~5-10 分鐘（依長度）
- 術語校正：~1 分鐘/部
- 整理分類：~2 分鐘/部
- **1,769 部 × 10 分鐘 ≈ 295 小時 ≈ 12 天（24小時不間斷）**
- 實際每天處理 8 小時 ≈ 37 天

## 優先處理項目

### 第一批：察爾思 程式入門

- 路徑：D:\!!!!!理周學院老師\察爾思\8.程式入門：從基礎到策略應用
- 數量：10 部影片
- 特點：有剪映 .txt 逐字稿，可作為參考
- 目標：建立完整的工作流範例，驗證流程 OK 後再批量處理

### 第一批完成後

- 檢查 SRT 品質
- 確認術語校正效果
- 建立 vocabulary.md（技術分析術語）
- 確認工作流 OK 後，批量處理其他老師

## XQ 整合（待規劃）

- 目標：在 XQ 系統建立模擬測試
- 驗證技術分析方法和結果
- 待知識庫建立後，再規劃整合方案

## 已知問題與排除

### PC 設定相關

#### npm 找不到

**問題**：新 PC 執行 `npm install -g opencode` 報錯「無法辨識 npm」。

**原因**：Node.js 未安裝。

**解法**：
```powershell
winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
```
重開終端後再執行 npm 指令。

#### npm 套件名稱錯誤

**問題**：`npm install -g opencode` 報 404 Not Found。

**原因**：套件名稱是 `opencode-ai`，不是 `opencode`。

**解法**：
```powershell
npm install -g opencode-ai
```

#### PowerShell 執行原則擋住 npm

**問題**：npm.ps1 報錯「系統上已停用指令碼執行」。

**解法**：
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```
輸入 `Y` 確認後再執行 npm。

#### AnyDesk 網站 404/403

**問題**：anydesk.com/en/download 返回 404。

**解法**：用直接下載連結：
```powershell
Invoke-WebRequest -Uri "https://download.anydesk.com/AnyDesk.exe" -OutFile "$env:USERPROFILE\Downloads\AnyDesk.exe"
```
或從 Uptodown 下載（但較小，可能只是安裝器）。

### PowerShell 編碼問題

**問題**：中文路徑在 PowerShell 輸出顯示為亂碼。

**影響**：不影響實際操作，但 readability 差。

**解法**：使用完整路徑字串，或用 `Get-ChildItem` 搭配 `Select-Object` 過濾。

### Obsidian 看不到文稿

**問題**：knowledge-base/trading/ 裡的檔案，Obsidian 無法顯示。

**原因**：Obsidian 預設只顯示 .md 檔案。trading/ 裡只有 .srt 和 .txt，沒有 .md。

**解法**：將逐字稿轉成 .md 格式，格式如下：

```markdown
# 影片標題

- 來源：本地影片
- 老師：老師名稱
- 系列：系列名稱

---

逐字稿內容...
```

**注意**：Clipping/ 裡的 .md 檔案格式有 YouTube 連結，本地影片改用「來源：本地影片」。

### Clipping 與 knowledge-base 格式不同

**問題**：Clipping/ 裡的 .md 有 YouTube 連結，但 trading/ 裡的本地影片沒有。

**解法**：本地影片的 .md 格式改用：
```markdown
- 來源：本地影片
- 老師：老師名稱
- 系列：系列名稱
```
不用 YouTube 連結。

### smart-cut 在筆電上超時

**問題**：2 小時影片跑 smart-cut 超過 10 分鐘仍無結果。

**原因**：筆電 CPU/RAM 不足，smart-cut 需要大量資源。

**解法**：在 PC1/PC2 上執行，或跳過 smart-cut 直接用 Whisper 辨識完整影片。

---

## 重要經驗與工作原則（Session 2026-07-14/15 記錄）

### 1. 設備分工原則

```
Notebook = 大腦（規劃、監控、後製）→ 保持彈性，可隨時移動/關機
PC1/PC2 = 雙腳（24hr 待命執行）→ 獨立運作，不依賴 Notebook
```

**重要**：規劃長任務時，必須考慮 Notebook 可能關機/移動。PC1/PC2 應具備獨立執行能力。

### 2. 自動化原則

**問題**：使用者不應手動切換畫面、貼指令來串接工作。

**原則**：
- 所有任務應設計成**一鍵執行**（如 `python process_tasks_pc.py --pc2`）
- 腳本應自動處理：壓縮 → 上傳 → 轉錄 → 後製 → 存檔
- 使用者只需：開機 → 執行指令 → 等結果

### 3. Context 管理原則

**問題**：長 session 的 context 空間會耗盡，影響效率。

**原則**：
- 當 context 使用超過 **70%**，應主動告知使用者開新 session
- 新 session 應能從 PLANNING.md 和 task_list.json 接續
- **不要讓使用者來提醒**，AI 應主動監控並告知

### 4. 記錄與避錯原則

**問題**：每次遇到問題解決後，應記錄下來，避免後續重蹈覆轍。

**原則**：
- 所有問題和解法都要記錄到 PLANNING.md
- 新 session 開始時，應先讀取 PLANNING.md 了解已知問題
- **不要讓使用者來提醒**，AI 應主動查閱已知問題

### 5. 任務分配設計

**問題**：PC1/PC2 需要從 Notebook 讀取原始影片，但 Notebook 可能關機。

**解決方案**：
- 方案 A：把原始影片複製到 PC1/PC2 本機（需要額外硬碟空間）
- 方案 B：等 Notebook 開著時再跑任務（使用者需配合）
- **建議**：長期應採方案 A，讓 PC1/PC2 完全獨立

### 6. 進度追蹤

**已完成**（106 部）：
- 1.中短線選股班：12/17
- 2.攻擊波之波段操作班：19/38
- 3.籌碼動能班：10/15
- 4.選擇權：55/139（含 28 部進階班補充影片）

**待處理**（254 部）：
- PC1 任務：33 部（中短線選股班、籌碼動能班、複訓班、程式入門）
- PC2 任務：55 部（攻擊波、台指期1分K、台指期15分K）
- Notebook 任務：166 部（選擇權、ETF、交易系統等）

**任務清單**：`task_list.json`（已建立，含 PC1/PC2/Notebook 分配）

### 7. Groq API 24MB 限制

**問題**：Groq Whisper API 有 24MB 檔案大小限制。

**解法**：大於 24MB 的音檔需先用 ffmpeg 壓縮到 16kbps：
```powershell
ffmpeg -i input.mp4 -vn -acodec libmp3lame -ab 16k -ac 1 -ar 16000 output.mp3 -y
```

**注意**：壓縮後若仍超過 24MB，需降到 8kbps 或分割檔案。

---

## 待辦清單

### 高優先

- [ ] 設定 PC2 環境
- [ ] 處理察爾思 程式入門 第一部影片（建立工作流範例）
- [ ] 建立技術分析 vocabulary.md
- [ ] 整理三師爸 ai-agent 知識庫分類

### 中優先

- [ ] 批量處理察爾思所有影片
- [ ] 處理廖崧沂影片
- [ ] 處理奧丁影片

### 低優先

- [ ] 處理其他老師影片
- [ ] XQ 整合規劃
- [ ] 建立報告模板

## 檔案結構

```
專案根目錄/
├── PLANNING.md              ← 本規劃文件
├── run_pipeline.py          ← 一鍵執行完整流程
├── setup.bat                ← 新 PC 一鍵安裝
├── opencode.json            ← opencode 設定
├── AGENTS.md                ← agent 說明文件
├── .opencode/skills/        ← 技能模組
│   ├── smart-cut/           ← 智能剪輯
│   ├── audio-to-srt/        ← 語音轉字幕
│   └── cover-image/         ← 封面生成
├── knowledge-base/          ← 知識庫
│   ├── ai-agent/            ← 三師爸 AI Agent 知識
│   ├── trading/             ← 技術分析
│   └── others/              ← 其他探索
├── raw/                     ← 原始影片（放入此處）
├── working/                 ← 暫存工作檔
└── output/                  ← 最終輸出
```
