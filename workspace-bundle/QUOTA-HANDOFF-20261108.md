# 額度撞牆接手包（2026-11-08 版）

> 用途：免費池撞牆時，**30 秒內存證 → 切 Go → 把第 4 節整段貼給接手 agent**。
> 長期規則與歷史實測見 `workspace-bundle/HANDOFF-QUOTA-TAKEOVER.md`；本檔只放「今天可直接照做」的版本。
> 全程繁體中文、指令一律 `python -X utf8`（cp950 會讓中文輸出變亂碼）。

---

## 0. 三句話

1. 今天（11-08 00:29 起算，**數字會隨對話一直增加，要用時請現場跑 `oc_usage.py`**）
   基準：日累計 251→265 次、5h 101→115/200（約 50~58%）；上次撞牆 11-06 14:11（當時日 270）。
2. 撞牆當下：**先跑第 2 節整段指令存證**，再切 `opencode-go/deepseek-v4.1-flash`。
3. 切完把**第 4 節整段**貼給新 agent，不要讓它重新摸索。

---

## 1. 撞牆前的基準數字（2026-11-08 00:29 第一次量測／00:35 複量）

| 項目 | 值 |
|---|---|
| 免費池日累計（08:01 起算） | **251 次 → 265 次**（對話每回合都會增加） |
| 5h 滾動窗 | **101 / 200（50%）→ 115 / 200（58%）** |
| 24h | 251 → 265 次 |
| 主用模型 | `opencode/big-pickle`（全部次數） |
| Go 5h / 週 / 月 | 0% / 0% / **100%（rate-limited，重置 11/10 22:32）** |
| 上次被拒 | 2026-11-06 14:11:01（當時日 270、5h 141、24h 423） |

**判讀**：今天已經逼近「上次撞牆的 270」，**日／帳號層級那道隨時可能觸發**；
5h 只有 5 成多，所以這次若被拒，**幾乎可以確定不是 5h 閘門**（正好是難得的對照資料）。

---

## 2. 撞牆當下：30 秒存證（先做這個，再切模型）

在 PowerShell 貼這整段（會自動用當下時間命名）：

```powershell
cd D:\AI-Agent-Workspace
$ts = Get-Date -Format "yyyyMMdd_HHmm"
python -X utf8 oc_usage.py --json | Out-File -Encoding utf8 "working\quota_wall_$ts.json"
python -X utf8 oc_usage.py --full | Out-File -Encoding utf8 "working\quota_wall_$ts.txt"
Select-String -Path D:\opencode-data\opencode\log\opencode.log `
    -Pattern "level=ERROR.*(QuotaExceeded|Free usage limit reached)" -Encoding utf8 |
    Where-Object { $_.Line -notmatch 'spawning process' } |
    Select-Object -Last 3 | ForEach-Object { $_.Line } |
    Out-File -Encoding utf8 -Append "working\quota_wall_$ts.txt"
"存證完成：working\quota_wall_$ts.json / .txt"
```

> 兩個必須保留的細節（2026-11-08 實測踩到，改掉會存到垃圾）：
> 1. `ForEach-Object { $_.Line }` 不能省：`Select-String` 回的是 MatchInfo 物件，
>    直接接 `Out-File` 會寫成表格檢視，尾巴變成空白／亂碼。
> 2. `Where-Object -notmatch 'spawning process'` 不能省：opencode.log 也會記下**我們自己跑的指令**，
>    指令字串裡若含 `Free usage limit` 就會變成假警報（會污染 `oc_usage.py` 的「上次被拒」）。

然後把下面這張表填好（貼在對話或 `docs/incidents/` 新檔）：

```
撞牆時間（本機） ：
撞牆時間（UTC）   ：
錯誤訊息原文      ：You've used today's free messages. They reset at ____
                  ／Free usage limit reached（log 版沒有 reset at）
宣告 reset 時間   ：
當下 5h           ：____ / 200
當下日累計        ：____ 次（08:01 起算）
當下 24h          ：____ 次
當下主用模型      ：opencode/____
撞牆前最後一件事  ：（例：正在 push 7f22a49／正在跑 harvest --dry-run）
快照檔            ：working\quota_wall________.json / .txt
```

> 一次撞牆只存一份。若只是**暫時性**（重試一次就成功，如 11-03 09:23→09:25），
> 在表上註明「暫時性、重試即成功」，不要當成真撞牆。

---

## 3. 切模型（不斷線）

```
/models                              ← 選 opencode-go / deepseek-v4.1-flash
```
或直接：
```
/model opencode-go/deepseek-v4.1-flash
```

切完立刻驗證（Go 行應該開始出現 5h 次數、免費行停止增加）：

```powershell
python -X utf8 oc_usage.py
```

注意：
- Go **月額度 100% `rate-limited`（重置 11/10 22:32）**，實測仍可請求，但**不要開長批次**（一次幾十支任務）。
- 切換後免費池不再累加 → 之後算「恢復」時要註明「撞牆後未再使用免費池」，否則會高估恢復速度。

---

## 4. 貼給接手 agent 的話（整段複製）

```
【接手】這台是 notebook（LAPTOP-VAG7LBD2），專案在 D:\AI-Agent-Workspace。
免費池剛撞牆，已切到 opencode-go/deepseek-v4.1-flash。指令一律 python -X utf8。

