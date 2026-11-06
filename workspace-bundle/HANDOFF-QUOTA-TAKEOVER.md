# 額度撞牆接手 Handoff（順便驗證 5h 滾動窗）

> 建立：2026-11-06　對象：**notebook 上的下一個 agent（自稱 deepseek v4.1 flash 接手時）**
> 用途：免費池撞牆時，不用重新摸索就能接著做 PC1 收割，並把撞牆瞬間的數字留下來，
> 用來檢驗「5h 滾動窗 ~200 次」到底是不是獨立的一道閘門。
> 全程繁體中文、回報簡短、指令一律 `python -X utf8 ...`（cp950 會讓中文輸出變亂碼）。

---

## 0. 三句話版本

1. **現在的狀態**：PC1 收割走到 Step 3 完成（唯讀盤點＋`git pull`＋`publish_outbox.py --dry-run`＝58 包），
   Step 4（Obsidian vault）／Step 5（正式打包）／Step 6（SMB＋收割）還沒做。
2. **撞牆時怎麼做**：切 `opencode-go/deepseek-v4.1-flash` 繼續做，**不要**停止工作、也不要重跑已完成任務。
3. **要記的四個數字**：撞牆時間、錯誤訊息原文、當下 5h 次數、當下日累計（08:01 起算）。缺一項就無法驗證。

---

## 1. 免費額度怎麼看（兩道閘門並存）

```powershell
cd D:\AI-Agent-Workspace
python -X utf8 oc_usage.py          # 兩行：免費池＋Go
python -X utf8 oc_usage.py --full   # 加上各模型用量、被拒紀錄
```

輸出長這樣（2026-11-06 實例）：

```
免費 日 149 次（08:01 換日）｜5h 149/200（74%）｜上次被拒 11-06 03:59（當時累計 330 次）
      兩道閘門並存：5h 滾動窗 ~200 次；日/帳號層級更高（11-04 5h 153 仍被拒時日 337）
Go   5h 0% · 週 10% · 月 100% ⛔→11/10 22:32
```

| 數字 | 意思 | 可信度 |
|---|---|---|
| `日 N 次（08:01 換日）` | 從**伺服器宣告的重置時間**起算的免費池用量 | 本機估算（DB assistant steps） |
| `5h M/200` | 現在往前推 5 小時內的用量，**滾動、不隨 08:01 重算** | 本機估算；200 是觀測值，**不是硬線** |
| `Go 月 100% ⛔` | Go 官方精確值；`rate-limited` 實測仍可請求（超額計費） | 官方 API，零 token |

**已知事實（不要重新推論）**

- 撞牆有兩種訊息，**原文照抄**（不要改寫，靠它的 `reset at` 反推換日時間）：

  **① 伺服器回的額度訊息（UI／TUI 看得到，含 `reset at`）**
  ```
  You've used today's free messages. They reset at 08:55
  ```
  ```
  You've used today's free messages. They reset at 上午8:01
  ```
  - 第一句是 2026-11-04 21:43（本機）被拒時宣告的，當時據此把換日時間設成 08:55。
  - 第二句是 2026-11-06 03:59（本機）被拒時宣告的，**最近一次的宣告值＝08:01**
    （`oc_usage.py` 的 `FREE_DAY_RESET_H/M = 8/1` 就是照這個改的）。
  - 宣告值會變，**以最近一次為準**；要改常數或 `--reset-at 08:01`／`OC_FREE_RESET`。

  **② 本機 log 記到的錯誤（`D:\opencode-data\opencode\log\opencode.log`，UTC、`Z` 結尾）**
  ```
  timestamp=2026-11-06T06:11:01.918Z level=ERROR run=a4654eae message="Failed to drain Session" cause="AI.Error: Free usage limit reached. Free models work in OpenCode (https://opencode.ai); subscribe to OpenCode Go to keep going: https://opencode.ai/go
      at Oae (B:/~BUN/root/chunk-0z87y99c.js:3:3633)
      ...
    [cause]: AI.Error.QuotaExceeded: Free usage limit reached. Free models work in OpenCode (https://opencode.ai); subscribe to OpenCode Go to keep going: https://opencode.ai/go
  ```
  - 這句**沒有** `reset at`（所以只看 log 推不出換日時間）；`reset at` 只在 UI 訊息裡。
  - log 時間是 **UTC**：`06:11Z` ＝ 本機 **14:11**；`2026-11-05T19:59Z` ＝ 本機 11-06 03:59。
  - 抓法：`Select-String -Path D:\opencode-data\opencode\log\opencode.log -Pattern "Free usage limit" -Encoding utf8`
  - 同一句也可能只是**暫時性**（2026-11-03 09:23 被拒、09:25 重試即成功），所以被拒當下先存快照再看。

