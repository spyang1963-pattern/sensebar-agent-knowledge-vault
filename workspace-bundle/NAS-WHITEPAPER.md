# NAS 白皮書（Synology DS718+）

> 版本：**v0.1**（2026-11-08）
> 撰寫：notebook 上的 agent（`opencode`），依 2026-11-08 實測與 repo 清查結果
> 定位：**NAS 的「現況＋登記簿＋紅線」**。要動 NAS 之前先看這份；切換步驟看 `NAS-PREP.md`。
> 這份文件的目標只有一個：**任何人（含 agent）都能一眼看出「這個東西是誰建的、為什麼、亂動會壞什麼」。**

---

## 0. 三句話

1. NAS 是 **Synology DS718+**（x86_64 / 2 GB RAM），已在 `192.168.1.121` 運作，DSM **7.3.1-86003**，
   **S0 建置已於 2026-11-08 20:2x 完成**：`exchange`／`backup`／`archive` 三個分享＋`producer`／`harvest` 兩個帳號
   都已建立並以 SMB 實測權限（見 §1.3、§5）。
2. 它的角色是 **交換區＋備份**，**不是**執行機：`shared/tasks`、`finance.db`、SQLite **一律不上 NAS**。
3. 2026-07 那份 NAS 計畫（SQLite 上 NAS、NAS 跑收集排程）**已被 11 月決策推翻**，只留歷史價值（見 §3）。

---

## 1. 硬體與服務現況（2026-11-08 實測，SSH 登入後逐項確認）

### 1.1 硬體與系統

| 項目 | 值 | 備註 |
|---|---|---|
| 型號 | Synology **DS718+**（2017，2 bay） | |
| CPU | **Intel Celeron J3455**（4 核，x86_64，含 AES-NI） | 是 x86_64，**不是 ARM**（容器／Linux 版程式都能用） |
| RAM | **1827 MB** 可用（實測 `free -m`：已用 358、可用 1162） | **最大的硬體限制**，別在上面常駐重服務 |
| Swap | 3147 MB（已用 20） | DSM 自己開的，別關 |
| 主機名 | **DATANAS** | 之後 `cmdkey`／`net use` 用它比用 IP 好（見 `AGENTS.md` SMB 段） |
| DSM 版本 | **7.3.1-86003**（GM，builddate 2025/10/22） | 已是最新分支，短期不用升級 |
| 儲存 | `/dev/mapper/cachedev_0` → **`/volume1` 7.0 TB，已用 207 MB（1%）** | 幾乎全空 |
| RAID | `md0`／`md1`／`md2` 全部 `[UU]`（**2×8 TB RAID1 鏡像**） | 兩顆都健康；壞一顆還撐得住 |
| Python | 系統 `/usr/bin/python3` = **3.8.15**；`Python3.9` 套件已安裝但 **`/usr/local/bin/python3` 不存在** | 要在 NAS 跑 Python 腳本前先確認解譯器路徑 |
| Synology 工具路徑 | `synoshare`／`synouser`／`synogroup` 在 **`/usr/syno/sbin/`**；`synopkg` 在 `/usr/syno/bin/`；`synoacltool` 在 **`/usr/syno/bin/`** | 都不在 sudo 的預設 PATH，**要用絕對路徑** |

### 1.2 帳號與權限

| 項目 | 值 |
|---|---|
| 使用者 | `admin`（系統內建，未啟用登入）、`guest`（停用）、**`yang`（uid 1026，實際使用的管理者）** |
| 群組 | `administrators` = `admin`、`yang`（**`yang` 是唯一能登入的管理者**） |
| `yang` 的 home | 設定寫 `/var/services/homes/yang`，但**目錄不存在**（SSH 登入會印 `Could not chdir` 警告，**不影響操作**） |
| SSH | 22 埠開，`yang`＋密碼可登入，`sudo` 可用（需密碼） |

