# 額度撞牆半自動 SOP（2026-11-10 改版）

> 任何機器／任何 agent 撞到免費額度被拒，照這頁做，不用重新分析。
> 一句話結論：**沒有可預測的門檻**；被拒 → 存快照 → 切 Go → 繼續，不要猜剩幾次。
> 本頁取代 2026-11-06 版（那版附帶的 PC1 收割 Step 4~6 已全部完成，不再保留）。

## 1. 被拒長相（兩種，原文照抄）

**① UI／TUI**（伺服器回的，含宣告的重置時間）：

```
You've used today's free messages. They reset at 08:01
```

- `reset at` 會漂移（已見 08:55 → 08:01 → 08:36），以**最近一次**為準；要改就改
  `oc_usage.py` 的 `FREE_DAY_RESET_H/M`，或 `--reset-at`／環境變數 `OC_FREE_RESET`。

**② 本機 log**（UTC、`Z` 結尾、**沒有** reset at）：

```
AI.Error.QuotaExceeded: Free usage limit reached. Free models work in OpenCode ...
```

- 抓法：`Select-String -Path D:\opencode-data\opencode\log\opencode.log -Pattern "Free usage limit" -Encoding utf8`
- 同一句也可能是暫時性（被拒後 2 分鐘重試即成功過），所以先存快照再說。

## 2. 照做（約 5 分鐘）

```powershell
cd D:\AI-Agent-Workspace
# 1) 存快照（檔名＝撞牆時間，一次撞牆一個檔）
python -X utf8 oc_usage.py --json | Out-File -Encoding utf8 working\quota_wall_YYYYMMDD_HHmm.json
python -X utf8 oc_usage.py --full
# 2) 切模型後繼續做手上的事（不斷線、不重跑已完成任務）
#    /model opencode-go/deepseek-v4.1-flash
python -X utf8 oc_usage.py      # 補記切換時刻＋Go 起始用量
```

- Go monthly 100% ⛔（rate-limited）實測**仍可請求**（超額計費），但別開長批次。
- **不重跑已完成任務**（worker 多半 skip-if-exists，重跑會重送 Whisper／Gemini）。
- **不跳過 `--dry-run`**（污染 KB 正本比額度貴）。
- 回報一行（貼對話即可）：
  `撞牆 HH:MM（5h __/200、日 __、24h __）；reset at __；快照 working\quota_wall____.json；已切 Go`

## 3. 已知事實（2026-11-10 彙整，勿重新推論）

**撞牆實測表（本機 DB 回算）**

| 撞牆（本機） | 日（宣告換日起） | 5h | 24h |
|---|---|---|---|
| 11-02 17:09 | 1 | 1 | 233 |
| 11-03 02:00 | 204 | 203 | 204 |
| 11-04 21:31 | 326 | 142 | 459 |
| 11-06 03:59 | 328 | 137 | 328 |
| 11-06 14:11 | 270 | 141 | 423 |
| 11-08 02:31 | 278 | 128 | — |
| 11-08 21:33 | 195 | 195 | 323 |
| 11-09 17:15 | 220 | 220 | 415 |

- **無固定門檻**：日 1／195／220／270／278／330／337、5h 1~233 都撞過；同支模型
  同日 5h 213 正常回話、5h 141 被拒 ⇒ 本地次數不足以預測伺服器判定（重試／token 加權不明）。
- **免費池跨機共用**（同帳號／同公開 IP `218.173.23.78`）：11-08 notebook 撞牆後，
  PC1 **從未使用、也沒登入**，一貼任務立刻被拒 ⇒ 本機 `opencode.db` 只能算「這台用掉幾次」，
  不是剩餘量；**多機任務一開始就用 Go**。
- **實務紅線**：日累計 250 以上＝高風險；長任務（轉錄、整批修檔、多工具 agent）直接用 Go。
- **恢復**：唯一可信是訊息宣告的 `reset at`（多次＝隔天上午 08:0x~08:55）。
  「撞牆後第一次成功」只是**上界**（使用者刻意延後才回來用），不是恢復時刻，勿拿來推論。
- **5h 與日額度並存**：5h 是「現在往前 5 小時」滾動窗（DB 計算、不隨換日重算），只當
  短期爆量指標；日累計才是實務瓶頸。
- **Go 精確額度（零 token）**：`GET https://opencode.ai/inference/go/v1/usage`
  （Bearer＝auth.json 的 Go key）→ `rolling/weekly/monthly {percent,status,resetsAt}`。
- 平時看額度用 `oc_widget.py` 常駐小窗（不經模型、不花配額）；對話中打 `/usage`。

## 4. 禁止事項

| ❌ | 原因 |
|---|---|
| 拿本地 5h／日次數預測「還能用幾次」 | 跨機共用池＋伺服器計數方式不明，必失準 |
| 撞牆後大量重跑已完成任務 | 重送 Whisper／Gemini，恢復後額度再燒一次 |
| 用「我下次開對話的時間」當恢復點 | 那是使用者作息，只能記上界 |
| 為省額度跳過 `--dry-run` | 汙染 KB 正本，修回來更貴 |
| 每回合跑 `oc_usage.py` 查額度 | 本身就是一次模型請求；改用 `oc_widget.py` |