- 2026-10-23 改制後，**沒有任何一次成功的 5h 窗超過 233 次**；三次撞牆落在 5h 205~232。
- 但也出現過「5h 只有 139／153／1 次就撞牆」（日累計 330／337／234）→ **另有一道日／帳號層級閘門**。
- 日累計可以超過 200 不撞牆（11-03 當日 264 次、5h 最高 133）。
- **5h 的 200 不是硬線（2026-11-06 12:30 實測）**：5h 衝到 **213（106%）** 仍正常回話，
  之後自然回落到 157。⇒ 5h 只當「短期爆量」指標，**不能**用它預測撞牆；日累計才是瓶頸。
  判讀表裡的「5h ≥ 200 → 5h 閘門成立」要改成「5h ≥ 230 才值得懷疑是 5h 閘門」。

### 撞牆實測表（本機 DB 回算，2026-11-06 補）

| 撞牆（本機） | 日（08:01 起） | 5h | 24h | 主用模型 |
|---|---|---|---|---|
| 11-02 17:09 | 0 | 0 | 233 | opencode/big-pickle |
| 11-03 02:00 | 204 | 203 | 204 | opencode/big-pickle |
| 11-04 21:31 | 326 | 142 | 459 | opencode/big-pickle |
| 11-06 03:59 | 328 | 137 | 328 | opencode/big-pickle |
| 11-06 14:11 | 270 | 141 | 423 | opencode/big-pickle |

回算指令（唯讀）：`python -X utf8 oc_usage.py --full`，或直接查
`session_message` 的 `json_extract(data,'$.model.id')`；時間戳是 epoch ms。

**從這張表只能得到三個結論（都別再往外推）：**

1. **沒有一個固定門檻**：日 270 / 326 / 328、24h 204 / 423 / 459 都撞過 ⇒ 用「日累計到 330 才會爆」
   去預測**會失準**（今天 14:11 就是 270 爆的）。
2. **5h 本地值 137～142 連續三次一致**（11-04、11-06×2）很可疑，但**不能用來證明 5h 是硬線**：
   同一天 13:15 本地 5h ＝ **213** 仍正常回話、14:11 本地 5h ＝ 141 卻被拒 ⇒ 本地次數
   **不足以解釋**伺服器端的判定（合理猜測：伺服器把重試／中斷的步驟也算進去，或按 token 加權）。
3. **實務做法只有一個**：被拒就切 `opencode-go/deepseek-v4.1-flash` 繼續做，
   被拒當下先存快照，**不要**再花時間猜門檻。
- **恢復時間不可推論**：`11-06 08:13`、`11-04 09:47` 都是使用者刻意延後才開對話，不是額度恢復時刻。
  唯一可信的是伺服器在錯誤訊息裡宣告的 `reset at HH:MM`。

---

## 2. 撞牆時：先記錄，再切 Go

### 2.1 立刻存證（30 秒）

```powershell
cd D:\AI-Agent-Workspace
python -X utf8 oc_usage.py --json | Out-File -Encoding utf8 working\quota_wall_20261106_0359.json
python -X utf8 oc_usage.py --full
```

