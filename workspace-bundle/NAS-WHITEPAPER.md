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
| `archive` | `/volume1/archive` | `producer` RW／`harvest` RW（2026-11-08 21:0x 加開，用來把 notebook 的成品搬上去）／`@administrators` RW／`guest` 拒絕 | `videos/`、`notebook-results/`（6.06 GB／1691 個 mp4·mp3） |
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

**2026-11-08 21:1x 實際灌進去的資料（第一份完整備份）**

| 目的地 | 內容 | 體積 | 驗收 |
|---|---|---|---|
| `backup\knowledge-base` | 全部 KB | **4540 檔／140.5 MB** | 兩邊檔數、大小一致（robocopy `rc=0/1`、0 失敗） |
| `backup\finance_db\finance.db` | 事件 51,580／快照 16,251 | **57.3 MB** | `PRAGMA quick_check=ok`＋**逐列雜湊與本機完全相同**（用 SQLite backup API，不是直接 copy） |
| `backup\shared` | `tasks`／`results` 的 json·srt·md（**不含影音**） | **7957 檔／165.2 MB** | 兩邊一致 |
| `archive\notebook-results` | 原本在 notebook `shared\notebook\results` 的 mp4/mp3 | **1691 檔／6.06 GB** | 搬完本機 0 檔、NAS 1691 檔；**D: 可用空間 32.3 → 38.4 GB** |
| `/volume1` 總用量 | 上述全部 | **6.4 GB／7.0 TB（1%）** | `df` |

### 1.4 已安裝套件（16 個，**沒有** Container Manager／Docker／Tailscale）

`SMBService`、`SynoFinder`、`Python2`、`StorageManager`、`ActiveInsight`、`ScsiTarget`、
`SynoAnalytics`、`USBCopy`、`SynoOnlinePack_v2`、`SecureSignIn`、`OAuthService`、`Python3.9`、
`HybridShare`、`QuickConnect`、`FileStation`、`SupportService`

### 1.5 網路與通道