> ⚠ **只有一個管理者帳號**：`yang` 的密碼就是 NAS 的最高權限。不要拿它當日常搬檔帳號（見 §5 的 `producer`／`harvest`）。

### 1.3 已建立的分享（2026-11-08 20:17 由 agent 建立三個）

| 分享 | 路徑 | 權限（實測結論） | 內容 |
|---|---|---|---|
| `exchange` | `/volume1/exchange` | `producer` RW／`harvest` **RO**／`@administrators` RW／`guest` 拒絕 | `pc1/outbox`、`pc2/outbox`、`pc3/outbox` |
| `backup` | `/volume1/backup` | `harvest` RW／`@administrators` RW／`producer` 拒絕／`guest` 拒絕 | `knowledge-base/`、`finance_db/`、`shared/` |
| `archive` | `/volume1/archive` | `producer` RW／`harvest` RO／`@administrators` RW／`guest` 拒絕 | `videos/` |
| `資料分享區` | `/volume1/資料分享區` | ACL 開、回收桶開（管理員限定）、RW／RO 名單空白、可瀏覽（**使用者的，不由 agent 管理**） | `finance/pip`（24 MB）、`finance/workspace`（59 MB）＝ **2026-07 的殘留**（見 §3.1） |

**驗收（2026-11-08 20:2x，notebook 以 SMB 實測）**

| 測試 | 期望 | 實測 |
|---|---|---|
| `harvest` 讀 `exchange` | 可 | ✅ |
| `harvest` 寫 `exchange` | 拒 | ✅ |
| `harvest` 寫 `backup` | 可 | ✅ |
| `producer` 寫 `exchange\pc1\outbox` | 可 | ✅ |
| `producer` 寫 `backup` | 拒 | ✅ |

> 這五條就是「方向只有 PC → NAS → notebook」的**機器層保證**，不是靠人記得。改權限前先看 §5.1。

### 1.4 已安裝套件（16 個，**沒有** Container Manager／Docker／Tailscale）

`SMBService`、`SynoFinder`、`Python2`、`StorageManager`、`ActiveInsight`、`ScsiTarget`、
`SynoAnalytics`、`USBCopy`、`SynoOnlinePack_v2`、`SecureSignIn`、`OAuthService`、`Python3.9`、
`HybridShare`、`QuickConnect`、`FileStation`、`SupportService`

### 1.5 網路與通道

| 項目 | 值 | 備註 |
|---|---|---|
| 網路 | `192.168.1.121` | 建議路由器做 DHCP 保留（固定 IP） |
| 遠端 | 已設 **QuickConnect** | 只給 DSM 網頁／手機 App 用，**不能 SSH** |
| 開啟的埠（實測） | `22`（SSH）、`445`（SMB）、`5000`（DSM）、`5001`（DSM HTTPS） | 皆可連 |
| DSM API | `:5000/webapi/query.cgi` → `{"success":true}` | 系統正常運行 |
| `\\192.168.1.121\exchange`／`\backup`／`\archive` | **False** | 分享還沒建（N-01~N-03 尚 pending） |
| notebook 網段 | Wi-Fi `192.168.0.127`（NAS 在 `192.168.1.x`） | 不同網段，目前靠路由器轉送；**一出家門就斷** |
| Tailscale | NAS **不在** Tailscale | 收割改讀 NAS 後，外出就收不到（見 `NAS-PREP.md` §13.3） |

---

## 2. 四條通道與各自的限制

| 通道 | 現在能不能用 | 限制 |
|---|---|---|
| **QuickConnect**（`quickconnect.to/<id>`） | 可（你已設好） | 只有 DSM 網頁／File Station／DS file；**沒有 SSH**，agent 無法用 |
| **SSH 22** | 埠開著，但**還沒有帳號給 agent** | DSM 帳號＋密碼（或金鑰）；外出需先有 Tailscale／VPN |
| **SMB 445** | 埠開著，**沒有分享／沒有認證** | 只給資料搬運，不給設定操作 |
| **DSM Web 5000** | 可用（瀏覽器） | 適合人手操作；agent 用 API 需登入（2FA 會擋） |

