# Step 7 — 單向收割架構（設計稿）

> 狀態：**設計完成、尚未實作**（2026-11-05）
> 動手時機：PC3 遷移完成後（PC3 是第三個產出機，收割器要先能吃三台）
> 相關：`HANDOFF-3MACHINE-DEPLOY.md` Step 7

---

## 1. 為什麼要收割，而不是同步

三機各自是完整副本，但**不該互相同步整份資料**：

| 資料 | 大小 | 該不該跨機同步 |
|---|---|---|
| 程式碼 | 小 | ✅ git（已做） |
| `knowledge-base/` | 124 MB，且每天長大 | ❌ 只有 notebook 是正本 |
| `finance.db` | 57 MB，SQLite 單檔 | ❌ 只有跑金融線的機器需要 |
| 影片 `D:\YouTube_Videos` | 數十 GB | ❌ 留在產出機，KB 只寫指標 |
| `shared/`（派工） | 小 | ⚠️ 仍需共用，見 §7 |

結論：**只有「文字產出」往 notebook 流**，其他都留在產出機。

---

## 2. 傳輸方式：notebook 主動 pull（UNC 唯讀）

```
PC1/PC2/PC3                     notebook
D:\AI-Agent-Workspace\          D:\AI-Agent-Workspace\
  shared\pc1\outbox\              knowledge-base\
    t1921\        ── UNC 讀取 ──▶   （收割後寫入這裡）
      manifest.json
      逐字稿.md / .srt
      課程筆記.md / .docx
```

**選 pull 不選 push 的理由**

1. 只有 notebook 一個讀者 → 權限只需「PC 給 notebook 唯讀」，不必讓 PC 有寫入 notebook 的權限。
2. 排程只要管一台（notebook），PC 掛掉不影響其他台收割。
3. 失敗可重試，PC 端不需要知道 notebook 在不在。

**代價**：PC 必須開 SMB 分享（§6），且 notebook 要能連到（Tailscale IP，已在 `config.py` 的 `TAILSCALE_IPS`）。

---

## 3. Outbox：PC 端的待收目錄

每個已完成的任務，worker 把產出**複製**（不是搬）到 outbox，最後才寫 `manifest.json`。

```
shared\<machine>\outbox\<task_id>\
├── manifest.json          ← 最後寫，代表「這包完整」
├── <stem>.md              逐字稿（KB 條目）
├── <stem>.srt
├── <stem> 課程筆記.md / .docx
└── <stem> 摘要.md / .docx
```

`manifest.json`（草案 v1）

```json
{
  "schema": 1,
  "task_id": "1921",
  "machine": "pc1",
  "video_id": "hY5G0pT5xmE",
  "title": "2026-11-02_週一 呂佳霖盤後分析",
  "kb_subdir": "人工智慧/AI agent-三師爸/直播",
  "local_video": "D:\\YouTube_Videos\\<stem>.mp4",
  "net_video": "\\\\100.84.223.110\\YouTube_Videos\\<stem>.mp4",
  "created_at": "2026-11-05T14:02:11+08:00",
  "files": [
    {"name": "<stem>.md",  "bytes": 48213, "sha256": "…"},
    {"name": "<stem>.srt", "bytes": 30122, "sha256": "…"}
  ]
}
```

規則：