| 項目 | 值 | 備註 |
|---|---|---|
| 網路 | `192.168.1.121` | 建議路由器做 DHCP 保留（固定 IP） |
| 遠端 | 已設 **QuickConnect** | 只給 DSM 網頁／手機 App 用，**不能 SSH** |
| Tailscale | **已加入 tailnet**（`spyang1963@gmail.com`），NAS tailnet IP **`100.65.113.20`**、MagicDNS `datanas.tail6b5f31.ts.net`（2026-11-08 22:0x） | 外出時改用這個 IP／名稱，不要用 `192.168.1.121` |
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
| N-02 | `\\NAS\backup` = `/volume1/backup` | 每日備份 | 收 `knowledge-base\`（4540 檔／140.5 MB）、`finance_db\finance.db`（57.3 MB，已驗證）、`shared\`（7957 檔／165.2 MB） | 沒有備份；不影響生產 | 刪分享；備份檔另存 | **active**（2026-11-08 20:17；21:1x 首次完整備份完成） |
| N-03 | `\\NAS\archive` = `/volume1/archive`（`videos\`、`notebook-results\`） | 冷片歸檔＋成品離線 | `notebook-results\`＝notebook 的 mp4/mp3（1691 檔／6.06 GB）；`videos\`＝30 天以上冷片（空） | 只影響空間回收，不影響流程 | 刪分享；影片搬回 | **active**（2026-11-08 20:17；21:00 搬入 6.06 GB） |
| N-04 | 使用者 `producer`（uid 1027，shell `/sbin/nologin`） | publish（PC1/2/3） | 只給各機寫 `exchange\<machine>\outbox`；**不能寫 backup** | publish 失敗（`WinError 1326`／權限被拒） | 停用帳號即可 | **active**（2026-11-08 20:16） |
| N-05 | 使用者 `harvest`（uid 1028，shell `/sbin/nologin`） | 收割（notebook） | **唯讀** `exchange\`、可寫 `backup\` | 收割失敗 | 降權或停用 | **active**（2026-11-08 20:16） |
| N-06 | `/volume1/agent-ops/`（NAS 本機，目前只有 `2026-11-08-nas-s0/README.md`） | 所有 agent 在 NAS 上的操作 | **agent 專用工作目錄**：腳本、日誌、暫存，一個任務一個子目錄 | 清掉會失去 agent 操作紀錄；**不含任何使用者的資料** | 整個目錄刪除即可 | **active**（2026-11-08 20:16） |
| N-07 | notebook `cmdkey` 認證（`192.168.1.121`、`100.65.113.20`、`datanas.tail6b5f31.ts.net` → `harvest`） | S1 | 讓 SMB 免密碼重連（重開機後仍有效）；在家走 LAN、外出走 tailnet | 收割／備份失敗（`WinError 1326`） | `cmdkey /delete:<host>` | **active**（2026-11-08 20:2x；22:1x 加 tailnet IP 與 FQDN） |
| N-08 | NAS 上的 Tailscale（套件 `Tailscale` 1.104.5-700104005，官方 DSM7 SPK） | 遠端收割 | 讓 notebook 外出也能讀 NAS | 停用＝外出時收割 `offline`（不會壞資料） | `synopkg uninstall Tailscale` | **active（2026-11-08 21:31 安裝，待使用者開授權連結）** |
| N-09 | notebook `%USERPROFILE%\.nas_admin`（`yang` 帳號／密碼，**repo 外**） | S0 建置 | 讓 agent 用 SSH 登入 NAS 做一次性設定 | 刪掉只是 agent 失去登入能力，**不影響 NAS 運作**；外流＝對方有 DSM 權限 | 直接刪檔；或改密碼／停用帳號 | **active**（2026-11-08；**S1 完成後刪除或改用金鑰**） |
| N-10 | notebook `%USERPROFILE%\.nas_accounts.json`（`producer`／`harvest` 密碼，**repo 外**） | S0 建置 | 讓 PC1（producer）與 notebook（harvest）取用各自密碼 | 刪掉不會壞 NAS，只是要重設密碼（`synouser --setpw`）；外流＝可寫 exchange／backup | 刪檔＋改密碼 | **active**（2026-11-08 20:16） |
| N-11 | notebook `nas_backup.py` ＋ `backup_daily.bat`（日誌 `logs\nas_backup.log`、`logs\backup_daily.log`） | 每日備份（N-02 的執行者） | KB／finance.db／shared → NAS `backup\`；`finance.db` 用 SQLite backup API（一致性快照）＋`quick_check`＋筆數驗證 | 沒跑＝沒有新備份（舊備份還在，不會壞資料） | 刪掉腳本；備份檔不動 | **active**（2026-11-08 21:14 手動驗收；21:39 建立排程 `NasBackupDaily` 每天 **01:30**，試跑 rc=0） |
| N-12 | NAS：`/var/packages/Tailscale`（套件本體）、`/var/packages/Tailscale/conf/privilege`（**改成 root 執行**）、`/etc/systemd/system/pkgctl-Tailscale.service.d/tun-device.conf`（agent 建立）、`/dev/net/tun`（`tun.ko`） | N-08 的實作 | 讓 Tailscale 用**核心網路**（`tailscale0 = 100.65.113.20`）而不是 `--tun=userspace-networking`；後者遠端無法用 SMB 連入 | 刪 drop-in 或還原 privilege → 遠端 SMB 失效（其餘不影響）；**套件升級會覆蓋 privilege，升級後要重套** | 還原 `privilege.orig.json`（在 agent-ops）＋刪 drop-in＋`daemon-reload`；必要時 `synopkg uninstall Tailscale` | **active**（2026-11-08 22:0x，tailnet SMB 五項實測通過） |
| H-01 | `/volume1/資料分享區/finance/workspace/`（59 MB） | 2026-07 舊計畫殘留 | 舊版 repo 副本，**不是** agent 建的、也不是生產資料 | 已刪；不影響任何現行流程 | 無（已無需求） | **retired**（2026-11-08 21:01 刪除） |
| H-02 | `/volume1/資料分享區/finance/pip/`（24 MB） | 2026-07 舊計畫殘留 | Python pip 安裝殘留 | 已刪 | 無 | **retired**（2026-11-08 21:01 刪除） |

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

### 5.2 NAS 上的 Tailscale（N-08／N-12，2026-11-08 實作）

**做法**：用 Tailscale **官方 DSM7 SPK**（不需要 Docker／Container Manager）＋一個 systemd drop-in。

| 步驟 | 指令／路徑 |
|---|---|
| 下載 | `https://pkgs.tailscale.com/stable/tailscale-x86_64-<ver>-700104005-dsm7.spk`（檔名版本要含 `700104005`） |
| 安裝 | `synopkg install <spk>`；套件名稱是 **`Tailscale`（大寫 T）**，`synopkg status tailscale` 會回 `non_installed` |
| 啟動 | `synopkg start Tailscale`；執行檔在 `/var/packages/Tailscale/target/bin/` |
| 狀態／登入 | `/var/packages/Tailscale/target/bin/tailscale status` ／ `tailscale login`（會印一次性網址，**要人到瀏覽器授權**） |

