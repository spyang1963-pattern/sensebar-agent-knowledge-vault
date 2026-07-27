# 2026-07-27 重要修正記錄

## KB 路徑系統重構
| 項目 | 修正前 | 修正後 |
|------|--------|--------|
| KB 路徑基準 | `knowledge-base/trading/` | `knowledge-base/`（根目錄） |
| 自動帶入 | `金融交易/理周學院/{course}` | `knowledge-base/{course}` |
| 跨碟支援 | 無 | 有（fallback 到 course/basename） |

## KB 結構重整
| 舊路徑 | 新路徑 |
|--------|--------|
| `trading/*` | `金融交易/理周學院/*` |
| `!!海龍王/` | `金融交易/!!海龍王/` |
| `AI agent-sensebar/` | `人工智慧/AI agent-sensebar/` |
| `traditional-kline/` | 已刪除 |
| `youtube-clips/` | 已刪除 |

## Worker 控制流程
| 項目 | 修正前 | 修正後 |
|------|--------|--------|
| 啟動方式 | 自動搶單 | 手動按「可加入任務」 |
| 預設狀態 | Worker 運行中 | Worker 待命 |
| 停止方式 | 按「停止工作指派」 | 按「停止工作指派」 |

## 新功能
1. **KB 路徑可配置**：建立任務時可指定 `kb_subpath`，決定收成位置
2. **自動清理課程名稱**：去掉 `!!` 前綴和 `-` 後的副標題
3. **Worker 手動控制**：建立任務後不會自動執行，需手動啟動

## Bug 修復
1. `auto_fill_from_path`：正確清理 `!!` 前綴和 `-` 後副標題
2. `scheduler.py kb_dir`：從 `trading/` 改為根目錄
3. Worker 預設不啟動：避免任務建立後立即執行

## 備份位置
- 系統備份：`D:\AI-Agent-Workspace\backup_20260727_181000\`
- KB 備份：`D:\備份\knowledge-base_20260726\`

## Git 提交
- Commit: `feat: KB path configurable, worker manual control, auto-fill cleanup`
- 推送到 GitHub: ✅
