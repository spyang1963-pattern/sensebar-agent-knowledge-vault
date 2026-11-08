# HANDOFF — NAS 上線／三機部署收尾（2026-11-09 02:00）

> 給下一個接手的人（或 agent）。先看這份，再看 `NAS-WHITEPAPER.md`、`NAS-PREP.md`、`DEPLOY-NEW-PC.md`。
> 本輪起點：NAS 剛上線、PC1 剛驗證 publish、PC2 環境全空、收割還在直讀 PC1。

---

## 0. 三句話

1. **資料流已改成「PC → NAS → notebook」**：PC1 22:50 發佈到 NAS（已驗證），notebook 23:10 從 NAS 收割
   （`skipped_same 102`）、01:30 備份到 NAS（每日排程已上線）。
2. **PC2 已 READY 但刻意待命**：環境／deno／Tesseract／Tailscale／NAS 憑證全部驗證通過，**0 排程、0 任務**。
3. **PC3 還沒處理**（未遷移、deno 未確認、無 Tailscale IP、無 NAS 憑證）。

---

## 1. 現況（2026-11-09 01:59）

| 機器 | 角色 | 狀態 | 排程 |
|---|---|---|---|
| **NAS DATANAS** | 交換＋備份（`192.168.1.121` / tailnet `100.65.113.20`） | 3 分享、2 帳號、Tailscale 已登入；`/volume1` 用 6.4 GB／7 TB | — |
| **PC1** | 產出＋發佈 | `producer` 憑證、`publish_daily.bat` 指向 NAS（實跑 `target = NAS`、`rc=0`） | `PublishOutboxDaily` 22:50 |
| **PC2** | 產出（待命） | READY；NAS 可寫、backup 被拒；0 包產出 | **無**（刻意） |
| **PC3** | 產出（未遷移） | 未遷到 `D:\AI-Agent-Workspace`；`TAILSCALE_IPS["pc3"]=None` | 無 |
| **notebook** | 收割＋正本 | KB 4540 檔／140.5 MB；`--prefer-nas` 已生效 | `ChannelWatcherDaily` 22:30、`HarvestPCDaily` 23:10、`NasBackupDaily` 01:30 |

**NAS 上的資料**

| 路徑 | 內容 |
|---|---|
| `exchange\pc1\outbox` | **102 包／102 manifest／102 唯一 video_id／10.3 MB** |
| `exchange\pc2\outbox`、`exchange\pc3\outbox` | 空（等產出） |
| `backup\knowledge-base` | 4540 檔／140.5 MB |
| `backup\finance_db\finance.db` | 57.3 MB（`quick_check=ok`、逐列雜湊與本機相同） |
| `backup\shared` | 7957 檔／165.2 MB |
| `archive\notebook-results` | 1691 個 mp4/mp3／6.06 GB（原在 notebook `shared\notebook\results`） |

---

## 2. 本輪完成

### 2.1 NAS 建置（S0–S3）

- 分享 `exchange`／`backup`／`archive`、帳號 `producer`（uid 1027）／`harvest`（uid 1028），
  SMB 五項權限實測通過（harvest 讀 exchange ✅／寫 ❌／寫 backup ✅；producer 寫 pc1 outbox ✅／寫 backup ❌）。
- agent 專用目錄 `/volume1/agent-ops/2026-11-08-nas-s0/`、`.../2026-11-08-nas-tailscale/`。
- 登記表 `NAS-WHITEPAPER.md §5`：**N-01~N-12**（多半 active）；`H-01`／`H-02`（2026-07 殘留 83 MB）**已刪、retired**。

### 2.2 Tailscale（N-08／N-12）

