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

---

## 11. PC2 / NAS 準備順序（2026-11-08 定案）

> 問題：額度、時間有限時，**PC2 和 NAS 哪個先準備？**
> 答案：**NAS 先（架構優先），但硬體未到，所以現在只做 PC2 的 deno**；
> **PC2 的 SMB 分享／憑證先不要做**（NAS 上線後就白工）。

### 11.1 當下實測（2026-11-08 02:37，notebook 端唯讀）

| 檢查 | 結果 | 意義 |
|---|---|---|
| `python -X utf8 nas_sync.py --check` | `OC_NAS_HOST`／`OC_NAS_ROOT` 未設定 | NAS 還沒上線，Phase 1~3 全部動不了 |
| `Test-NetConnection 100.113.234.81 -Port 445` | **True** | PC2 開機、SMB 埠可達 |
| `tailscale status` | `100.113.234.81 desktop-nl6va8t … active; direct` | Tailscale 正常，不是網路問題 |
| `shared\pc2\status.json` | `tasks_completed: 0`、`last_seen: 2026-07-23` | **PC2 從建置到今天沒跑過任何任務** |
| `shared\pc2\status\heartbeat.json` | `status: offline`、`pid: null`（2026-07-23 起） | PC2 端 worker 沒在跑 |
| harvest 失敗原因 | `WinError 1326`（登入失敗） | notebook 沒有 PC2 的 SMB 認證 |

### 11.2 為什麼架構上 NAS 該先

1. **pc2／pc3 現在 offline 的病根，是「每台 PC 各自開 SMB ＋ 各自存憑證」這套交換設計**
   （`WinError 1326`、pc3 沒 IP 都是同一類）。NAS 把交換層集中成一個點，
   **這類問題整類消失**，而不是一台一台補。
2. NAS 是**備援**；目前 outbox 只存在各 PC 本機磁碟，磁碟壞了就沒了。
3. 但 **NAS 尚未上線**（Phase 0 的程式已完成：`OC_OUTBOX_ROOT`／`OC_OUTBOX_ROOTS`／
   `nas_sync.py`，commit `7f22a49`），所以硬體到之前**什麼都不能驗**。

### 11.3 因此的執行順序

| 階段 | 做什麼 | 為什麼 |
|---|---|---|
| **現在**（NAS 未到） | PC2：安裝 **deno** → 跑 `smoke_test.py`（25 項） | 與 NAS 無關；沒有 deno，PC2 一下載 YouTube 就 403，會重演「66 支 14 秒全滅」 |
| **現在** | ❌ 先不要：PC2 的 SMB 分享、`cmdkey` 憑證 | 若 NAS 上線，PC2 的 outbox 直接指 NAS，這 10 分鐘是白工 |
| **現在** | ❌ 先不要：PC2 的 publish 排程 | 同上；等交換層定案再設一次 |
| NAS 到貨 | Phase 1 影子：`nas_sync.py --mirror --verify`（收割仍讀舊路徑） | 零風險，可先跑一週觀察 |
| Phase 2 | 設 `OC_OUTBOX_ROOT`（PC1／PC2）＋`OC_OUTBOX_ROOTS`（notebook）→ `harvest_pc.py --dry-run` 全 `skipped_same` | 驗收過才切；**切完不要立刻刪本機 outbox** |
| 之後 | PC2：`OC_OUTBOX_ROOT` 指 NAS、設 publish 排程 → **先跑 1 支測試任務** | PC2 從未跑過任務，別直接放整批 |

### 11.4 決策規則（一句話）

- NAS **2~4 週內**會到 → 照上表，PC2 只裝 deno，**不要**碰 SMB／憑證。
- NAS **延期或還沒採購** → 才回頭做 PC2 的 SMB 憑證，因為那時它是 PC2 產出被收割的唯一途徑。

### 11.5 不要做

- ❌ 看到 PC2 445 通就急著開分享＋存憑證（NAS 一到就作廢）。
- ❌ 在 PC2 上直接放幾十支任務當「測試」（它 `tasks_completed: 0`，先 smoke test ＋ 1 支）。
- ❌ 把 `shared\tasks` 或 `finance.db` 放上 NAS（控制面與 SQLite 都留本機）。

---

