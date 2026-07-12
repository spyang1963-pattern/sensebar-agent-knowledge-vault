---
name: smart-cut
description: 智能剪口播。當使用者提供影片原始檔並要求「剪掉沒講話的片段」「去靜音」「剪口播」「自動剪輯」「像剪映那樣自動去停頓」時使用此技能。底層走 auto-editor（開源），偵測音量低於閾值的片段並剪掉，輸出只有人聲的版本。
---

# smart-cut：智能剪口播

## 何時觸發
使用者提供 mp4/mov/mkv/webm 原始影片，並要求：
- 剪口播、去靜音、剪掉沒聲音的部分
- 自動剪輯、像剪映那樣自動去停頓

## 原理
偵測音訊中音量低於閾值的片段 → 剪掉 → 把剩下的片段 concat 回成一支影片。

## 前置需求
```powershell
pip install auto-editor
ffmpeg -version  # auto-editor 內部會呼叫 ffmpeg
```

## 參數說明

| 參數 | 預設 | 說明 |
|------|------|------|
| `--threshold` | `0.04` | 音量門檻（4%）。越大剪越多：0.04=寬鬆，0.06=嚴格，0.08=極嚴 |
| `--margin` | `0.2s` | 每段語音前後保留緩衝。停頓多→拉到 0.3s |

## 標準呼叫
```powershell
python ".opencode\skills\smart-cut\scripts\smart_cut.py" `
  "raw\<影片代號>\原始.mp4" `
  --out "working\<影片代號>\<影片代號>.cut.mp4" `
  --threshold 0.05 `
  --margin "0.2s"
```

## 輸出
- `<影片代號>.cut.mp4` — 去靜音後的影片
- 統計回報：`原長 18:42 → 新長 12:15（剪掉 34.6%）`

## 與其他 Skill 的銜接
1. **smart-cut**（本 Skill）→ 產出剪好的影片
2. → 抽音訊（`ffmpeg -i x.cut.mp4 -vn -ar 16000 x.cut.wav`）
3. → **audio-to-srt** Skill：對 cut 後的音訊轉字幕

## 踩坑
- VFR（可變幀率）原始檔 → smart_cut.py 內建自動轉 CFR
- 不要對「原始檔」轉字幕再剪片 → 時間碼會錯位
- 音樂段落會被誤判為靜音 → 需手動處理