- 官方 DSM7 SPK `1.104.5`，tailnet `spyang1963@gmail.com`，NAS IP **`100.65.113.20`**。
- 兩個坑都已修並寫進白皮書 §5.2：
  1. DSM7 無 `/dev/net/tun` → 套件自動退回 userspace（遠端 SMB 不可用）；用 drop-in
     `pkgctl-Tailscale.service.d/tun-device.conf` 在啟動前 `insmod /lib/modules/tun.ko`＋`mknod`。
  2. 套件以 `tailscale` 使用者跑、`CapEff=0` → `tstun.New: operation not permitted` 後**默默退回**；
     已把 `/var/packages/Tailscale/conf/privilege` 改成 `defaults.run-as = root`。
     **套件升級會覆蓋，升級後要檢查。**

### 2.3 備份（N-11）

- `nas_backup.py`＋`backup_daily.bat`；`finance.db` 用 SQLite backup API（非直接 copy）。
- 自動選路：LAN → tailnet → MagicDNS FQDN；排程 **01:30**，試跑 `LastTaskResult=0`（約 4.5 分鐘）。

### 2.4 發佈與收割（S2／S3）

- PC1：102 包影印到 NAS；本機 108 = 102 ＋ 6 個 2026-11-06 舊重複包（同 video_id，去重後留較完整那份）。
- PC1 `publish_daily.bat` 改「NAS 優先、本機 fallback、獨立帳本」；**機器名由 `config.MACHINE` 取得**，
  同一支檔可用於 pc1/2/3；NAS 先試 LAN、再試 tailnet。
- notebook `harvest_pc.py --prefer-nas`：每台先看 NAS 該格，**空的才退回直讀**；
  `harvest_daily.bat` 已改成單一呼叫。
- 驗收：`harvest_pc.py --prefer-nas --dry-run` → pc1 `skipped_same 102`；PC1 端 `打包 0｜跳過 306｜失敗 0`
  （306＝102 唯一＋204 重複任務，NAS 目錄仍 102）。

### 2.5 一鍵部署（2026-11-08 補）

- 新文件 **`workspace-bundle/DEPLOY-NEW-PC.md`**（現行清單）。
- `external_tools.ps1` 補 **Deno**、**Tailscale**，並把 **Tesseract 寫入使用者 PATH**。
- `deploy.ps1` 新增 `PublishOutboxDaily`／`HarvestPCDaily`／`NasBackupDaily`（依機器篩選），
  新增 NAS 可達性＋cmdkey＋outbox 檢查；`Ensure-RuntimeDirs` 補 `logs`／`raw`／`shorts`。
- `smoke_test.py` 從 25 項→**35 項**（NAS、Tailscale、Tesseract、Obsidian、排程）。
- `ONBOARDING.md` 標示舊流程作廢（AnyDesk 複製 KB、NAS＝collector）。

### 2.6 PC2

- 環境、Python 套件、ffmpeg／VLC／Obsidian／Tesseract／Deno 2.9.8、Tailscale 1.104.5 全部就緒。
- NAS 憑證 `producer @ 100.65.113.20`（PC2 到不了 `192.168.1.121`）；讀 ✅／寫 `pc2\outbox` ✅／寫 `backup` ❌。
- `publish_outbox.py --dry-run`：0 包（尚無產出），正常。
- **沒有註冊任何排程**（`PublishOutboxDaily` 是 `smoke_test` 唯一刻意 ❌）。
- 一次誤貼事故（把 notebook 的回報貼給 PC2）：PC2 確認**沒有執行任何動作**，排程／程序／NAS 皆無變化。

---

## 3. 重要決定（不要推翻，除非改文件）

1. NAS **只做交換與備份**，不當執行機；`shared/tasks`、`task_status.json`、SQLite **不上 NAS**。
2. 方向單向：**PC → NAS → notebook**；notebook 不寫回 PC／NAS 的 exchange。
3. 產出機各寫自己的 `exchange\<machine>\outbox`；notebook 用 `harvest` **唯讀** exchange、可寫 backup。
4. 收割端「NAS 優先、空的退回直讀」——不要改成「看到 NAS 目錄就一律讀 NAS」，pc2/pc3 空目錄會漏收。
5. 排程單一寫入者；`deploy.ps1 -RegisterTasks` 會依機器篩選。

