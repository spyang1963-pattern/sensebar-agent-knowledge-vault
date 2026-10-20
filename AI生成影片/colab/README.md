# Colab Batch Asset Factory (P5-5)

用途：把耗時的「生圖」「B-roll 抓取」「批次重製」工作丟到免費 Google Colab（T4）執行。本機只負責排程與收成。

## 1. 設計原則
- **彈性擴充**：以 `task_type` 為擴充點，新增 handler 即可
- **最小耦合**：任務透過 JSON 檔案交換（`working/_colab_tasks/*.json`）
- **可收成**：Colab 將產出打包成 `.zip`，手動下載到 `working/_colab_inbox/` 後由 harvester 解壓至 `working/_colab_out/`
- **保留彈性**：不強制綁定特定模型，日後可自由替換

## 2. 目錄結構

```text
AI生成影片/
├── colab/
│   ├── README.md              # 本說明文件
│   ├── requirements-colab.txt # Colab 所需套件
│   ├── worker.ipynb           # Colab Notebook（建議直接複製到 Colab 使用）
│   └── worker.py              # Colab 純 Python 執行腳本
│
└── engine/workers/
    ├── __init__.py
    ├── colab_dispatch.py      # 本機：建立/列出 Colab 任務
    └── colab_harvest.py       # 本機：收成 Colab 輸出 zip
```

## 3. 工作資料夾

執行時會自動建立以下目錄（位於 `AI生成影片/working/`）：

| 目錄 | 說明 |
|---|---|
| `working/_colab_tasks/` | 本機建立的任務 JSON（Colab 會讀取） |
| `working/_colab_inbox/` | Colab 產出 zip 請放在此處（手動下載） |
| `working/_colab_out/` | Harvester 自動解壓至此，依 `task_id` 分資料夾 |

## 4. 任務格式

`working/_colab_tasks/<task_id>.json`：

```json
{
  "id": "t-20261020-001",
  "type": "image_gen",
  "status": "queued",
  "priority": 1,
  "params": {
    "prompt": "minimal interior design, warm light",
    "count": 2,
    "w": 1080,
    "h": 1920
  },
  "outputs": {
    "dir": "colab_out/t-20261020-001"
  },
  "created_at": "2026-10-20T15:00:00+08:00",
  "updated_at": "2026-10-20T15:00:00+08:00"
}
```

### task_type（預定支援）
| 類型 | 用途 |
|---|---|
| `image_gen` | 批次 AI 生圖 |
| `video_broll_fetch` | 批次抓取 Pixabay/Pexels B-roll（沿用 providers 邏輯） |
| `batch_rebuild` | 批次重製已存在的素材/腳本 |

## 5. Colab 使用流程

### 方法 A：使用 `worker.ipynb`
1. 到 [Google Colab](https://colab.research.google.com/) 建立新 Notebook
2. 複製 `colab/worker.ipynb` 的內容貼入（或直接上傳該檔案）
3. 在 Colab 執行儲存格，依提示上傳 `tasks.zip`（可由 `colab_dispatch.py` 產生）
4. 執行完成後下載 `outputs-<task_id>.zip`，放到本機 `working/_colab_inbox/`

### 方法 B：使用 `worker.py`
1. 在 Colab 的儲存格執行 `!wget <worker.py URL>` 或上傳檔案
2. 執行 `python worker.py`

## 6. 本機操作

### 建立任務
```powershell
python engine/workers/colab_dispatch.py --type image_gen --prompt "interior warm" --count 4
```

### 收成輸出
```powershell
python engine/workers/colab_harvest.py
```

## 7. 擴充方式
新增 `task_type` 時，只需在 `colab/worker.py` 補一個對應的 handler 函式即可，不需修改現有架構。此設計旨在**盡量保留彈性，以便於擴充資源**。
