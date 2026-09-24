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
**從「## 0c 均線排列速查表」挑選**：偏多組從「強勢股」清單、偏空組從「弱勢股」清單，**清單有多少檔就選多少檔（不硬湊 20 檔）**，中性股不列入。偏多組與偏空組各自涵蓋大型/中型/小型三類（市值參考 input「## 0 現價速查表」的市值欄）：
- 大型：市值 ≥ 800 億
- 中型：市值 100~800 億
- 小型：市值 < 100 億
每組按「值得留意程度」排序。每檔**嚴格**用以下格式（標題行與細節行都要照寫，不可省略任何欄位）：

N. 代碼 名稱｜方向：偏多/偏空｜強度：強/中/弱｜規模：大型/中型/小型｜滿足條件：X/5
- 候選條件：列出滿足哪幾個（從 ①資金位移 ②法人買賣超 ③融資券/三大觸發 ④千張大戶 ⑤催化劑 五個中勾選，寫明條件名）
- 預期：上漲概率 X%（偏空則寫下跌概率）、區間 +X%~+Y%（預期隔日漲跌幅）、vs大盤 跑贏/跑輸/同步
- 出榜依據：條列 **3~4 條**具體實數，**每條都要有數字**，**禁止**寫「法人看好」「資金流入」這種無數字空話，**禁止只寫單一指標**：
  - ①資金位移（verdict=進貨/疑似出貨/惜售/退潮 ＋ 成交值增減 ＋ 股價收紅/收黑；**偏空組若查無資金位移數據，改用「全空排列＋8MA 跌破＋量縮價跌」技術結構當第一條，不強求資金**）
  - ②籌碼指標（三大法人買賣超張數／融資券增減或三大觸發／千張大戶增減 pp，至少擇一）
  - ③量價結構八象限（寫 Q1~Q8 象限＋8MA 站/破＋量增/量縮＋邊際K；**若 input「## 1b」顯示「資料不足」或「無法判讀」，改寫「0b 技術位階」的 MA20 乖離率＋前20日高/低，並註記「（1b 資料不足）」**）
  - ④技術/供需（MA5/MA20 乖離、前高/前低、三盤突破/跌破、大量關鍵K 守住/跌破、上漲角度陡/緩、扣抵）
- 可靠度：高/中/低＋一句話理由（多個指標同步同向者「高」，僅單一指標或訊號互斥者「中/低」）。理由**禁止重複出現「高/中/低」評級字**（例如不可寫「高＋中...」，評級只在最前面標一次）
- 操盤邏輯：一句話（為什麼是這檔、法人明天可能怎麼做）
- 關鍵價位：支撐/壓力（見下方鐵律）
- 催化劑：行事曆/消息/籌碼中支持這方向的因子

「滿足條件 X/5」＝下列 5 個候選條件（①資金位移 ②法人買賣超 ③融資券/三大觸發 ④千張大戶 ⑤催化劑）中，有 X 個同向支持該檔方向。每組排序最前面的 5 檔是你最有把握的「核心推薦」，在股名後加【核心】標記（例：「2330 台積電【核心】」），其餘為觀察名單。

⚠️ 大盤方向一致性鐵律（最重要，不可違反）：
- 先依「## 明日大盤情境」判斷明日大盤偏強/偏弱，個股方向必須與大盤情境自洽。
- 大盤偏弱時，偏多組的 10 檔**每一檔都必須有「逆勢抗跌」獨立依據**（籌碼極度集中、獨立題材催化），否則該檔改列偏空組。
- **「資金位移 verdict=進貨/惜售」是「今日」資金狀態，不是明日漲跌的充分條件**。大盤重挫日，資金流入股照樣被拖累下跌，嚴禁機械式把「進貨」直接翻成「偏多」。
- 產出前自我核對：偏多組每檔是否都有抗跌依據？方向分布是否與「明日大盤情境」一致？

⚠️ 資金板塊權重鐵律（本儀表板核心資訊，不可違反）：
- input「## 1 XQ 盤中快照摘要」的「資金位移（成交值增減前8）」列出 verdict=進貨/惜售/退潮/疑似出貨。**偏多組的 10 檔中，至少 6 檔的資金位移 verdict=進貨或惜售（資金流入、量價配合）**，因為它們是盤面主力資金的落點。
- 但「占榜單」≠「判偏多」：資金流入股的方向（偏多/偏空）須依大盤情境與籌碼判斷，不可一律判偏多。
- 每檔「出榜依據」第一條若來自資金位移，要寫明該股的 verdict 與成交值增減數字，否則視為未遵守。