> 結論：**要讓 agent 真正「著手」NAS，缺的是 SSH 帳號，不是 opencode。**

---

## 3. 2026-07 的作業清查（結論：只有文件，沒有實際設定）

| 項目 | 實際狀態 |
|---|---|
| `financial_news/MULTIMACHINE_NAS_GUIDE.md` | 8/2 建立（commit `a5a2956`、`5dc7f91`），內容是「DS718+ 開箱→裝 DSM→開 SMB→建 `share`」的**步驟 guide** |
| 實際在 NAS 上做過的設定 | **查不到任何落地痕跡**（無 `exchange`／`backup` 分享、無認證、無排程紀錄） |
| 該 guide 的設計 | 中央 SQLite 放 NAS、NAS 跑 `pipeline.py --collect` 每 30 分、三機共用 DB |
| 該設計的現況 | **已被推翻**：`workspace-bundle/NAS-PREP.md` §1 明定 **SQLite／DB 不上 NAS**（SMB 鎖定＋毀損風險），NAS 只做交換區＋備份；`FinanceNews_Pipeline` 排程也已 `Disabled`（2026-08-24 起） |

**接手原則**：不要把 July guide 當規格書，它只是「怎麼把機器弄起來」的歷史文件。
真正的規格是 `NAS-PREP.md`（Phase 0~3）＋本白皮書。

### 3.1 July 在 NAS 上真正留下的東西（2026-11-08 實測）

| 路徑 | 大小 | 內容 | 處置 |
|---|---|---|---|
| `/volume1/資料分享區/finance/workspace/` | **59 MB** | 2026-07-26～08-17 的**整份 repo 副本**：`agents.md`、`CLAUDE.md`、`channel_watcher.py`、`auto_update.py`、`config.py`、`Clipping/`、`docs/`、`2026-07-26.md`、`PLANNING.md` … | **只讀參考，不當來源**（與本機 repo 已分歧）；確認沒人要就刪（`H-01`） |
| `/volume1/資料分享區/finance/pip/` | 24 MB | Python `pip` 安裝殘留（`bin/`、`lib/`） | 同上，`H-02` |
| `/volume1/資料分享區/#recycle/` | ~0 | 只有 `desktop.ini` | 不用管 |

> 這兩包是「把 NAS 當執行機」那個舊計畫的遺跡。**不要**從中取腳本回來跑（版本比本機舊、且含已廢棄的 SQLite 設計）。
> 它們在 `資料分享區` 內，**不是** agent 建的，所以登記為 `H-01`／`H-02`（人手建立）。

---

## 4. 現行架構（目標狀態）

```
PC1（產出）                       NAS DS718+                     notebook（收割／正本）
shared\pc1\outbox  ──publish──▶  exchange\pc1\outbox  ──harvest──▶  knowledge-base\
（Phase 2 後直接寫 NAS）           exchange\pc2\outbox                （唯一正本，永不回寫 PC）
                                  exchange\pc3\outbox
knowledge-base\    ──備份────▶    backup\knowledge-base\
finance.db         ──備份────▶    backup\finance_db\
                                  archive\videos\（30 天冷片）
```

- **控制面永遠在本機**：`shared/tasks`、`task_status.json`、heartbeat、`finance.db` 不搬。
- **方向永遠單向**：PC → NAS → notebook。notebook 不寫回 PC／NAS 的 exchange。

---

## 5. 建置登記表（Registry）— 動任何東西前先看這張

> 規則：**每一項由 agent 建立的檔案／設定，都必須有一列**。沒有列的就是「來路不明」，不要動、先問。
> 狀態：`pending`（計畫中）／`active`（已建立）／`retired`（已停用，保留紀錄）。
> agent 建立的一律加前綴 `N-`；人手建立的加 `H-`。

