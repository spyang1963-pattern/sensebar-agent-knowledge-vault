# 多機協同 + NAS 啟用指南

## 一、你的 NAS：Synology DS718+ 啟用步驟

**型號確認**：DS718+（2017年款，2 bay、Intel Celeron J3455 四核、2GB RAM、雙網孔）。
這台當金融系統的 7×24 收集站非常夠用。

### 步驟 1：接上電源與網路
1. 插電源線
2. **網路線接「LAN 1」孔**（DS718+ 有兩個網孔，接任一即可，LAN1 習慣接分享器）
3. 網路線另一頭 → 家用路由器（分享器）任一 LAN 孔
4. 按電源鍵開機（等 1-2 分鐘）

### 步驟 2：找到 NAS 的 IP
在筆電執行：
```powershell
# 掃描 192.168.0.x 網段
python -X utf8 -c "import socket; [print('found:', f'192.168.0.{i}') for i in range(1,255) if socket.socket().connect_ex(('192.168.0.'+str(i), 5000))==0]"
```
或直接看路由器管理頁面的「已連線裝置」列表（找 Synology / DS718+ 字樣）。
常見：`192.168.0.100`~`192.168.0.150` 之間。

### 步驟 3：首次登入 DSM
1. 瀏覽器開 `http://<NAS-IP>:5000`
2. 首次會引導安裝 **DSM**（Synology 作業系統，需下載安裝，約 10-20 分鐘）
3. 建立管理者帳號（例如 `admin`）與密碼
4. 建立 Storage Pool + Volume（若硬碟是舊的且要清空重用，選 RAID 或 Basic）

### 步驟 4：開啟 SMB 檔案分享（供筆電/PC 讀寫）
1. DSM 桌面 → **控制台 → 檔案服務 → SMB** → 啟用 SMB 服務
2. **控制台 → 共用資料夾 → 新增**：建立 `share`（權限給你的帳號 讀寫）
3. 在筆電試連：
   ```powershell
   net use Z: \\<NAS-IP>\share
   ```
   或檔案總管網址列輸入 `\\<NAS-IP>\share`

## 二、NAS 啟用後的定位

| 功能 | 用途 |
|------|------|
| 中央資料庫 | 金融新聞 SQLite 放 NAS，三機共用同一份資料 |
| 檔案中心 | KB、報表、備份統一存放 |
| 7×24 排程 | 讓 NAS 自己跑收集（每30分鐘），不需開電腦 |
| 備份 | 每日自動備份三機工作檔 |

## 三、三機分工建議

```
筆電（收成站）   ← 你現在這台，跑儀表板 + 每日報告
PC1（分析站）    ← 跑 Gemini 分析批次 + 報告產生
PC2（收集站）    ← 跑 news_collector 收集（低負載，可常駐）

同步：所有程式碼與資料用 GitHub 私人 repo 同步（現有 repo）
      SQLite 資料庫放 NAS 共用（啟用後）
```

## 四、立即可以做的（不等 NAS）

1. **其他機器部署**：在 PC1/PC2 上
   ```powershell
   git clone https://github.com/spyang1963-pattern/sensebar-agent-knowledge-vault.git
   cd sensebar-agent-knowledge-vault
   pip install flask feedparser requests PyYAML google-genai
   python financial_news\pipeline.py --collect   # PC2 可每30分跑這個
   python financial_news\pipeline.py --analyze --batch 8   # PC1 可跑這個
   ```
2. **錯開時間**：不同機器設不同排程時間，避免同時抓同一批新聞（DB 已去重，沒影響）

## 五、NAS 教學（啟用後）

> 依步驟 1-4 完成後，回到這裡確認，我幫你把 SQLite 資料庫與排程搬上 NAS。

### DS718+ 啟用後可做的事
| 功能 | 作法 |
|------|------|
| 中央資料庫 | 把 `finance.db` 放到 NAS 共用資料夾，三機指向同一份 |
| 收集排程 | 在 NAS 上安裝 Python（套件中心 → 安裝 Python3），設定任務排程器每 30 分跑 `pipeline.py --collect` |
| 檔案中心 | KB 報告同步到 NAS `share\finance_reports` |
| 每日備份 | DSM 控制台 → 備份與還原，排程備份三機工作檔 |

### 多機協同最終架構
```
┌─ 筆電：儀表板 + 每日報告 + Obsidian 閱讀
├─ PC1 ：Gemini 分析批次
├─ PC2 ：收集站
└─ NAS DS718+：中央 SQLite + 7×24 收集排程 + 每日備份（Always On）
         ▲ 三機程式碼用 GitHub 同步，資料庫集中 NAS
```

> 完成步驟 1-4 後告訴我 NAS 的 IP，我繼續把資料庫遷移和 NAS 排程設定好。
