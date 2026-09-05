# Autonomy Layer（自主任務層）

通解架構：在本機（Notebook）交付任務 → 任何 PC 接收後**自動執行、自癒、通知**，不須人在場轉貼指令。

## 一、原理（三根柱子）

1. **交付（git）**：任務＝一份 `missions\*.json`（manifest）。本機 commit → 目標機 `Autonomy_Guard` 每日 05:45 起自動 `git pull` → 程式自動送達。
2. **執行（runner）**：每份 manifest 對應一個排程任務 `Autonomy_<name>`，固定呼叫通用執行器 `runner.py`（鎖檔防重入、超時、狀態回寫）。
3. **自癒＋通知（self_heal）**：看門狗每 30 分檢查所有任務——卡死（lock 過齡）→ 強制終止＋重跑；逾時未產出 → 自動補跑；連敗 → 暫停補跑並 Telegram 告警。

## 二、manifest 格式（新任務＝寫一份這個）

```json
{
  "name": "finance-pipeline",
  "description": "金融新聞 30 分滾動",
  "workdir": "D:\\sensebar-agent-knowledge-vault\\financial_news",
  "command": ["python", "-X", "utf8", "pipeline.py", "--full", "--batch", "150", "--time-budget", "480"],
  "schedule": { "kind": "interval", "minutes": 30, "start": "00:00" },
  "timeout_min": 75,
  "log": "D:\\...\\logs\\autonomy\\finance-pipeline.log",
  "notify_on_fail": true
}
```

- `schedule.kind`：`interval`（minutes＋start）或 `daily`（start "HH:MM"）
- `timeout_min`：逾時視為卡住，由看門狗處理
- 路徑一律絕對路徑

## 三、目標機安裝（一次性）

```powershell
cd <目標機>:\sensebar-agent-knowledge-vault\workspace-bundle\infra\autonomy
.\missionctl.ps1 -Action list          # 看現有任務與 missions
.\missionctl.ps1 -Action guard         # 安裝看門狗（每30分，含自動 pull）
.\missionctl.ps1 -Action install -Mission missions\finance-pipeline.json   # 各任務
```

> 會彈一次 Windows 密碼視窗（讓任務在未登入也能跑）；不想輸入就取消（改為登入時才跑，功能仍正常）。

## 四、Telegram 通知（選擇性但強烈建議）

在目標機 `C:\Users\<user>\.telegram_env` 放兩行（見 `financial_news\TELEGRAM_SETUP.md` 建立 bot）：

```
TELEGRAM_BOT_TOKEN=<你的bot token>
TELEGRAM_CHAT_ID=<你的chat id>
```

測試：`python notify.py --test`

## 五、常用操作

```powershell
.\missionctl.ps1 -Action run    -Mission finance-pipeline   # 立即觸發一次（測試）
.\missionctl.ps1 -Action selfheal                           # 手動跑看門狗看輸出
.\missionctl.ps1 -Action remove -Mission finance-pipeline   # 移除任務
python self_heal.py --check finance-pipeline                # 看單一任務狀態
```

## 六、狀態與診斷

- `state\<name>.json`：每次執行的 exit/last_complete/fail_streak
- `state\<name>.lock`：執行中鎖檔（看門狗據此偵測卡死）
- `state\_heartbeat.json`：看門狗每輪寫回，供本機 agent 被動掃描診斷（免轉貼 log）
- 任務執行輸出連到 `mission.log\` 路徑（manifest 指定，或 `state\<name>.out.log`）