- 檔名放**撞牆的實際時間**，一次撞牆一個檔（同一波被拒只算一次）。
- 不要用 `> "$env:TEMP\x.txt"`：PS 5.1 會用 cp950 解讀 Python 的 UTF-8 輸出，變成不可逆亂碼。
- 記錄表格（貼在本次對話或 `docs/incidents/` 新檔）：

```
撞牆時間（本機） ：
撞牆時間（UTC）   ：
錯誤訊息原文      ：You've used today's free messages. They reset at ____
                  ／Free usage limit reached
宣告 reset 時間   ：
當下 5h           ：____ / 200
當下日累計        ：____ 次（08:01 起算）
當下 24h          ：____ 次
當下主用模型      ：opencode/____
快照檔            ：working\quota_wall________.json
```

### 2.2 切模型（不斷線）

```
/model opencode-go/deepseek-v4.1-flash
```

- 之後所有請求走 Go，**不佔免費池**（`oc_usage.py` 會顯示「同視窗另有 Go 呼叫 N 次」）。
- Go 月額度目前 100% ⛔→11/10 22:32，實測仍可請求，但**別開長批次**（一次跑幾十支任務）。
- 切完先跑一次 `python oc_usage.py`，把「切換時刻＋Go 起始用量」也補進記錄。

### 2.3 撞牆後照常做的事

- 繼續 Step 4～6（下面第 4 節），這些都是**本機檔案操作＋一次 Git／SMB 指令**，
  真正吃模型的地方只有「你要判斷輸出對不對」。
- **不要**為了省額度跳過 `--dry-run`（跳過的代價是污染 KB 正本，比額度貴）。
- **不要**重跑已完成的任務（worker 多半 skip-if-exists，重跑會重送 Whisper／Gemini）。

---

## 3. 怎麼證明／否證「5h 滾動窗」（恢復後才做）

免費池恢復後（任一免費模型能回話即可，用一句「test」測，不要用長任務測），補記：

```
恢復後首次成功（本機）：____
（這是**上界**，不是恢復點；額度可能在更早就好了，只是沒人測）
```

### 判讀表

| 撞牆時 5h（本地） | 是否等到 08:01 才恢復 | 結論 |
|---|---|---|
| ≥ 230 | 任意 | **5h 閘門成立**（第一次拿到直接證據；200～213 已實測不會被拒） |
| < 200 | 是（撐到 08:01 後） | 撞到**日／帳號閘門**，5h 不是瓶頸 |
| < 200 | 否，半天內自行恢復 | 存在**滾動成分**（5h 或 24h）→ 用下面方法分辨 |

**2026-11-06 14:11 實測已把這張表打殘**：日 270、5h 141、24h 423 就被拒，
同一天 13:15（5h 213）卻正常。⇒ 本地次數**不足以**定位門檻，判讀表只能當「事後歸類」，
**不要**拿它預測「還能用幾次」。要做的只有：被拒 → 存快照 → 切 Go → 繼續。

### 分辨 5h 還是 24h（事後用 DB 回算，0 成本）

1. 用快照裡的 `last_hit.at` 當 T。
2. 查 T 之前 5h 內、T 之前 24h 內各有多少次免費呼叫（`oc_usage.py --full` 已印 24h）。
3. 找「恢復時刻往前推 5h」那條界線：如果恢復**(a)** 發生在 08:01 之前，且
   **(b)** 當時 5h 視窗裡的次數剛好掉到 ~200 以下 → 5h 滾動窗就是那道閘門。
4. 如果 5h 早就掉到很低（例如 <100）卻仍被拒，而 24h 仍高 → 是 24h／帳號層級。

**注意偏差**：撞牆後切 Go，免費池用量就停止累加，恢復會比「持續用免費」更早。
記錄時要註明「撞牆後未再使用免費池」，否則會高估恢復速度。

---

## 4. 接手後要做的步驟（PC1 收割，未完成部分）

> 完整背景：`workspace-bundle/PC1-AGENT-BRIEF.md`（PC1 端）、`STEP7-HARVEST-DESIGN.md`（架構）。
> PC1 已回報：`A. KB 1412 md / 280 srt / 280 docx`、`youtube-clips 176 md = 62 支影片`、
> `dry-run 成功 58｜跳過 109｜失敗 0`。