---

## 4. 踩過的坑（完整清單見 `DEPLOY-NEW-PC.md §6`、白皮書 §5.1／§5.2）

1. 先 `mkdir` 再 `synoshare --add` → `share_create.c:134`（0xE700）。
2. `synoacltool -enforce-inherit` 會變成 `everyone` 完整控制（紅線）。
3. SMB 同主機只保留一個 session；換帳號測試前要重啟 LanmanWorkstation。
4. `cmdkey` 認的是主機名；`\\datanas` 不通是正常的，用 IP。
5. `.bat` 在 `chcp 65001` 前不要有中文（UTF-8 位元組含 `&`／`|` 會被 cmd 當分隔）。
6. `.ps1` 含中文要存 **UTF-8 with BOM**（PS 5.1 會用 ANSI 讀沒 BOM 的檔）。
7. 缺 deno → yt-dlp 抓得到 metadata、下載全 403（PC1 曾 66 支全滅）。
8. Tesseract winget 版不會加 PATH → `pytesseract` 直接 `TesseractNotFoundError`。
9. **改了 repo 一定要 push**（PC2 曾因未推而拉到舊版 `external_tools.ps1`）。
10. 把「狀態回報」貼給另一台 agent 時，前面要加「這不是任務，不要執行任何動作」。

---

## 5. 待辦（依優先序）

| # | 事項 | 怎麼做 | 備註 |
|---|---|---|---|
| 1 | **PC2 手動跑一支測試影片**（驗證 deno→下載→轉錄→筆記全鏈路） | 在 PC2：`python -X utf8 run_pipeline.py raw\<資料夾>\<檔>.mp4` | 會用 Groq＋Gemini（PC2 的 Gemini key 已存在） |
| 2 | PC2 是否開始領任務 | 先決定「領哪些」（`assigned_to=pc2` 或未指派）→ 開 worker（**同機只能一個**） | 目前 PC2 `shared\tasks` 是 repo 自帶狀態 |
| 3 | **PC3 遷移** | 搬到 `D:\AI-Agent-Workspace` → `deploy.ps1 -Machine pc3` → `tailscale up` → 寫 `TAILSCALE_IPS["pc3"]` → 存 NAS 憑證 | 需要新主機名進 `MACHINE_ALIASES`（已預留 `desktop-mfkvcso`） |
| 4 | PC1 fallback 實測（選用） | 暫時讓 NAS 不可達，跑 `publish_daily.bat` 應改寫本機 | 不要真的關 NAS 太久 |
| 5 | NAS Tailscale 升級後檢查 | `ps -o user= -p $(cat /volume1/@appdata/Tailscale/tailscaled.pid)` 應為 root；`ip addr show tailscale0` | privilege 會被升級覆蓋 |
| 6 | `N-09`（`.nas_admin`）清理 | S1 完成後刪除或改金鑰 | 目前仍需要它做 NAS SSH |
| 7 | `nas_sync.py --check --write-test` | notebook 端 write-test 一定失敗（harvest 唯讀），這是預期 | `--check` 已 rc=0 |

---

## 6. 接手第一步（5 分鐘驗證，全部唯讀）

```powershell
cd D:\AI-Agent-Workspace

# 1) 收割來源與冪等（應 pc1 走 NAS、skipped_same 102；pc2 空 → 退回直讀）
python -X utf8 harvest_pc.py --prefer-nas --dry-run

# 2) 備份可達與大小
python -X utf8 nas_backup.py --dry-run

# 3) NAS 狀態
$env:OC_NAS_HOST="192.168.1.121"; $env:OC_NAS_ROOT="\\192.168.1.121\exchange"
python -X utf8 nas_sync.py --check

# 4) 排程
Get-ScheduledTask | Where-Object { $_.TaskName -match 'Harvest|NasBackup|Channel' } | Select-Object TaskName,State

# 5) 部署自檢（35 項）
python -X utf8 workspace-bundle\infra\setup\smoke_test.py
```

