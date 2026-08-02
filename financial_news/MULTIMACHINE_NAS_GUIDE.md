# 多機協同 + NAS 啟用指南

## 一、先找到你的 NAS

NAS 目前掃不到，代表**沒開機或沒接網路線**。請依序檢查：

### 1. 找機器本體
NAS 外觀像「小型的直立式/橫放式主機」，通常有幾個**硬碟插槽**（可抽換硬碟），
常見廠牌：**Synology（群暉）、QNAP（威聯通）、ASUSTOR、ASUS**。
- 找找書桌下、電視櫃、路由器附近、主機旁有沒有這種裝置
- 上面通常有電源鍵和網路孔（RJ45）

### 2. 接上電源與網路
1. 插電源線
2. 接網路線：NAS 網路孔 → 家用路由器（分享器）任一 LAN 孔
3. 按電源鍵開機（等 1-2 分鐘開機完成）

### 3. 確認抓到
在筆電執行（本專案目錄）：
```powershell
ping <NAS-IP>
```
開機後告訴我**廠牌型號**（機器上的貼紙或型號標籤），我給你啟用步驟。
常見型號範例：`Synology DS220+`、`QNAP TS-464`、`ASUSTOR AS5202T`。

> 若完全不確定是哪一台，也可以把機器外觀拍下來給我看。

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

> 待你提供廠牌型號後，我會給 Synology 或 QNAP 的專屬設定步驟
> （開啟 SMB 分享、建立共用資料夾、設定開機自動啟動排程）。