⚠ **DSM7 最大的坑：套件預設用 userspace 網路**
`start-stop-status` 裡有一段：DSM7 且 `/dev/net/tun` 不存在時，自動加 `--tun=userspace-networking`。
後果是**沒有 `tailscale0` 介面**，只能單向對外，遠端 **無法用 SMB 連進 NAS**（收割／備份就沒用）。

修法（N-12，已建立）：

```ini
# /etc/systemd/system/pkgctl-Tailscale.service.d/tun-device.conf
[Service]
ExecStartPre=/bin/bash -c 'insmod /lib/modules/tun.ko 2>/dev/null || true; mkdir -p /dev/net; [ -e /dev/net/tun ] || mknod /dev/net/tun c 10 200; chmod 666 /dev/net/tun'
```

- 這台 `tun.ko` 在 **`/lib/modules/tun.ko`**（不在 `.../kernel/drivers/net/`），`insmod` 前若已載入會回
  `File exists`，視為正常。
- `/dev` 是 devtmpfs，**重開機就會消失**；靠上面的 `ExecStartPre` 在套件啟動前重建。
- 建完 drop-in 要 `systemctl daemon-reload`，再 `synopkg restart Tailscale`。

**⚠ 第二個坑（更難查）：套件預設以 `tailscale` 使用者執行，`CapEff=0`**
就算 `/dev/net/tun` 存在，`tailscaled` 仍會回
`wgengine.NewUserspaceEngine(tun "tailscale0") error: tstun.New(...): operation not permitted`，
然後**默默退回 userspace 網路**（log 只寫一行，狀態仍顯示 `Running`、tailnet IP 也拿得到，
但 `ip link` 永遠沒有 `tailscale0`，遠端 SMB 一定連不進來）。

已修（N-12）：把套件權限改成 root 執行（DSM 的 `privilege` 檔支援 `defaults.run-as`）：

```json
// /var/packages/Tailscale/conf/privilege（原始檔備份在 agent-ops/2026-11-08-nas-tailscale/privilege.orig.json）
{
  "defaults": {
    "run-as": "root"
  }
}
```

- 只加 `"executable": [{"relpath": "bin/tailscaled", "run-as": "root"}]` **實測無效**（仍是 `tailscale`、`CapEff=0`）。
- 改完 `synopkg stop/start Tailscale`；驗收 `ps -o user= -p $(cat .../tailscaled.pid)` 必須是 **root**，
  且 `grep CapEff /proc/<pid>/status` 非 0、`ip addr show tailscale0` 有 `100.65.113.20`。
- **套件升級會覆蓋 `/var/packages/Tailscale/conf/privilege`**：升級後若 `tailscale0` 又不見，先查這個檔。

