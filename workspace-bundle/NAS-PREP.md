# NAS 預備計畫（Synology DS718+）

> 狀態：**NAS 尚未上線**。本文件與程式掛鉤已就緒，機器到手後照「第 5 節 三階段」走即可。
> 定位沿用 `HANDOFF-3MACHINE-DEPLOY.md` 第 4 節：**備援儲存 + 交換區，不當執行機**；
> **SQLite 不放 NAS**（SMB 鎖定／毀損風險），DB 留在現役 harvester，NAS 只收備份。

---

## 1. 先切清楚：控制面 vs 資料面

| 面 | 內容 | 現在 | NAS 上線後 |
|---|---|---|---|
| **控制面** | `shared/tasks/*.json`、`task_status.json`、heartbeat | 本機 `shared/` | **不動**（worker／GUI／scheduler 都是本機路徑，搬了會分裂） |
| **資料面** | `shared/<machine>/outbox/<tid>/`（成品包） | PC 本機 → SMB 給 notebook 讀 | **可搬到 NAS 交換區** |
| 備份 | `knowledge-base/`、`finance.db`、`shared/` | 無 | NAS 每日備份 |

只有「資料面」有掛鉤，控制面刻意不開放搬遷。

---

## 2. 本次已完成的預備（2026-11-07）

| 項目 | 內容 |
|---|---|
| `config.py` | 新增 `OUTBOX_ROOT`（產出機 publish 目的地）、`OUTBOX_ROOTS`（收割端機器→路徑覆寫）、`NAS_HOST`／`NAS_ROOT`；全部可用環境變數覆寫，預設值＝現況 |
| `harvest_pc.py` | `machine_root()` 先看 `OUTBOX_ROOTS`，沒設定就照舊用 Tailscale IP 推導 → **未設定時行為完全不變** |
| `publish_outbox.py` | 有 `OC_OUTBOX_ROOT` 就寫那裡，否則照舊 `shared/<machine>/outbox` |
| `nas_sync.py` | 新增。`--check` 檢查連線／資料夾／空間／寫入；`--mirror` 影子複製（只複製不刪、manifest 最後寫、可 `--verify` 比 sha256） |
| 回歸驗證 | `harvest_pc.py --machine pc1 --dry-run` → `skipped_same 108`（0 衝突）；`publish_outbox.py --dry-run` → rc=0；`nas_sync.py --mirror` 連跑兩次第二次 0 複製（冪等） |

環境變數一覽：

```powershell
# 產出機（PC1/PC2/PC3）：publish 直接寫 NAS
$env:OC_OUTBOX_ROOT = "\\NAS\exchange\pc1\outbox"

# 收割端（notebook）：從 NAS 讀（JSON；單引號內是字面值，反斜線要兩層）
$env:OC_OUTBOX_ROOTS = '{"pc1":"\\\\NAS\\exchange\\pc1\\outbox","pc2":"\\\\NAS\\exchange\\pc2\\outbox"}'

# nas_sync.py 檢查用
$env:OC_NAS_HOST = "192.168.1.50"
$env:OC_NAS_ROOT = "\\192.168.1.50\exchange"
```

> 環境變數只對「該次執行」有效；排程要用，請在 `publish_daily.bat`／`harvest_daily.bat` 內加
> `set OC_...=...`（cmd 語法），或直接寫進 `config.py`（單機設定最省事）。

---

## 3. NAS 資料夾規劃

```
\\NAS\exchange\                    ← OC_NAS_ROOT（三機唯一寫入區）
├── pc1\outbox\<task_id>\          ← PC1 publish 產出
├── pc2\outbox\<task_id>\
├── pc3\outbox\<task_id>\
└── _quarantine\                   ← 人工判斷用（衝突／壞包，不自動清）

\\NAS\backup\                      ← 只收備份，不當工作區
├── knowledge-base\                ← notebook 正本（Hyper Backup 或 robocopy /MIR）
├── finance.db\
├── shared\
└── config\                        ← config.py、opencode.json、.env（不含 API key 明文）

\\NAS\archive\videos\              ← 冷片（30 天後從 PC 搬過來，見 HANDOFF 第 4 節）
\\NAS\wheelhouse\                  ← pip download 的 wheels（新機離線安裝）
```

命名原則：**機器代號資料夾＝`config.MACHINE`**（pc1／pc2／pc3／notebook），不要用 hostname 或 IP，
換網路時才不用改一堆東西。

---

## 4. 帳號與權限（別再犯 `Everyone` 的錯）

