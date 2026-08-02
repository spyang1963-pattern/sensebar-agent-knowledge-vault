# Telegram 通知設定（3 分鐘完成）

## 步驟 1：建立 Bot
1. 打開 Telegram，搜尋 **@BotFather**（官方藍色勾勾）
2. 傳送 `/newbot`
3. 依指示取名，例如：`Sensebar Finance Alert`
4. 最後會給一組 **token**（格式 `123456789:ABC...`），複製下來

## 步驟 2：取得你的 Chat ID
1. 打開 Telegram，搜尋你的 bot 名稱並**開始**（傳任意訊息給它）
2. 開啟瀏覽器連到：
   `https://api.telegram.org/bot<你的token>/getUpdates`
3. 看到 `"chat":{"id": 數字...}` 那段，數字就是 **chat_id**

## 步驟 3：填入設定
開啟 `D:\AI-Agent-Workspace\financial_news\notifier.py`，
在檔案上方找這兩行，填入：

```python
TELEGRAM_TOKEN = "你的token"
TELEGRAM_CHAT_ID = "你的chat_id"
```

## 步驟 4：測試
```powershell
cd D:\AI-Agent-Workspace\financial_news
python notifier.py --test-tg
```

手機收到「【測試】金融新聞系統 Telegram 通知已上線！」即成功。

## 給夥伴
每個人要使用時：把 bot 加進群組，取群組的 chat_id（負數），
即可讓多位夥伴同時收到推播。