> **⚠ 2026-11-08 白天修正**：本節與 §11 撰寫時都假設「NAS 未到」。實際上 **NAS 已經就位**
> （`192.168.1.121:5000`，ping／445／5000／22 全通，DSM API 回 `success`），
> 卡點是「DSM 上還沒建 `exchange`／`backup` 分享與帳號」。**§11.4 的決策規則作廢，改看 §13。**

## 12. 2026-11-08 白天複核（撞牆後接手第一件事）

> 背景：§11 是 02:37 撞牆當下寫的。結論正確，但它把「現在」縮到只剩「PC2 裝 deno」，
> 而 deno 需要**有人在 PC2 前面**（沒有遠端通道），所以照那張表，今天實際可執行的動作是 **0**。
> 本節補「不等硬體、也不等人」的部分，並修正三個 §11 沒觀察到的事實。

### 12.1 複核結果（notebook 端唯讀實測）

| 檢查 | 結果 | 與 §11 的差異 |
|---|---|---|
| `python -X utf8 nas_sync.py --check` | NAS 尚未設定（預備狀態，rc=0） | 相同 |
| `Test-NetConnection 100.113.234.81 -Port 445` | **True**；`tailscale status` = `active; direct` | 相同 |
| `shared\pc2\status\heartbeat.json` | `offline`、`pid: null`、`last_seen 2026-07-23` | 相同（新架構 worker 從未啟動） |
| `Test-Path \\100.113.234.81\AI-Agent-Workspace` | **False**（新分享不存在） | §11 寫「先不要開」，實際是「確實沒開」 |
| `\\100.113.234.81\Share` | **可讀**，舊帳號 `user/abc123` 直接通過認證 | §11 未提：PC2 還開著**七月世代舊 Share** |

舊 Share 內容（2026-11-08 實測）：