- 驗收：`ps aux | grep tailscaled` **不能**出現 `--tun=userspace-networking`；登入後 `ip addr show tailscale0` 要有介面。
- 其他限制：Synology 版**不支援 `--accept-routes`**（會直接報錯），所以不要拿它當 subnet router；
  但當「一般節點」讓 notebook 直接連它的 tailnet IP 是沒問題的。
- 記憶體實測：`tailscaled` 約 **36~38 MB**，2 GB 的機器完全夠。
- 移除：刪 drop-in → `systemctl daemon-reload` → `synopkg uninstall Tailscale`（不會動到任何分享）。

> 目前狀態（2026-11-08 22:1x）：**已完成**。`tailscale0 = 100.65.113.20`，notebook 以 `harvest`
> 走 tailnet 實測：讀 `exchange` ✅、寫 `exchange` ❌（正確）、寫 `backup` ✅、讀 `archive` ✅。
> ⚠ SMB **用名稱**（`\\datanas\…`）會失敗；`\\datanas.tail6b5f31.ts.net\…` 則**要先有該名稱的
> `cmdkey`** 才會通（已加入）。日常請優先用 **IP**。

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
- [x] S1：`nas_sync.py --check`（設 `OC_NAS_HOST=192.168.1.121`、`OC_NAS_ROOT=\\192.168.1.121\exchange`）
      → **rc=0**、SMB 445 OK、`pc1`／`pc2`／`pc3` 皆 OK。
      `--write-test` 在 **notebook 一定會失敗（這是對的）**：notebook 是 `harvest`，本來就唯讀 exchange；
      該工具會把本機當產出機，所以還會顯示「缺 `exchange\notebook\outbox`」——**預期行為，不要因此去建 notebook 目錄**。
- [ ] S1b：**PC1 存 `producer` 認證**：把 repo 的 `set_nas_producer_cred.bat` 帶到 PC1 執行一次
      （會 `cmdkey /add:192.168.1.121 /user:producer`，密碼在 notebook 的 `%USERPROFILE%\.nas_accounts.json`），
      再從 PC1 跑 `publish_outbox.py --dry-run` → 試推一包
- [x] **P0 備份（2026-11-08 21:1x 完成）**：KB 4540 檔／140.5 MB、`finance.db` 57.3 MB（逐列雜湊相同）、
      `shared` 7957 檔／165.2 MB；腳本 `nas_backup.py`＋`backup_daily.bat` 可重跑（第二次 `rc=0` 無變更）
- [x] **P0 備份排程**：`NasBackupDaily` **每天 01:30**（2026-11-08 21:39 建立，試跑 `LastTaskResult=0`）。
      設定與 `HarvestPCDaily` 同：`hpspy`／Interactive／`StartWhenAvailable`／可電池／`IgnoreNew`／6 小時上限。
      未登入 Windows 時不會跑，下次登入由 `StartWhenAvailable` 補跑
- [x] **6.06 GB 影音搬到 `archive\notebook-results`**（本機 0 檔、NAS 1691 檔、D: +6.1 GB）
      **程式面已確認沒有依賴**：`scheduler.py` 收割只讀 `.md`／`.srt`／`.txt`；
      `ipc.py.upload_results()` 是通用複製（不挑副檔名，少媒體不影響）；
      `sync_results.py` 是 PC→KB 同步、與 `results\` 媒體無關；GUI 沒有用 `results\*.mp4` 做預覽。
      ⇒ 只有「人想直接點開舊成品影片」時要改去 NAS 拿，程式流程不受影響。
- [x] **H-01／H-02 刪除**（83 MB；`資料分享區` 現在是空的）
- [x] S1：NAS 裝 Tailscale（N-08／N-12）— **完成**：`tailscale0 = 100.65.113.20`，
      notebook 以 `harvest` 走 tailnet 實測（讀 exchange ✅／寫 exchange ❌／寫 backup ✅／讀 archive ✅）
- [ ] S2：PC1 影子 mirror（Phase 1）
- [ ] S3：切 `OC_OUTBOX_ROOT(S)` → `harvest --dry-run` 全 `skipped_same`