| ID | 物件（路徑／設定） | 屬於哪個任務 | 用途 | 亂動會怎樣（影響） | 回滾 | 狀態 |
|---|---|---|---|---|---|---|
| N-01 | `\\NAS\exchange` = `/volume1/exchange` | 跨機收割 | PC 產出包的中央交換區（`pc1/pc2/pc3/outbox`） | 收割全部 `offline`；PC 的 publish 失敗 | 刪分享、把 `OC_OUTBOX_ROOT(S)` 拿掉即回本機路徑 | **active**（2026-11-08 20:17） |
| N-02 | `\\NAS\backup` = `/volume1/backup` | 每日備份 | 收 `knowledge-base\`、`finance.db`、`shared\` 備份（子目錄已建空） | 沒有備份；不影響生產 | 刪分享；備份檔另存 | **active**（2026-11-08 20:17） |
| N-03 | `\\NAS\archive` = `/volume1/archive`（`videos\`） | 冷片歸檔 | 30 天以上影片離線存放 | 只影響空間回收，不影響流程 | 刪分享；影片搬回 | **active**（2026-11-08 20:17） |
| N-04 | 使用者 `producer`（uid 1027，shell `/sbin/nologin`） | publish（PC1/2/3） | 只給各機寫 `exchange\<machine>\outbox`；**不能寫 backup** | publish 失敗（`WinError 1326`／權限被拒） | 停用帳號即可 | **active**（2026-11-08 20:16） |
| N-05 | 使用者 `harvest`（uid 1028，shell `/sbin/nologin`） | 收割（notebook） | **唯讀** `exchange\`、可寫 `backup\` | 收割失敗 | 降權或停用 | **active**（2026-11-08 20:16） |
| N-06 | `/volume1/agent-ops/`（NAS 本機，目前只有 `2026-11-08-nas-s0/README.md`） | 所有 agent 在 NAS 上的操作 | **agent 專用工作目錄**：腳本、日誌、暫存，一個任務一個子目錄 | 清掉會失去 agent 操作紀錄；**不含任何使用者的資料** | 整個目錄刪除即可 | **active**（2026-11-08 20:16） |
| N-07 | notebook `cmdkey` 認證（`192.168.1.121` → `harvest`） | S1 | 讓 SMB 免密碼重連（重開機後仍有效） | 收割／備份失敗（`WinError 1326`） | `cmdkey /delete:192.168.1.121` | **active**（2026-11-08 20:2x，已驗收） |
| N-08 | NAS 上的 Tailscale（套件） | 遠端收割 | 讓 notebook 外出也能讀 NAS | 外出時收割 `offline`（不會壞資料） | 移除套件 | pending |
| N-09 | notebook `%USERPROFILE%\.nas_admin`（`yang` 帳號／密碼，**repo 外**） | S0 建置 | 讓 agent 用 SSH 登入 NAS 做一次性設定 | 刪掉只是 agent 失去登入能力，**不影響 NAS 運作**；外流＝對方有 DSM 權限 | 直接刪檔；或改密碼／停用帳號 | **active**（2026-11-08；**S1 完成後刪除或改用金鑰**） |
| N-10 | notebook `%USERPROFILE%\.nas_accounts.json`（`producer`／`harvest` 密碼，**repo 外**） | S0 建置 | 讓 PC1（producer）與 notebook（harvest）取用各自密碼 | 刪掉不會壞 NAS，只是要重設密碼（`synouser --setpw`）；外流＝可寫 exchange／backup | 刪檔＋改密碼 | **active**（2026-11-08 20:16） |
| H-01 | `/volume1/資料分享區/finance/workspace/`（59 MB） | 2026-07 舊計畫殘留 | 舊版 repo 副本，**不是** agent 建的、也不是生產資料 | 刪掉不影響任何現行流程；但**別從這裡取腳本回來跑**（版本已歧異） | 已無回滾需求 | active（待使用者決定是否刪） |
| H-02 | `/volume1/資料分享區/finance/pip/`（24 MB） | 2026-07 舊計畫殘留 | Python pip 安裝殘留 | 同上 | 已無回滾需求 | active（待使用者決定是否刪） |

> **N-06 是關鍵**：agent 在 NAS 上建立的東西**一律**放 `/volume1/agent-ops/<任務代號>/`，
> 並在該子目錄放一個 `README.md` 寫「為什麼建、對應哪個 repo 任務、怎麼刪」。
> 這樣「哪些檔案是 agent 建的」不需要靠記憶，看目錄就知道；使用者的資料（`exchange`／`backup`／`archive`／相簿…）**永遠不在這裡**。

### 5.1 建立分享＋設定權限的**唯一正確做法**（2026-11-08 實踩，勿憑記憶重做）

```sh
# 0) 目標路徑必須【不存在】，DSM 會自己建；先 mkdir 會失敗（share_create.c:134 / 0xE700）
/usr/syno/sbin/synoshare --add exchange "desc" /volume1/exchange "" "" "" 1 0