| 目錄 | 內容 |
|---|---|
| `tasks\task_status.json` | 236 KB，停在 **2026-07-31**（舊架構最後一次派工） |
| `videos\` | 20 檔 / **3.8 GB**（7 月的課程影片） |
| `output\` | 424 檔 / 335 MB |
| `AI-Agent-Workspace\` | 59 檔 / 57 MB（7/19 的專案快照，與現行 repo 無關） |

**修正兩句**：

1. 「PC2 從沒跑過任務」要精確成「**新架構**沒跑過；舊 Share 架構在 7 月跑過，之後換代就停了」。
2. notebook 沒有 PC2 的**新**分享認證（`WinError 1326`），但**有**舊 Share 的弱憑證。
   舊分享是**暴露面**，不是解法 —— 它讓「PC2 有網路」看起來像「PC2 可用」，兩者不同。

### 12.2 備份缺口：比 §11 寫的小，但比「等 NAS」急

| 標的 | 大小 | 現況 |
|---|---|---|
| `knowledge-base/`（**正本**） | 140.5 MB / 4539 檔 | 只在 notebook `D:`，**無任何備份** |
| `financial_news/finance.db` | 57.3 MB | 同上（最後寫入 2026-09-10，pipeline 已停用） |
| PC1 `outbox` | 108 包 / 852 檔 / **10.6 MB** | 可重生的成品包，不是唯一副本 |
| `shared\notebook\results` | **6.36 GB / 1691 任務**（7 月～11/04） | 舊產物（mp4／mp3），佔住 `D:`；`D:` 只剩 **32.3 GB** |

NAS 的兩個價值要分開看：**交換層**（等硬體）與**備份**（不必等硬體）。
notebook 有 `H:`（外接 USB 3.7 TB，剩 1.5 TB），先做「KB ＋ finance.db 快照（約 200 MB）」就能補最痛的一塊。

### 12.3 修正後的優先序（風險 → 架構 → 產能）

| 級 | 動作 | 觸發條件 | 成本 | 為什麼排這裡 |
|---|---|---|---|---|
| **P0** | KB ＋ finance.db 快照到 `H:\_backup\`，留 `backup_pre_nas.bat` | 現在 | 3 分鐘 | 正本只有一份，`D:` 只剩 32 GB |
| **P0** | `shared\notebook\results` 的 mp4／mp3 移到 `H:`（md／srt 留著） | 現在（需同意） | 10 分鐘 | 回收 ~6 GB；舊產物不會再變動 |
| **P1** | PC2 到手 30 分鐘收拾：關舊 `Share`、停用 `user/abc123`、裝 deno、`smoke_test.py` 25 項 | 有人在 PC2 前 | 30 分鐘 | 舊分享是弱憑證暴露面 |
| **P1** | NAS Phase 1 影子（`nas_sync.py --mirror --verify`） | NAS 到貨 | 半天 | 零風險，先跑一週 |
| **P2** | PC2 開 worker（修 `AI_Agent_Worker` 觸發）＋ **1 支**測試任務 → 確認 outbox／publish | P1 之後 | 1~2 小時 | `tasks_completed: 0`，別直接放整批 |
| **P2** | NAS Phase 2（`OC_OUTBOX_ROOT`／`OC_OUTBOX_ROOTS`）＋收割驗收 | Phase 1 一週無異常 | 半天 | 切完不要立刻刪本機 outbox |
| **P3** | PC3（無 Tailscale IP、未部署） | NAS 上線後 | — | 三台裡最不重要 |

### 12.4 反向意見：NAS 若延期超過一個月

§11.4 說「NAS 延期就回頭做 PC2 的 SMB 憑證」。**建議不要**：那等於把已知會壞的設計
（每台 PC 各自開分享、各自存憑證、`WinError 1326` 無限循環）再複製一次；
而且 PC2 就算通了 SMB，派工仍要人 RDP 進去跑 `queue_youtube.py`（本專案刻意**沒有**中央派遣）。

折衷做法（NAS 延期時）：

- PC2 只當「**有人在旁邊時的本地批次機**」：不開分享、不設 publish 排程，
  跑完手動把成品併回 notebook（或等 NAS 上線再走正常路徑）。
- 交換層維持「PC1 → notebook」單線（目前正常：`harvest --dry-run` 全 `skipped_same`）。
- 這樣 PC2 的價值是**短期爆量**（一次 10~20 支），不是常態產能。

### 12.5 需要使用者決定（兩個輸入）

1. **NAS 大概什麼時候到？** ≤2 週／1 個月／還沒採購 → 決定 §11.4 走哪條。
2. **P0 兩項要不要現在做？**（快照到 `H:`、清 `results` 的 mp4／mp3）

### 12.6 P0 驗收

```powershell
# H: 需接著
robocopy knowledge-base H:\_backup\KB_latest /MIR /R:1 /W:1 /NFL /NDL
Copy-Item financial_news\finance.db H:\_backup\finance_latest.db
# 期望：H:\_backup\KB_latest 檔案數 = 4539；第二次跑「複製 0」
```

> 不要做：把 `H:\_backup` 當唯一備份。USB 接在同一台機器上，勒索／竊盜／機器損壞都擋不住；
> 它是 NAS 上線前的過渡，NAS 到貨後仍要 Hyper Backup ＋ Snapshot Replication。

---

## 13. NAS 已就位（2026-11-08 實測）→ 改走這條

### 13.1 實測（notebook 端，唯讀）

| 檢查 | 結果 | 意義 |
|---|---|---|
| `Test-Connection 192.168.1.121` | **通** | NAS 開機中 |
| TCP `445` / `5000` / `22` | **True / True / True** | SMB、DSM Web、**SSH 都開著** |
| `GET :5000/webapi/query.cgi?api=SYNO.API.Info` | `200 {"success":true}` | DSM 正常，不是半死機 |
| `Test-Path \\192.168.1.121\exchange` | **False** | 分享不存在，或無認證 |
| `Test-Path \\192.168.1.121\backup` | **False** | 同上 |
| `net view \\192.168.1.121` | 系統發生 5 錯誤（存取被拒） | 典型「沒有該機認證」 |
| notebook 網段 | Wi-Fi `192.168.0.127`（NAS 是 `192.168.1.121`） | **不同網段**，目前靠路由器轉送才通 |
| `tailscale status` | 只有 laptop／desktop-ndlv9li／desktop-nl6va8t | **NAS 不在 Tailscale 上** |

**結論**：真正缺的不是硬體，而是 **DSM 上的分享與帳號**（約 10~20 分鐘），
外加一個必須先解決的架構風險：**NAS 只在 LAN 內可達**，notebook 一離開 `192.168.1.x` 就收不到包。

### 13.2 新順序（今天就能走完 S0~S2）

| 步 | 做什麼 | 誰／怎麼做 | 驗收 |
|---|---|---|---|
| **S0** | DSM 建分享 `exchange`／`backup`／`archive`；建帳號 `producer`（讀寫自己子目錄）、`harvest`（唯讀 `exchange`） | DSM → 控制台 → 共用資料夾／使用者；或 SSH（22 已開）用 `synoshare --add`、`synouser --add` | `\\192.168.1.121\exchange` 打得開 |
| **S1** | notebook 存認證（`cmdkey`，重開機仍有效）→ `nas_sync.py --check --write-test` | notebook | `--check` 回 OK、寫入測試 OK |
| **S2** | Phase 1 影子：PC1 本機 outbox 照舊，另跑 `nas_sync.py --mirror --verify`；收割**仍讀 PC1** | PC1 | 連跑兩次第二次「檔案複製 0」；包數與本機相同 |
| **S3** | Phase 2：PC1 `OC_OUTBOX_ROOT` 指 NAS、notebook `OC_OUTBOX_ROOTS` 指 NAS → `harvest --dry-run` 全 `skipped_same` | 兩端 | 見 §5 驗收 |

### 13.3 前提風險：NAS 不在 Tailscale 上

- 現在 notebook 是 `192.168.0.127` → NAS `192.168.1.121` 還能通，是因為同一台路由器在轉。
- **一出家門就斷**；而 Phase 2 之後「收割」就是讀 NAS。斷了 → 收割記 `offline`（不會壞資料，但當天收不到）。
- 兩個選項（S3 之前做完任一個）：
  1. **NAS 裝 Tailscale**（DSM 套件中心有 Tailscale）→ notebook 隨地可收，與 PC1 現況一致。
  2. 維持 notebook **只在家收割**，外出當天就跳過（`offline` 會自動略過，隔天補）。
- 建議選 1：NAS 本來就要當「三機唯一交換點」，它不在 Tailscale 上，等於把可用性綁在家裡。

### 13.4 和 §12 的關係

- §12 的 **P0 備份**仍然要做，但目的地改成 NAS `backup\`（有了 S0 之後），`H:` 只當第二份。
- §12 的 **P1「PC2 到手 30 分鐘收拾」** 不變（關舊 Share、裝 deno），因為那和 NAS 無關。
- §11.4「NAS 延期才回頭做 PC2 SMB」**作廢** —— NAS 沒延期，PC2 的 SMB 分享就不必做了。

### 13.5 不要做

- ❌ S3 之前把 notebook 的 `OC_OUTBOX_ROOTS` 指 NAS（影子還沒驗過就切，等於拿生產賭）。
- ❌ Phase 2 後立刻刪 PC1 本機 outbox（NAS 還沒驗證完就是唯一副本）。
- ❌ 把 `shared\tasks`／`finance.db` 放上 NAS（控制面與 SQLite 留本機）。
- ❌ 在 NAS 上用 `Everyone`／弱密碼（PC2 舊 `Share` 的 `user/abc123` 就是前車之鑑）。

---

## 14. 決策紀錄（2026-11-08）

| 問題 | 決定 | 依據 |
|---|---|---|
| NAS 上要不要裝 opencode？ | **暫不裝**。先開 SSH 通道讓 notebook 上的 agent 直接操作；Tailscale 為第二順位；opencode 只在「真的需要 NAS 常駐 agent」時才用 Container Manager 跑，且用途限 NAS 本機運維 | 2 GB RAM、QuickConnect 不轉 SSH、NAS 上看不到 repo 的 `AGENTS.md`／KB，另養一個 agent 只會多一份會分歧的上下文 |
| 7 月那份 NAS 計畫還算數嗎？ | **不算**。July guide 只當「開箱步驟」的歷史文件；規格以本檔＋`NAS-WHITEPAPER.md` 為準 | July 設計把 SQLite 與收集排程放 NAS，與 §1「DB 不上 NAS」衝突 |
| 建置的東西怎麼記？ | **登記制**：`NAS-WHITEPAPER.md` §5 登記表（`N-xx`）＋ agent 專用目錄 `/volume1/agent-ops/<任務代號>/` | 使用者要求「不可隨便更動」，且要知道**為哪個任務而建** |

> 相關：`NAS-WHITEPAPER.md` §8 有完整評估表（相容性／記憶體／額度／上下文／遠端／維護）。
