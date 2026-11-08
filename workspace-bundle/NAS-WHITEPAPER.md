# NAS 白皮書（Synology DS718+）

> 版本：**v0.1**（2026-11-08）
> 撰寫：notebook 上的 agent（`opencode`），依 2026-11-08 實測與 repo 清查結果
> 定位：**NAS 的「現況＋登記簿＋紅線」**。要動 NAS 之前先看這份；切換步驟看 `NAS-PREP.md`。
> 這份文件的目標只有一個：**任何人（含 agent）都能一眼看出「這個東西是誰建的、為什麼、亂動會壞什麼」。**

---

## 0. 三句話

1. NAS 是 **Synology DS718+**（x86_64 / 2 GB RAM），已在 `192.168.1.121` 運作，SMB／DSM／SSH 都開著，
   但 **`exchange`／`backup`／`archive` 三個分享與 `producer`／`harvest` 帳號還沒建**（見 §5 登記表）。
2. 它的角色是 **交換區＋備份**，**不是**執行機：`shared/tasks`、`finance.db`、SQLite **一律不上 NAS**。
3. 2026-07 那份 NAS 計畫（SQLite 上 NAS、NAS 跑收集排程）**已被 11 月決策推翻**，只留歷史價值（見 §3）。

---

## 1. 硬體與服務現況（2026-11-08 實測）

| 項目 | 值 | 備註 |
|---|---|---|
| 型號 | Synology **DS718+**（2017，2 bay） | |
| CPU | **Intel Celeron J3455**（4 核，x86_64，含 AES-NI） | 是 x86_64，**不是 ARM**（容器／Linux 版程式都能用） |
| RAM | **2 GB** DDR3L（單槽，最高 6 GB） | **最大的硬體限制**，別在上面常駐重服務 |
| 網路 | `192.168.1.121` | 建議路由器做 DHCP 保留（固定 IP） |
| 遠端 | 已設 **QuickConnect** | 只給 DSM 網頁／手機 App 用，**不能 SSH** |
| 開啟的埠（實測） | `22`（SSH）、`445`（SMB）、`5000`（DSM） | 三者皆 True |
| DSM API | `:5000/webapi/query.cgi` → `{"success":true}` | 系統正常運行 |
| `\\192.168.1.121\exchange`／`\backup` | **False** | 分享還沒建，或沒有該機認證（`net view` 回系統錯誤 5） |
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
| N-01 | `\\NAS\exchange\` | 跨機收割（Phase 1/2） | PC 產出包的中央交換區 | 收割全部 `offline`；PC 的 publish 失敗 | 刪分享、把 `OC_OUTBOX_ROOT(S)` 拿掉即回本機路徑 | pending |
| N-02 | `\\NAS\backup\` | 每日備份 | 收 `knowledge-base\`、`finance.db`、`shared\` 備份 | 沒有備份；不影響生產 | 刪分享；備份檔另存 | pending |
| N-03 | `\\NAS\archive\videos\` | 冷片歸檔 | 30 天以上影片離線存放 | 只影響空間回收，不影響流程 | 刪分享；影片搬回 | pending |
| N-04 | 使用者 `producer` | publish（PC1/2/3） | 只給各機寫自己的 `exchange\<machine>` | publish 失敗（`WinError 1326`／權限被拒） | 停用帳號即可 | pending |
| N-05 | 使用者 `harvest` | 收割（notebook） | **唯讀** `exchange\`、可寫 `backup\` | 收割失敗；給太大權限則有寫壞風險 | 降權或停用 | pending |
| N-06 | `/volume1/agent-ops/`（NAS 本機） | 所有 agent 在 NAS 上的操作 | **agent 專用工作目錄**：腳本、日誌、暫存，一個任務一個子目錄 | 清掉會失去 agent 操作紀錄；**不含任何使用者的資料** | 整個目錄刪除即可 | pending |
| N-07 | notebook `cmdkey` 認證（`192.168.1.121`） | S1 | 讓 SMB 免密碼重連 | 收割／備份失敗（重開機後尤其） | `cmdkey /delete:192.168.1.121` | pending |
| N-08 | NAS 上的 Tailscale（套件） | 遠端收割 | 讓 notebook 外出也能讀 NAS | 外出時收割 `offline`（不會壞資料） | 移除套件 | pending |

> **N-06 是關鍵**：agent 在 NAS 上建立的東西**一律**放 `/volume1/agent-ops/<任務代號>/`，
> 並在該子目錄放一個 `README.md` 寫「為什麼建、對應哪個 repo 任務、怎麼刪」。
> 這樣「哪些檔案是 agent 建的」不需要靠記憶，看目錄就知道；使用者的資料（`exchange`／`backup`／`archive`／相簿…）**永遠不在這裡**。

---

## 6. 紅線（不可更動，除非先改本文件並經使用者同意）

1. ❌ **不要把 `shared/tasks`、`task_status.json`、`finance.db` 放上 NAS**（控制面與 SQLite 留本機）。
2. ❌ **不要用 `Everyone` 或弱密碼開分享**（PC2 舊 `Share` 用 `user/abc123`，2026-11-08 仍可從 notebook 讀到，就是反面教材）。
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

- [ ] S0：建 `exchange`／`backup`／`archive` ＋ `producer`／`harvest`（本表 N-01~N-05）
- [ ] S0：建 `/volume1/agent-ops/`（N-06）
- [ ] S1：notebook 存認證（N-07）→ `nas_sync.py --check --write-test`
- [ ] S1：NAS 裝 Tailscale（N-08）
- [ ] S2：PC1 影子 mirror（Phase 1）
- [ ] S3：切 `OC_OUTBOX_ROOT(S)` → `harvest --dry-run` 全 `skipped_same`