⚠️ 量價結構互證鐵律（v2 八象限，不可違反）：
- input「## 1b 量價結構判讀」是程式以當日 15分K 算出的供需象限（Q1~Q8）＋量價結構警示（極限大量、大量後未過高→調節、破8MA、邊際K轉弱、Sweep 標籤等），與你的方向互證。
- 若某檔結構警示與你判的方向**相左**（例：判偏多但顯示「⚠偏多vs空方大量（量增價跌+極限大量）」「偏多破8MA」，或判偏空但「偏空vs多頭增量」）→ 該檔「可靠度」一律降為「低」並在「風險與不確定性」點出，**禁止無視結構警報**。
- 「Q8縮量緩跌（多方整理）」屬健康整理，不必然抵觸偏空，可說明為「結構整理待量」。
- 若「## 1b」段不存在或為空，忽略本鐵律。

⚠️ 出榜必含技術/結構依據鐵律（不可違反）：
- 每一檔「出榜依據」**至少要含「量價結構八象限」或「技術位階/供需」其中一類的具體數據**（Q1~Q8 象限、8MA 站/破、MA20 乖離率、前高/前低、三盤突破/跌破、大量關鍵K）。
- 若「## 1b」整段顯示「資料不足」或「無法判讀」，第 ③ 條自動改用「0b 技術位階」並加註「（1b 資料不足）」，不得留空。
- 產出後自我核對：20 檔每一檔第 ③④ 條是否都寫了實數；缺了就重寫該檔，不可跳過。

⚠️ 關鍵價位的鐵律（最重要，不可違反）：
- input 有「## 0b. 技術位階速查表」，列出各股 前收/前高/前低/MA5/MA20/前20日高/前20日低。
- **支撐與壓力必須從這些技術位階中選取**，並在價位後括號標明依據，例：「壓力 2520（前20日高）」「支撐 2380（MA20）」「支撐 2300（前20日低）」。
- 支撐 < 現價 < 壓力，價位應落在前高/前低/MA/前20日高低這些真實位階附近。
- **嚴禁無依據的隨機價位**（例：現價已是 166 元，卻寫「支撐 42 元/壓力 48 元」＝重大錯誤）。
- 若「## 0b」查無該股技術位階，該檔「關鍵價位」一律寫「無技術位階資料，不估價位」，**不許硬編數字**。
- 每寫一檔價位，產出前自我核對一次：價位有標明依據、支撐 < 現價 < 壓力。

挑選條件（依序權重）：
1. 強勢/弱勢趨勢（## 0c 均線排列，硬門檻）第一優先 —— 偏多必須全多排列、偏空必須全空排列，不在清單不選
2. 盤中資金位移（進貨/出貨訊號）在清單內排序 —— 進貨者偏多優先、出貨者偏空優先
3. 法人買賣超與千張大戶增減（籌碼集中）
4. 融資券變化與三大觸發（法人吃貨＝股漲融資減、恐慌殺出＝股跌融資減、斷頭壓力＝股跌融資大減；散戶多空指標）
5. 消息/行事曆催化劑
6. 平衡涵蓋不同族群與大中小型規模，避免集中單一產業或單一規模

⚠️ 強勢/弱勢選股鐵律（最重要，不可違反）：
- 預測榜目標是「**明日日內趨勢明確**」的個股，不是「成交值最大的權值股」。
- **偏多組每一檔都必須是「## 0c」清單內的強勢股（全多排列＋5日量增＋5日累計漲幅≥5%＝正要/剛起漲）**；**偏空組每一檔都必須是弱勢股（全空排列，不要求資金/量）**。**不在清單內的一律不選**。
- **嚴禁**直接拿成交值前 20 名填榜單（那些多半是日K 盤整、均線糾結的權值股）。
- **強勢股到了量縮階段（量縮價漲＝飄/背離、軋空後段）有反轉疑慮，不是首選**；首選是量增起漲、剛突破的標的。
- **弱勢股不要要求資金位移/成交值**——沒有買盤、無量下跌是自然的，不該因「資金」而排除。
- 清單內再依「當沖選榜條件」排序：偏多＝15分K 站上 8MA＋5分K 共振起漲；偏空＝15分K 跌破 8MA＋5分K 共振下跌。
- 選不出足夠趨勢明確的就少列，不可硬湊 20 檔。

## 廖崧沂 2.0 供需三盤戰法（判讀個股方向的總心法，比任何單一指標優先）
- **三盤＝趨勢的最小單位**：三根連續K（日K／15分K 皆可）波段式堆疊。三盤突破（高點越過越高）＝多方攻擊；三盤跌破（低點破越低）＝空方壓制。單根K不是三盤。
- **供需位置先於方向**：需求區＝箱型下緣／大量關鍵K／8>21>55 均線支撐；供給區＝前高／大量區／箱型上緣。在供需位置判斷多空，不追高峰。
- **角度定強弱**：上漲角度陡＋回檔角度緩＝最強；突破後角度上不去（回跌至前高之下）＝走弱別追。角度＝均線斜率，可目測。
- **扣抵預判**：8/21/55 未來若扣高＝均線準備下彎（壓力）；扣低＝準備上揚（支撐）。個股方向須與大盤情境自洽。
- **大量關鍵K＝生死線**：攻擊的大量關鍵K守住＝波段續抱；跌破大量關鍵K且站不回＝方向翻轉、出場。
- **量價互證**：三盤突破＋量增價漲＝攻擊確認；三盤跌破＋量大＝率先開溜。量縮價穩在供需位置等，不追量增高峰。

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
    import time as _time
    client = genai.Client(api_key=_read_key())
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
    last_err = None
    for attempt in range(1, 4):
        try:
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
        except Exception as e:
            last_err = e
            print(f"[report] Gemini 呼叫失敗（第 {attempt}/3 次）：{type(e).__name__} {e}")
            if attempt < 3:
                _time.sleep(20 * attempt)
    raise RuntimeError(f"Gemini 呼叫 3 次皆失敗：{last_err}")


