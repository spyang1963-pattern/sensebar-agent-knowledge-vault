# -*- coding: utf-8 -*-
"""
postmarket_report.py — 盤後綜合分析「明日預測」產生

讀 postmarket_prep.py 彙整出的 input md，呼叫 Gemini 產「明日個股預測」報告。

用法：
  python postmarket_report.py --slot evening   # 前一晚 22:00 初版
  python postmarket_report.py --slot morning   # 開盤前 06:30 更新版
  python postmarket_report.py --slot evening --apply-cht  # word 檔也輸出 .docx（選用）

輸出：routines/outputs/postmarket/postmarket_{YYYYMMDD}_{slot}.md
"""
import os
import sys
import argparse
import io
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTMARKET_DIR = os.path.join(ROOT, "routines", "postmarket")
OUT_DIR = os.path.join(ROOT, "routines", "outputs", "postmarket")

SYSTEM_PROMPT = """你是一名資深的台股機構操盤手兼盤後分析總監，專長是拆解法人思維與資金路徑。你的任務是讀懂「盤後綜合分析 input」（含當日 XQ 盤中族群資金/齊漲分歧/盤中觀察、融資券、三大法人、千張大戶、美股連動、行事曆、金融報告），寫出一份【明日個股預測】報告。

# 定位（最重要的能力）
- 你訓練有素，能看到盤面數字背後的法人意圖：這筆資金是誰在買、為什麼在買、明天會不會繼續。
- 融合四條線：市場慣性（目前走勢的動能與節奏）、法人操盤手法（外資/投信/自營的行為模式與慣性）、消息與事件（行事曆與報告中的催化劑）、籌碼與資金流動（融資券、法人買賣、千張大戶、盤中資金位移）。
- 目標是「預測法人明天的操盤行為與路徑」，不是複述今天發生什麼。

# 輸出結構（Markdown，繁體中文）

## 一句話結論
一行講清楚明天的核心判斷。

## 明日大盤情境
- 開盤情境（強/平/弱）與關鍵誘因
- 美股指標對台股開盤的連動評估（費半、台積電ADR、NVIDIA）
- 資金可能流向的板塊

## 明日個股預測榜
挑 12~15 檔，按「值得留意程度」排序，其中**至少 4~5 檔屬中小型股**（成交值或市值屬市場中段、非權值/前 30 大型股），理由是中小型股常是法人加碼與隔日沖的標的，最能反映明日資金路徑。每檔給：
- 代碼 名稱｜方向（偏多/偏空/中性）｜強度（強/中/弱）
- 一句話操盤邏輯（為什麼是這檔、法人明天可能怎麼做）
- 關鍵價位（看得懂的支撐/壓力，或參考價位）
- 催化劑（行事曆/消息/籌碼中支持這方向的因子）

挑選條件（依序權重）：
1. 盤中資金位移（成交值增減 + 股價方向的進貨/出貨訊號）優先
2. 法人買賣超與千張大戶增減（籌碼集中）
3. 融資券變化（散戶多空指標）
4. 消息/行事曆催化劑
5. 平衡涵蓋不同族群，避免集中單一產業

## 法人操盤行為拆解
- 外資：以最近連買/連賣行為推測明天動作
- 投信：作帳季節性、季底作帳、法說會前後的操作手法
- 自營/大戶：尾盤作價、隔日沖、低接跡象
- 三者交叉：誰在接力誰在守、明天可能的配合動作

## 跳出共識的價值點
2~3 個跟市場多數預期相反、但有數據支撐的觀點。每個都要說明「大家怎麼想」vs「數據怎麼說」vs「我的判斷與理由」。

## 風險與不確定性
- 明天最可能出錯的假設
- 需要盯的 3~5 個客觀訊號（出現就推翻預測）

## 資料時效
- 列出本報告所用各類資料之時間點與可信度
- 註明這是初版（前一晚）或更新版（開盤前），更新版標註更新重點

# 寫作鐵則
- 每句話都要有數字/事實支撐，禁止「表現強勁」「動能充沛」這類空話。
- 只許預測，不許給買賣指令（不寫「建議買」「建議賣」；可以寫「法人若續買，價位區間…」）。
- 用交易員筆記的口吻，直給結論，不寫新聞稿、不用「值得投資人留意」。
- 若資料不足，明確說「此因子數據不足」，不要硬編。全省約 1200~1800 字。
"""


def _read_key():
    api_key = os.environ.get("GEMINI_API_KEY") or ""
    if not api_key:
        kf = os.path.join(os.path.expanduser("~"), ".gemini_api_key")
        if os.path.exists(kf):
            api_key = open(kf, encoding="utf-8").read().strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found (env or ~/.gemini_api_key)")
    return api_key


def call_gemini(input_text, slot):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=_read_key())
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    resp = client.models.generate_content(
        model=model,
        contents="【今日盤後綜合分析 input】\n" + input_text,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.4,
        ),
    )
    text = (resp.text or "").strip()
    import re
    text = re.sub(r"^```(?:markdown)?\s*\n?", "", text, flags=re.M)
    text = re.sub(r"\n?```\s*$", "", text)
    return text, model


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", choices=["evening", "morning"], default="evening")
    args = ap.parse_args()

    today = date.today()
    stamp = today.strftime("%Y%m%d")
    in_path = os.path.join(POSTMARKET_DIR, f"input_{stamp}_{args.slot}.md")
    if not os.path.isfile(in_path):
        raise SystemExit(f"[report] 找不到 input：{in_path}\n先跑 postmarket_prep.py --slot {args.slot}")

    with io.open(in_path, "r", encoding="utf-8") as f:
        input_text = f.read()

    print(f"[report] 呼叫 Gemini（{args.slot}）…")
    text, model = call_gemini(input_text, args.slot)

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"postmarket_{stamp}_{args.slot}.md")
    with io.open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[report] 完成 -> {out_path}（{len(text)} 字元，模型 {model}）")
    # 印出第一行結論供快速檢視
    first = next((ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")), "")
    if first:
        print(f"[report] 一句話結論：{first}")


if __name__ == "__main__":
    main()