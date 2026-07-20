# 通知整合完成摘要

## 已整合的內容

### 時機點（誰會觸發 LINE/Email）
| 觸發時機 | 標題 | 說明 |
|---------|------|------|
| worker 完成一部影片 | `影片處理完成 #N` | 課程名、影片名 |
| worker 完成 sensebar 任務 | `@sensebar 文字稿完成` | 影片名 |
| worker 批次全部跑完 | `Worker 批次完成` | 成功 N / 失敗 N |
| scheduler 掃到新影片 | `新影片 N 部已掃描` | 新增數 |
| scheduler 收成到知識庫 | `知識庫已更新` | 幾部新內容 |
| scheduler 重新分配任務 | (無) | 暫不發，避免干擾 |

### 未整合的（覺得不必要就跳過）
- `--release` 釋放任務 — 管理操作不需通知
- `--redistribute` 重新分配 — 同上
- 磁碟空間警告 — Windows 本機通知即可

## 下一步若要做
1. 把 stock-monitor/config.yaml 的 LINE (channel_access_token) 和 Email (sender_password) 使用環境變數
2. 考慮把 LINE 改為 LINE Notify（比 Messaging API 簡單，但已可 work 就不動）