# 1) 新分享預設 ACL RO = #everyone（等於「所有帳號可讀」）→ 必須先歸零
/usr/syno/sbin/synoshare --set_share_default_acl exchange      # 只剩 @administrators

# 2) 再指定各帳號（這一步會「覆寫」整份 ACL，所以務必在 1) 之後）
/usr/syno/sbin/synoshare --setuser exchange RW = producer
/usr/syno/sbin/synoshare --setuser exchange RO = harvest
/usr/syno/sbin/synoshare --setuser exchange NA = guest          # NA = deny

# 3) 2) 會把 @administrators 那條蓋掉 → 補回來（否則連 yang 都進不去）
/usr/syno/bin/synoacltool -add /volume1/exchange "group:administrators:allow:rwxpdDaARWc--:fd--"

# 4) 用 CLI 先建好的子目錄不會自動繼承 → 從自己的上層複製 ACL
/usr/syno/bin/synoacltool -copy /volume1/exchange /volume1/exchange/pc1
```

❌ **絕對不要用 `synoacltool -enforce-inherit`**：在 DSM 7.3.1 上實測會把整份 ACL 換成
`everyone::allow:rwxpdDaARWcCo`（**所有人完整控制**），等於紅線 2 直接破功。`-set-eadir-acl` 同批也報錯。
✅ 驗收一律用 `synoacltool -get-perm <path> <user>` 與**真的用 SMB 寫一次**（見 §1.3 表）。

> 另一個坑：SMB 對同一台主機**只保留一個 session**。先用 `producer` 連過，之後就算 `cmdkey` 已改成
> `harvest`，也會沿用舊 session 的身份（會看到「harvest 竟然寫得進 exchange」）。換身份測試前要
> `Restart-Service LanmanWorkstation`（或等 session 逾時）再測，否則會誤判權限設定錯誤。

---

## 6. 紅線（不可更動，除非先改本文件並經使用者同意）

1. ❌ **不要把 `shared/tasks`、`task_status.json`、`finance.db` 放上 NAS**（控制面與 SQLite 留本機）。
2. ❌ **不要用 `Everyone` 或弱密碼開分享**（PC2 舊 `Share` 用 `user/abc123`，2026-11-08 仍可從 notebook 讀到，就是反面教材）。
   **也不要跑 `synoacltool -enforce-inherit`**：它會把 ACL 換成 `everyone::allow:rwx…`（所有人完整控制），見 §5.1。
3. ❌ **不要讓 notebook 寫回 PC／NAS 的 exchange**（方向只有 PC → NAS → notebook）。
4. ❌ **不要在 NAS 上跑長時間 AI 批次**（2 GB RAM；額度也是共用同一個帳號）。
5. ❌ **不要刪 `backup\` 的備份**來「重跑一次看起來乾淨」。
6. ❌ **不要動 `/volume1/agent-ops/` 以外、且不在本表登記的東西**（相簿、套件資料、使用者的分享）。

---

## 7. 變更流程（agent 與人都一樣）

```
1) 先在本表加一列（ID／任務／用途／影響／回滾）→ 狀態 pending
2) 動手
3) 回填實際路徑、時間、驗收結果 → 狀態 active
4) 停用時改 retired（不刪列，保留歷史）
```

- 每次變更在 commit message 或 `NAS-PREP.md` 留一行（日期＋做了什麼＋為什麼）。
- 給 agent 的指令一律附「這是 N-xx」，避免同一件事被兩個任務各建一份。

---

## 8. 「NAS 可以裝 opencode 嗎？」評估（2026-11-08）

**結論：技術上可以，但不建議當主要路線。真正的缺口是 SSH 帳號，不是 agent。**

| 面向 | 評估 |
|---|---|
| 平台相容 | ✅ DS718+ 是 **x86_64**，opencode 有 `opencode-linux-x64.tar.gz`（v1.19.5，另有 `baseline`／`musl` 版） |
| 容器 | ✅ Container Manager 官方支援 x86_64 機型；也可用 `node:22`／`debian` 映像 |
| 記憶體 | ⚠ **只有 2 GB**。DSM 常駐 ~500 MB，opencode（Bun）活躍時 300~800 MB；一個 TUI 對話可以，**長上下文／大 repo 會吃緊** |
| 模型額度 | ⚠ 與 PC1／notebook **共用同一個帳號**的免費池與 Go 額度；NAS 上跑不會變多 |
| 上下文 | ❌ NAS 上看不到本 repo 的 `AGENTS.md`／KB／scripts（除非另 clone 一份，那又多一份會分歧的副本） |
| 遠端使用 | ⚠ QuickConnect **不轉 SSH**；外出要先有 Tailscale／VPN 才連得進去 |
| 維護 | ⚠ DSM 升級／套件更新會動到環境；多一個要顧的執行環境 |

### 建議順序

1. **先做（我今天就能做）**：NAS 開一個 **SSH 專用帳號**（或金鑰）給 notebook → 我直接從這裡操作 NAS。
   這樣我用的是**同一份** `AGENTS.md`、`NAS-PREP.md`、`publish_outbox.py`、`nas_sync.py`，
   不需要轉貼、不會出現「兩個 agent 各自記一半」的情況。
2. **再加（可選）**：NAS 裝 **Tailscale** → 外出時 SSH/SMB 都通（也解掉收割「只在家」的限制）。
3. **最後才考慮（可選）**：真的要在 NAS 上有一個常駐 agent，再用 Container Manager 跑 opencode（`N-0x` 登記），
   用途限定「NAS 本地運維」；**不要**拿它處理 KB／影片／知識庫（那些在 notebook）。

> 一句話：**要「精準處理 NAS 問題」，缺的是通道與紀錄，不是多一個 agent。**
> 通道＝SSH；紀錄＝本白皮書的登記表。

---

## 9. 待辦（對應 `NAS-PREP.md` §13）

- [x] S0：建 `exchange`／`backup`／`archive` ＋ `producer`／`harvest`（N-01~N-05）— 2026-11-08 20:17，SMB 五項權限實測通過
- [x] S0：建 `/volume1/agent-ops/`（N-06）— 含 `2026-11-08-nas-s0/README.md`
- [x] S1：notebook 存認證（N-07）— `cmdkey` 已寫入 `harvest`，免 `net use` 可直接讀
- [ ] S1：`python -X utf8 nas_sync.py --check --write-test`（要先設 `OC_NAS_HOST`／`OC_NAS_ROOT`）
- [ ] S1b：**PC1 存 `producer` 認證**（`cmdkey /add:192.168.1.121 /user:producer /pass:<...>`）＋ `publish_outbox.py` 試推一包
- [ ] S1：NAS 裝 Tailscale（N-08，待使用者同意）
- [ ] S2：PC1 影子 mirror（Phase 1）
- [ ] S3：切 `OC_OUTBOX_ROOT(S)` → `harvest --dry-run` 全 `skipped_same`