PC1（在 PC1 上）：

```powershell
python -X utf8 publish_outbox.py --dry-run
Get-Content logs\publish_outbox.log -Tail 6     # 應見 target = NAS
```

PC2（在 PC2 上）：`python -X utf8 workspace-bundle\infra\setup\smoke_test.py`
→ 預期只剩 `PublishOutboxDaily` ❌（刻意未註冊）。

---

## 7. 本輪 commits（origin/master 已同步）

```
82990b2 docs: deno status refresh (PC1/PC2/notebook ok; only PC3 unconfirmed)
2ed1127 docs: add trap about pasting status reports into another machine's agent
861928c deploy: PC2 environment + NAS credential verified ready (no schedule yet)
a2a4966 harvest: --prefer-nas makes every producer NAS-first with per-machine fallback
3d6f299 publish_daily: auto-detect machine + tailnet fallback (PC2 cannot reach NAS LAN IP)
a9aaaf9 deploy: tesseract PATH fix, logs/raw/shorts dirs, smoke checks for OCR/Obsidian; document push requirement
b3e1e13 deploy: add current one-click checklist + deno/Tailscale/NAS/tasks coverage
c8045c0 docs: S3 complete on both ends (PC1 target=NAS, 306 skips = 102 unique + 204 duplicate tasks)
9e55495 docs: S2/S3 results (102 packs verified, harvest from NAS skipped_same 102) + bat ASCII-only trap
14bc8bf S3 switch: pc1 publish -> NAS (with local fallback), notebook harvest -> NAS (with PC1 fallback)
e317608 quota: prove free pool is shared across machines (PC1 0 local usage blocked), reset drifted to 08:36
c2b2bf7 NAS backup: add MagicDNS FQDN fallback + record SMB name caveat (cmdkey needed per name)
cd1f8af NAS Tailscale live: tailscale0 100.65.113.20, root privilege fix, backup auto LAN/tailnet fallback
be57b17 NAS: Tailscale package + tun fix (N-12), daily backup schedule 01:30, record 21:33 quota wall
e2860f9 NAS P0: first full backup (KB/finance.db/shared) + move 6.06GB media to archive
a18d5b3 NAS S0 done: exchange/backup/archive shares + producer/harvest accounts, ACL recipe, whitepaper inventory
6796fdb add PC-side producer credential helper + record nas_sync --check result (rc=0)
```

---

## 8. 額度（交棒時 2026-11-09 01:59）

- 免費池：本機日累計 **195 次**（08:01 起算）、5h **60/200**；上次撞牆 11-08 21:33。
- **宣告重置：2026-11-09 08:36**（三台共用同一 pool，按帳號／公開 IP 計）。
- Go：5h 0%／週 0%／**月 100% `rate-limited`（11/10 22:32 重置）**，請求仍可成功。
- 實務：多機任務一律先用 Go；被拒就存快照再切，不要猜剩多少。

---

## 9. 相關文件

- `workspace-bundle/NAS-WHITEPAPER.md` — NAS 現況、登記表 N-01~N-12、ACL／Tailscale 正確做法、紅線
- `workspace-bundle/NAS-PREP.md` — S0~S3 步驟與實作結果（§13.6／§13.7）
- `workspace-bundle/DEPLOY-NEW-PC.md` — 新機一鍵部署（現行）
- `workspace-bundle/ONBOARDING.md` — 金融線細節（部分流程已被 NAS 取代，文首有標示）
- `docs/incidents/2026-11-08_quota-wall.md` — 兩次撞牆與「跨機共用免費池」證據
- `AGENTS.md` — 日常規則（NAS 段、deno 狀態、免費額度、YouTube 403、跨機收割）