- **`manifest.json` 最後寫**，先寫 `manifest.json.tmp` 再 `os.replace` → 收割器看到 `manifest.json` 就代表整包完整（跟音訊快取的 `.part.mp3` 同一個套路）。
- **複製不搬**：outbox 是副本，本機 KB 條目照舊留在 `knowledge-base\`（PC 自己也要能查）。
- `net_video` 由產出端算好（`config.TAILSCALE_IPS` 已有各機 IP），**收割器不改內文**。
- 重跑同一個 task → 先清空該目錄再寫，避免新舊檔混在一起。

---

## 4. 收割器：`harvest_pc.py`（notebook 端）

```
python -X utf8 harvest_pc.py                 # 收割所有可連線的機器
python -X utf8 harvest_pc.py --machine pc1   # 只收一台
python -X utf8 harvest_pc.py --dry-run       # 只列會做什麼，不寫檔、不動帳本
```

流程（每台機器）：

1. 讀 `config.TAILSCALE_IPS[machine]` → 組 UNC 根 `\\<ip>\AI-Agent-Workspace\shared\<machine>\outbox`
2. 連不到 → 記 `offline`，跳過（不算失敗，下次再試）
3. 逐個 `<task_id>\manifest.json`：
   - schema 版本不認識 → 跳過並警告（不要猜）
   - `video_id` 已在本機 KB（`channel_watcher.kb_video_index()`）→ 記 `skipped_exists`
   - `video_id` 已在帳本且 sha256 全對 → 記 `skipped_same`
   - 目標目錄已有同名檔但內容不同 → **不覆蓋**，移到 `knowledge-base/_harvest_conflicts/<machine>/<task_id>/` 並警告（寧可人工看，不要靜默蓋掉正本）
   - 乾淨的：逐檔複製 → 驗 sha256 → 全部通過才寫入 KB
4. 更新帳本（local，notebook 端）

**帳本**：`working\harvest_ledger.json`

```json
{
  "pc1:t1921": {"video_id": "hY5G0pT5xmE", "harvested_at": "…",
                "dest": "knowledge-base/…/<stem>.md",
                "sha256": {"<stem>.md": "…", "<stem>.srt": "…"}}
}
```

帳本放 notebook → **PC 的分享維持唯讀**（收割器不需要寫回 PC）。想標記「已被收割」就靠帳本，不靠 PC 端的回條。

**結束碼＝失敗數**（沿用 `smoke_test.py` 慣例），排程可直接看 exit code。

---

## 5. 影片指標：雙欄路徑

KB 條目的影片段落固定長這樣（**由產出端寫，收割器只驗證**）：

```markdown
## 影片
- 本機影片：`D:\YouTube_Videos\<stem>.mp4`
- 網路影片：`\\100.84.223.110\YouTube_Videos\<stem>.mp4`（PC1，Tailscale）
```

- notebook 點「網路影片」→ 線上播放，不搬檔
- 產出機點「本機影片」
- PC 離線時「網路影片」點不到 → 條目頂端加 `> ⚠️ 本片保存在 PC1，離線時無法播放`（可選，收割時偵測不到就標記？先不做自動偵測，避免每次收割都改檔）

---

## 6. PC 端一次性設定（SMB）

在每台產出機（PC1/PC2/PC3）用系統管理員 PowerShell 執行：

```powershell
# 1) 分享（唯讀）
New-SmbShare -Name "AI-Agent-Workspace" -Path "D:\AI-Agent-Workspace" -ReadAccess "Everyone"
New-SmbShare -Name "YouTube_Videos"     -Path "D:\YouTube_Videos"     -ReadAccess "Everyone"

# 2) NTFS 權限也要給（否則會出現「分享 Everyone Full 但 NTFS 沒有 → 存取被拒 5」）
icacls "D:\AI-Agent-Workspace" /grant "Everyone:(OI)(CI)(RX)" /T /C /Q
icacls "D:\YouTube_Videos"     /grant "Everyone:(OI)(CI)(RX)" /T /C /Q

# 3) 驗證（在 notebook 執行）
Test-Path "\\100.84.223.110\AI-Agent-Workspace\shared\pc1\outbox"
```

> 這是 **PC → notebook 方向**的權限。notebook 端先前設的是反向（notebook → PC），兩者不衝突，但方向不同、要各做一次。

---

## 7. 未解／待決（動手前要拍板）

| 項目 | 問題 | 目前傾向 |
|---|---|---|
| `shared/` 派工通道 | `task_status.json`、`shared/tasks/*.json`、heartbeat 都在 `shared/`。PC 若不與 notebook 共用，**跨機派工就斷** | 派工仍需共用；短期用 notebook 分享 `shared/` 給 PC 讀寫（已現況），收割只管 KB。長期才考慮資料庫化 |
| outbox 清理 | 收割後 PC 的 outbox 會一直長大 | 收割器寫帳本後，PC 端 worker 可選擇性清理「超過 30 天且已收割」——但 PC 不知道帳本。折衷：outbox 只保留 N 天，收割器看到帳本已收就直接跳過（不需要 PC 知道） |
| 影片保留 | 只進不出 | 30 天／或總量上限後搬 NAS 或刪；與收割無關，另案 |
| 衝突處理 | 同名不同內容 | 移到 `_harvest_conflicts/`，人工裁決（見 §4） |
| 舊條目無 `video_id` | 2133 筆舊 KB 條目沒有 id、沒有連結 | 收割器只處理有 `video_id` 的新產出；舊條目一次性補 id 是另一件工 |
| 三台同一支影片 | 理論上 worker 分工後不該發生，但重派可能 | 帳本以 `video_id` 為主鍵，第二台只記 `duplicate` 不覆蓋 |

---

## 8. 驗收方式（實作後）

1. `harvest_pc.py --dry-run` 只印計畫、不改檔、不動帳本（比照 `backfill_products.py --dry-run` 不扣配額的教訓）
2. 在 PC 造一個假 task（manifest + 2 個小檔）→ 收割 → 檔案落到 KB、帳本有記錄
3. 再跑一次 → `skipped_same`，檔案 mtime 不變
4. 拔網路（或改錯 IP）→ `offline`，結束碼 0（不是失敗）
5. 同名不同內容 → 進 `_harvest_conflicts/`，KB 正本未被覆蓋
6. 收割後 KB 條目在 notebook 可讀、影片連結可點

---

## 9. 排程建議

| 機器 | 時間 | 工作 |
|---|---|---|
| notebook | 22:30 | `ChannelWatcherDaily`（現況，唯一寫 KB 者） |
| notebook | 23:10 | `HarvestDaily`（新）→ 收 PC1/PC2/PC3 |

PC 端**不需要**任何收割排程（pull 模式）。