| 帳號 | 權限 | 給誰 |
|---|---|---|
| `producer` | 讀寫 `exchange\<machine>`（各自子目錄） | PC1／PC2／PC3 |
| `harvest` | **唯讀** `exchange\`、讀寫 `backup\`（若由 notebook 推備份） | notebook |
| `admin` | 僅 DSM 管理 | 人 |

- DSM → 控制台 → 共用資料夾 → 權限，**不要**勾 `Everyone`。
- notebook 存認證用 **`cmdkey`**（重開機仍有效），不要只靠 `net use /persistent:yes`：

```powershell
cmdkey /add:192.168.1.50 /user:harvest /pass:"<密碼>"
Test-Path \\192.168.1.50\exchange        # 應 True
```

- 建議 NAS 設 **固定 IP**（路由器 DHCP 保留），或走 Tailscale（跨網段時）。

---

## 5. 三階段切換（每階段都可回滾）

### Phase 0 — 現在（NAS 未到）
- 生產不動。
- `python -X utf8 nas_sync.py --check` 應回「NAS 尚未設定（預備狀態，正常）」、rc=0。

### Phase 1 — 影子模式（NAS 到了，先驗證）
- PC 照舊 publish 到本機 `shared\<machine>\outbox`，**再加跑**一次鏡像：

```powershell
python -X utf8 nas_sync.py --mirror --verify
```

- notebook **仍讀舊 UNC**（不要改 `OC_OUTBOX_ROOTS`）。
- 驗收：
  - `nas_sync.py --check` → 根目錄存在、`pc1` OK、空間足夠、寫入 OK
  - `nas_sync.py --mirror --verify` 連跑兩次 → 第二次「檔案複製 0」
  - 比對包數：本機 `shared\pc1\outbox` 目錄數 ＝ NAS `exchange\pc1\outbox` 目錄數
- 這一階段不影響生產，有問題直接停排程即可。

### Phase 2 — 正式切換
1. PC 端：`OC_OUTBOX_ROOT=\\NAS\exchange\<machine>\outbox`（或改 `config.py`）
2. notebook 端：`OC_OUTBOX_ROOTS={"pc1":"\\\\NAS\\exchange\\pc1\\outbox", ...}`
3. 跑一次 `publish_outbox.py`（沒變的會跳過）→ `harvest_pc.py --dry-run`（期望全 `skipped_same`）
4. 確認後才關掉 PC 的 SMB 分享／停用 `harvest` 帳號

驗收（切換後第一次）：
```powershell
python -X utf8 harvest_pc.py --machine pc1 --dry-run     # 期望 skipped_same，0 conflict
python -X utf8 harvest_pc.py --machine pc1               # 再跑一次應全部 skipped_same（冪等）
```

### Phase 3 — 備份與歸檔
- NAS Hyper Backup（或 notebook 端 robocopy）每日抓 `knowledge-base\`、`finance.db`、`shared\`。
- `\\NAS\archive\videos\` 收 30 天以上冷片；`wheelhouse\` 收 wheels。
- 開 **Snapshot Replication**（Btrfs）防勒索；快照不等於備份，兩者都要。

---

## 6. 排程建議（切換後）

| 機器 | 時間 | 工作 | 腳本 |
|---|---|---|---|
| PC1 | 22:50 | publish（寫 NAS） | `publish_daily.bat` |
| notebook | 23:10 | harvest（讀 NAS） | `harvest_daily.bat` |
| NAS | 03:00 | Hyper Backup → 外接／雲端 | DSM 內建 |

Phase 1 期間可在 PC1 加一個 22:55 的 `nas_sync.py --mirror`；切到 Phase 2 就移除。

---

## 7. 回滾

| 階段 | 回滾方式 | 影響 |
|---|---|---|
| Phase 1 | 停掉 mirror 排程 | 無（生產沒動） |
| Phase 2 | 移除 `OC_OUTBOX_ROOT`／`OC_OUTBOX_ROOTS` 即回舊路徑 | 帳本 key 是 `machine:task_id`，不受路徑影響；已收割的不會重收 |
| 任何時候 | NAS 掛掉 → 把 `OC_*` 拿掉，PC 本機 outbox 仍在 | 前提：Phase 2 前**不要**刪本機 outbox |

**不要做**：Phase 2 之後立刻刪 PC 本機 outbox（NAS 還沒驗證完就是唯一副本）。

---

## 8. 待決事項（機器到手前先想）

1. 硬碟容量與 RAID（建議 SHR-1，可容單碟故障）。
2. 分享名稱與配額：`exchange` / `backup` / `archive` 三顆，配額怎麼分。
3. 備份由誰發起（建議 notebook 推，或 NAS 自己 pull）。
4. 是否啟用 Snapshot Replication（Btrfs）。
5. NAS 固定 IP 或 Tailscale。
6. 要不要把 `finance.db` 備份加密（含交易資料）。

---

## 9. 已知風險

| 風險 | 說明 | 對策 |
|---|---|---|
| SMB 上的 SQLite | 多機同時開會鎖定／毀損 | DB 不上 NAS，只放備份 |
| NAS 單點故障 | 交換區掛掉 → 收割停 | 本機 outbox 保留到驗證完；`offline` 只會延後，不會弄壞資料 |
| 權限過寬 | 任一台被入侵就全滅 | 每台只給自己的子目錄；notebook 唯讀 |
| 時鐘不同步 | mtime 比較會失準 | `nas_sync.py` 比**大小／sha256**，不比 mtime |
| 半成品包 | 打包中就被複製 | 沿用「manifest 最後寫」，沒 manifest 的包跳過 |
| 兩邊同時寫 | 同包不同內容 | 指紋帳本會跳過未變更的；切換期避免同時跑兩套 |

---

## 10. 快速指令卡

```powershell
# 現在就能跑（NAS 未設定會回「預備狀態」）
python -X utf8 nas_sync.py --check

# NAS 設定後
python -X utf8 nas_sync.py --check --write-test
python -X utf8 nas_sync.py --mirror --dry-run
python -X utf8 nas_sync.py --mirror --verify

# 切換後驗收
python -X utf8 harvest_pc.py --machine pc1 --dry-run
python -X utf8 publish_outbox.py --dry-run
```