def _audit_feedback():
    """讀預測績效稽核歷史＋盤中 15 分兌現軌跡＋預判正確率，回饋 Gemini。"""
    try:
        import predict_audit
        fb = predict_audit.recent_summary(5)
        parts = [s for s in (predict_audit.intraday_summary(2),
                             predict_audit.intraday_direction_accuracy(2)[0]) if s]
        extra = "\n\n".join(parts)
        if extra:
            fb = extra if (not fb or "尚無" in fb) else fb + "\n\n" + extra
        return fb
    except Exception:
        return ""


_TECH_MARKERS = ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "8MA", "MA5", "MA20", "MA10",
                 "乖離", "前20日", "前高", "前低", "量增", "量縮", "均線", "三盤", "大量關鍵K",
                 "角度", "扣抵", "象限")


def _parse_alignment(input_text):
    """從 input 的「## 0c 均線排列速查表」解析 強勢股/弱勢股 股號集合。"""
    import re
    strong, weak = set(), set()
    cur = None
    for ln in input_text.splitlines():
        s = ln.strip()
        if s.startswith("- 強勢股"):
            cur = "strong"
        elif s.startswith("- 弱勢股"):
            cur = "weak"
        elif s.startswith("- "):
            cur = None
        if cur in ("strong", "weak"):
            (strong if cur == "strong" else weak).update(re.findall(r"\d{4,5}", s))
    return strong, weak


def _validate_board(text, strong_codes=None, weak_codes=None):
    """檢查預測榜：①出榜依據含八象限/技術 ②偏多在強勢清單、偏空在弱勢清單。"""
    try:
        import predict_audit
        stocks = predict_audit.parse_forecast(text)
    except Exception as e:
        return [("", "", f"無法解析預測榜：{type(e).__name__}")]
    issues = []
    for s in stocks:
        basis = " ".join(s.get("basis") or [])
        if not basis.strip():
            issues.append((s["code"], s["name"], "出榜依據留空"))
            continue
        if not any(k in basis for k in _TECH_MARKERS):
            issues.append((s["code"], s["name"], "出榜依據缺八象限/技術位階依據"))
        d = s.get("dir", "")
        code = s.get("code", "")
        if strong_codes and weak_codes:
            if "偏多" in d and code not in strong_codes:
                issues.append((code, s["name"], "偏多但不在 0c 強勢（全多排列）清單"))
            elif "偏空" in d and code not in weak_codes:
                issues.append((code, s["name"], "偏空但不在 0c 弱勢（全空排列）清單"))
    return issues


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
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

    strong_codes, weak_codes = _parse_alignment(input_text)

    fb = _audit_feedback()
    if fb and "尚無" not in fb:
        input_text = "【歷史預測績效檢討（供你修正本次預測）】\n" + fb + "\n\n" + input_text

    print(f"[report] 呼叫 Gemini（{args.slot}）…")
    text, model = call_gemini(input_text, args.slot)

    MAX_RETRY = 3
    issues = _validate_board(text, strong_codes, weak_codes)
    for attempt in range(1, MAX_RETRY):
        if not issues:
            break
        fix_lines = "\n".join(f"- {c} {n}：{r}" for c, n, r in issues)
        input_text = (input_text
                      + "\n\n## 你上一版的預測榜不合格，必須整份重寫\n"
                      + "以下各檔未達標，請修正後重新輸出完整報告：①偏多必須在「## 0c」強勢股（全多排列）清單內、偏空必須在弱勢股（全空排列）清單內，不在清單的一律換掉；②每檔出榜依據要含 ③量價結構八象限 或 ④技術/供需 實數（Q1~Q8／MA20 乖離／前高前低／三盤／大量關鍵K）：\n"
                      + fix_lines)
        print(f"[report] 驗證未過（{len(issues)} 檔未達標），重跑第 {attempt + 1} 次…")
        text, model = call_gemini(input_text, args.slot)
        issues = _validate_board(text, strong_codes, weak_codes)

    if issues:
        print(f"[report] ⚠ 重試 {MAX_RETRY} 次後仍有 {len(issues)} 檔未填完整：")
        for c, n, r in issues:
            print(f"    - {c} {n}：{r}")

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