請先讀這三份，不要重新摸索：
1. workspace-bundle/QUOTA-HANDOFF-20261108.md（本檔：撞牆紀錄格式＋今日狀態）
2. workspace-bundle/NAS-PREP.md（NAS 預備計畫，尚未上線）
3. AGENTS.md（專案規則）

【今日已完成，不要重做】
1. PC1→notebook 收割鏈已驗證：PC1 publish 22:50 rc=0（0 新／306 未變）、
   notebook harvest 23:10 rc=0（skipped_same 108｜offline 2）、連結修正 rc=0。
2. HarvestPCDaily 電池限制已修（StartWhenAvailable=True、允許電池、不因電池中止）。
3. NAS 預備已實作並推上 GitHub：commit 7f22a49
   （config.py／harvest_pc.py／publish_outbox.py／nas_sync.py／NAS-PREP.md／agents.md）。
   未設定 OC_* 環境變數時行為完全不變。
4. SensebarVaultSync 已停用（sync.bat 是 LF 換行＋if 區塊，cmd 解析失敗，
   2026-07-11 建立至今從未成功推送過）。

【目前待決，等使用者指示，不要自行動手】
A. 是否讓 repo 只留程式碼：把 Clipping/（147 檔）、AI生成影片/（194 檔）
   以 git rm -r --cached 取消追蹤並加進 .gitignore（本機檔案不刪）。
B. 是否移除 stock-monitor-bundle.zip（12.9MB）、stock-monitor.zip、stock-monitor-new.zip。
C. AI_Agent_Worker 排程從未執行（開機觸發＋Interactive 登入），是否改成登入時啟動。
D. 收割 pc2（WinError 1326，無認證）、pc3（未設 Tailscale IP）仍 offline，不影響 rc。

【額度紀錄（撞牆當下填入）】
撞牆時間：____（UTC ____）｜錯誤訊息原文：____｜reset at：____
當下 5h：____/200｜日：____｜24h：____｜快照：working\quota_wall____.json / .txt

【規則】
- 不要重跑已完成任務（worker 多半 skip-if-exists，重跑會重送 Whisper／Gemini）。
- shared\tasks\task_*.json 才是任務狀態來源，task_status.json 只是鏡像。
- PC 不寫 notebook 的 KB；方向永遠是 notebook 去 pull。
- 免費池數字是本機估算，Go 是官方精確值；不要用本地次數預測還會不會被拒。
```

---

## 5. 觀察數據（留給事後分析）

### 5.1 檔名規則

| 檔案 | 內容 |
|---|---|
| `working\quota_wall_YYYYMMDD_HHMM.json` | `oc_usage.py --json` 快照（撞牆瞬間） |
| `working\quota_wall_YYYYMMDD_HHMM.txt` | `--full` 輸出＋log 的 `Free usage limit` 原文 |
| `docs/incidents/YYYY-MM-DD_quota-wall.md`（可選） | 第 2 節表格＋後續恢復紀錄 |

### 5.2 恢復後補記（只記上界）

```
恢復後首次成功（本機）：____
（這是上界，不是恢復點；額度可能更早就好了，只是沒人測）
當時 5h：____｜日：____｜是否早於 08:01：是／否
```

### 5.3 事後分析（0 成本，唯讀）

```powershell
python -X utf8 oc_usage.py --full
```

要回答的三個問題：

1. **這次是不是 5h 閘門？** 撞牆時 5h 若 < 200（今天 101 起跳），就不是。
   只有在 5h ≥ 230 時才值得懷疑是 5h 閘門。
2. **日／帳號閘門的觀察帶有沒有變？** 已知撞牆日累計：270（11-06）、326（11-04）、328（11-06）、204（11-03）。
   **沒有固定門檻**，只能持續記錄、不能拿來預測。
3. **恢復是不是發生在 08:01？** 若在 08:01 前就恢復、且當時 5h 已掉到 <100 → 偏向 24h／帳號滾動成分。

### 5.4 判讀限制（已寫死，不要推翻）

- 5h 的 200 **不是硬線**（11-06 實測 213 仍正常）。
- 本地次數**不足以**解釋伺服器判定（11-06 同一天 5h 213 正常、141 卻被拒）。
- 因此**不要**用「還能用幾次」預測；被拒就存證 → 切 Go → 繼續。

---

## 6. 撞牆時不要做的事

| ❌ | 原因 |
|---|---|
| 用「下次開對話的時間」當恢復點 | 那是作息，不是額度；只能寫「上界」 |
| 撞牆後大量重跑已完成任務 | 重送 Whisper／Gemini，把恢復後額度再燒一次 |
| 為了省額度跳過 `--dry-run` | 會污染 KB 正本，修回來更貴 |
| 用 `Set-Content -Encoding UTF8` 寫 JSON | PS 5.1 會加 BOM，`json.loads` 直接爆（讀取請用 `utf-8-sig`） |
| 只改 `task_status.json` 當任務狀態 | `shared\tasks` 才是 worker 讀的來源，會被覆蓋回去 |