### Step 4（PC1，零風險）：Obsidian 指本機 KB

1. Obsidian → **Open folder as vault** → `D:\AI-Agent-Workspace\knowledge-base`
2. 命名 `AI-Agent-KB (PC1)`
3. 驗收：左側看得到 `youtube-clips`；點開任一 `.md` 內文正常；搜一個內文詞找得到。

❌ 不要指到 `\\100.111.44.63\...`（SMB 當 vault 會卡、斷線會壞索引、兩邊互蓋）。
需要 Clipping 就開第二個 vault 指 `D:\AI-Agent-Workspace\Clipping`，不要用 junction。

### Step 5（PC1）：正式打包

```powershell
cd D:\AI-Agent-Workspace
python -X utf8 publish_outbox.py
python -X utf8 -c "import pathlib; o=pathlib.Path('shared/pc1/outbox'); d=[p for p in o.iterdir() if (p/'manifest.json').exists()]; print('完整包', len(d))"
```

驗收：完整包 = **58**（dry-run 相同）；隨機開一個 `manifest.json` 確認 `schema=1`、`video_id`、`kb_subdir`、`files`。

### Step 6（PC1 需要管理員；目前卡在這）

- 方案 a（建議）：請管理員跑一次
  ```powershell
  New-SmbShare -Name "AI-Agent-Workspace" -Path "D:\AI-Agent-Workspace" -ReadAccess "Everyone"
  icacls "D:\AI-Agent-Workspace" /grant "*S-1-1-0:(OI)(CI)(RX)" /T /C /Q
  ```
- 方案 b（不提權）：`mklink /J "D:\Share\pc1-outbox" "D:\AI-Agent-Workspace\shared\pc1\outbox"`，
  notebook 從 `\\100.84.223.110\Share\pc1-outbox` 收。

notebook 端（先 dry-run 對帳，再正式）：

```powershell
cd D:\AI-Agent-Workspace
python -X utf8 harvest_pc.py --dry-run
python -X utf8 harvest_pc.py          # 正式；衝突會丟 knowledge-base\_harvest_conflicts\pc1\<tid>\
```

驗收：包數一致、`working\harvest_ledger.json` 有紀錄、重跑一次全部 `skipped_same`（冪等）。

### Step 7（順手查）

62 支 KB 影片 vs 58 筆 youtube 任務，差 4 支。查那 4 支「有 KB 條目但沒有任務」的來歷
（舊機器手動處理？別台收成？），不要直接重跑。

---

## 5. 禁止事項（撞牆時最容易犯）

| ❌ | 原因 |
|---|---|
| 用「我下次開對話的時間」當恢復點 | 那是使用者作息，不是額度；只能寫「上界」 |
| 撞牆後大量重跑已完成任務 | 重送 Whisper／Gemini，把恢復後額度再燒一次 |
| 為了省額度跳過 `--dry-run` / `--force` 硬打包 | 會污染 KB 正本，修回來更貴 |
| 手改 `task_status.json` 當成任務狀態 | `shared\tasks` 才是 worker 讀的來源，會被覆蓋回去 |
| 用 `Set-Content -Encoding UTF8` 寫 JSON | PS 5.1 加 BOM，`json.loads` 直接爆 |
| PC1 寫入 notebook 的 KB | 正本只有 notebook 能寫；方向永遠是 notebook 來 pull |

---

## 6. 回報格式（給接手者，貼這段就好）

```
【額度】撞牆 ____（5h ____/200、日 ____、24h ____）；訊息：____；reset at ____
        已切 opencode-go/deepseek-v4.1-flash；快照 working\quota_wall________.json
【恢復】首次成功 ____（上界）；當時 5h ____、日 ____；是否早於 08:01：是/否
【判讀】5h 閘門：成立／日閘門／滾動成分（5h 或 24h）
【進度】Step 4 __／Step 5 __（包數 __）／Step 6 __（方式 a/b）
【阻礙】____
```
