# -*- coding: utf-8 -*-
"""
predict_audit.py — 預測榜績效稽核

讀「前一晚 evening 初稿」與「當日 morning 定稿」兩份預測榜，跟「當日收盤」
（最新 breadth 快照的 Close/Chg）比對，計分：
  - 方向命中率（偏多→漲、偏空→跌；中性不計）
  - 價位命中（偏多：突破壓力=2 / 守住區間=1 / 跌破支撐=0；偏空對稱）
  - 可靠度校準（高/中/低 分層的方向命中率）
  - 規模分層命中率
  - 初稿→定稿 變動清單

累積寫入 routines/outputs/audit/audit_history.json，供 dashboard 績效區塊與
postmarket_report.py 回饋 Gemini 使用。

用法：
  python predict_audit.py --date 20260914   # 稽核 20260914 的預測（用當日收盤）
  python predict_audit.py --summary         # 印出最近 5 天績效摘要（給 Gemini）
"""
import os
import re
import sys
import io
import json
import argparse
from datetime import date, timedelta, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROUTINES = os.path.join(ROOT, "routines")
sys.path.insert(0, ROUTINES)

import render_html as rh  # noqa: E402

POSTMARKET_OUT = os.path.join(ROUTINES, "outputs", "postmarket")
AUDIT_DIR = os.path.join(ROUTINES, "outputs", "audit")
AUDIT_FILE = os.path.join(AUDIT_DIR, "audit_history.json")

_STOCK_RE = rh._PM_STOCK_RE
_DIR_RE = rh._PM_DIR_RE
_STR_RE = rh._PM_STR_RE
_SIZE_RE = rh._PM_SIZE_RE


def parse_forecast(md_text):
    """解析預測榜每檔 → list of dict(code,name,dir,strength,size,rel,support,resistance)。"""
    stocks = []
    cur = None
    for ln in md_text.splitlines():
        s = ln.strip()
        if not s:
            continue
        flat = s.replace("**", "").strip()
        m = _STOCK_RE.match(flat)
        if m and m.group(2) and not re.match(r"\d", m.group(2)):
            if cur:
                stocks.append(cur)
            dm = _DIR_RE.search(flat)
            sm = _STR_RE.search(flat)
            szm = _SIZE_RE.search(flat)
            core_name = m.group(2).replace("【核心】", "").replace("[核心]", "").strip()
            cur = {
                "code": m.group(1), "name": core_name,
                "dir": dm.group(1).strip() if dm else "",
                "strength": sm.group(1).strip() if sm else "",
                "size": szm.group(1).strip() if szm else "",
                "stance": "", "lvl_conflict": False,
                "basis": None,
                "rel": "", "support": None, "resistance": None,
                "prob": None, "range_lo": None, "range_hi": None, "vs_market": "",
            }
        elif cur and (s.startswith("-") or s.startswith("·")):
            raw = s.lstrip("-· ").strip()
            mm = re.match(r"^([^：]+)：\s*(.*)$", raw, re.S)
            if not mm:
                if cur.get("basis") is not None:
                    cur["basis"].append(raw)
                continue
            lab = mm.group(1).strip().replace("**", "")
            val = mm.group(2).strip()
            if "出榜依據" in lab:
                cur["basis"] = [val] if val else []
            elif "可靠度" in lab:
                mrel = re.match(r"^([高中低])", val)
                cur["rel"] = mrel.group(1) if mrel else ""
            elif "預期" in lab:
                mp = re.search(r"概率\s*(\d+)\s*%", val)
                if mp:
                    cur["prob"] = int(mp.group(1))
                mi = re.search(r"區間\s*([+\-]?\d+(?:\.\d+)?)%\s*~\s*([+\-]?\d+(?:\.\d+)?)%", val)
                if mi:
                    cur["range_lo"] = float(mi.group(1))
                    cur["range_hi"] = float(mi.group(2))
                mv = re.search(r"vs\s*大盤\s*(跑贏|跑輸|同步)", val)
                if mv:
                    cur["vs_market"] = mv.group(1)
            elif "關鍵價位" in lab:
                ms = re.search(r"支撐\s*([\d,]+\.?\d*)", val)
                mr = re.search(r"壓力\s*([\d,]+\.?\d*)", val)
                if ms:
                    cur["support"] = float(ms.group(1).replace(",", ""))
                if mr:
                    cur["resistance"] = float(mr.group(1).replace(",", ""))
            elif cur.get("basis") is not None and (re.match(r"^\d+[.、)]", lab) or lab[:1] in "①②③④⑤⑥⑦⑧⑨⑩"):
                cur["basis"].append(raw)
        elif cur and cur.get("basis") is not None and (re.match(r"^\d+[.、)]", s) or s[:1] in "①②③④⑤⑥⑦⑧⑨⑩" or ln[:1] in (" ", "\t")):
            cur["basis"].append(s.strip())
    if cur:
        stocks.append(cur)
    return stocks


def _read_md(path):
    if not os.path.isfile(path):
        return None
    with io.open(path, "r", encoding="utf-8") as f:
        return f.read()


def actual_close_map():
    """最新 breadth 快照 {code: (close, chg)}，附快照日期。"""
    out = {}
    stamp = ""
    try:
        snaps = rh.list_snapshots("breadth")
        if not snaps:
            return out, stamp
        stamp, path = snaps.popitem()
        for r in rh.load_csv(path):
            c = r.get("Code")
            if c:
                try:
                    out[str(c).zfill(4)] = (float(r.get("Close", 0) or 0), float(r.get("Chg", 0) or 0))
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass
    return out, stamp


def _dir_hit(stock, chg):
    """方向命中：偏多→chg>0、偏空→chg<0、中性/無→None（不計）。

    規則_08 層級鐵律（稽核閉環掛載 2026-09-20）：
    - 層級一致（dir×stance 同向、可靠度≠低）才算 hit；
    - 層級打架（Gemini 判方向與 15分K stance 相左 → prompt 巢已規定可靠度降為「低」）
      → 不計 hit（層級打架剔除，避免 42.1% 假數字吃進榜單誤判）。
    """
    d = stock.get("dir", "")
    if stock.get("rel") == "低":
        return None
    if "偏多" in d:
        return chg > 0
    if "偏空" in d:
        return chg < 0
    return None


def _price_score(stock, close):
    """價位命中：偏多 突破壓力=2 / 守住區間=1 / 跌破支撐=0；偏空對稱；無價位→None。"""
    sup = stock.get("support")
    res = stock.get("resistance")
    d = stock.get("dir", "")
    if "偏多" in d:
        if res is not None and close >= res:
            return 2
        if sup is not None and close <= sup:
            return 0
        if sup is not None or res is not None:
            return 1
        return None
    if "偏空" in d:
        if sup is not None and close <= sup:
            return 2
        if res is not None and close >= res:
            return 0
        if sup is not None or res is not None:
            return 1
        return None
    return None


def _diff(evening_stocks, morning_stocks):
    """初稿→定稿 變動清單。"""
    emap = {s["code"]: s for s in evening_stocks}
    mmap = {s["code"]: s for s in morning_stocks}
    changes = []
    for code in sorted(set(emap) | set(mmap)):
        e, m = emap.get(code), mmap.get(code)
        if not e or not m:
            changes.append({"code": code, "name": (m or e)["name"],
                            "change": "新增" if m else "移除"})
            continue
        diffs = []
        if e["dir"] != m["dir"]:
            diffs.append(f"方向 {e['dir']}→{m['dir']}")
        if e["support"] != m["support"]:
            diffs.append(f"支撐 {e['support']}→{m['support']}")
        if e["resistance"] != m["resistance"]:
            diffs.append(f"壓力 {e['resistance']}→{m['resistance']}")
        if e["rel"] != m["rel"]:
            diffs.append(f"可靠度 {e['rel']}→{m['rel']}")
        if diffs:
            changes.append({"code": code, "name": m["name"], "change": "；".join(diffs)})
    return changes


def _score_stocks(stocks, cmap):
    """對一份預測榜計分，回 (per_stock, stats)。"""
    per = []
    stat = {"n": 0, "dir_hit": 0, "dir_n": 0,
            "rel": {"高": [0, 0], "中": [0, 0], "低": [0, 0]},
            "size": {}, "by_dir": {"偏多": [0, 0], "偏空": [0, 0]},
            "price": {"total": 0, "score": 0, "break": 0},
            "range": {"total": 0, "hit": 0}, "prob": {"n": 0, "hit": 0},
            "prob_sum": 0}
    for s in stocks:
        key = str(s["code"]).zfill(4)
        got = cmap.get(key)
        if not got:
            per.append({"code": s["code"], "name": s["name"], "dir": s["dir"], "hit": None})
            continue
        close, chg = got
        hit = _dir_hit(s, chg)
        ps = _price_score(s, close)
        range_hit = None
        if s.get("range_lo") is not None and s.get("range_hi") is not None:
            stat["range"]["total"] += 1
            range_hit = s["range_lo"] <= chg <= s["range_hi"]
            if range_hit:
                stat["range"]["hit"] += 1
        row = {"code": s["code"], "name": s["name"], "dir": s["dir"],
               "chg": chg, "hit": hit, "price": ps, "rel": s["rel"], "size": s["size"],
               "range_hit": range_hit, "prob": s.get("prob")}
        per.append(row)
        if hit is not None:
            stat["dir_n"] += 1
            if hit:
                stat["dir_hit"] += 1
            rel = s["rel"] if s["rel"] in stat["rel"] else None
            if rel:
                stat["rel"][rel][1] += 1
                if hit:
                    stat["rel"][rel][0] += 1
            d = s.get("dir", "")
            if "偏多" in d:
                stat["by_dir"]["偏多"][1] += 1
                if hit:
                    stat["by_dir"]["偏多"][0] += 1
            elif "偏空" in d:
                stat["by_dir"]["偏空"][1] += 1
                if hit:
                    stat["by_dir"]["偏空"][0] += 1
            if s.get("prob") is not None:
                stat["prob"]["n"] += 1
                stat["prob_sum"] += s["prob"]
                if hit:
                    stat["prob"]["hit"] += 1
        if ps is not None:
            stat["price"]["total"] += 1
            stat["price"]["score"] += ps
            if ps == 0:
                stat["price"]["break"] += 1
        sz = s["size"] or "未標"
        if hit is not None:
            st = stat["size"].setdefault(sz, [0, 0])
            st[1] += 1
            if hit:
                st[0] += 1
    stat["n"] = len(stocks)
    return per, stat


def audit_day(day_str):
    """稽核某交易日：讀 前一晚 evening + 當日 morning，比對當日收盤。"""
    d = datetime.strptime(day_str, "%Y%m%d").date()
    prev = (d - timedelta(days=1)).strftime("%Y%m%d")
    morning_md = _read_md(os.path.join(POSTMARKET_OUT, f"postmarket_{day_str}_morning.md"))
    evening_md = _read_md(os.path.join(POSTMARKET_OUT, f"postmarket_{prev}_evening.md"))
    cmap, stamp = actual_close_map()
    snap_day = stamp[:8] if stamp else ""
    if not cmap or snap_day != day_str:
        return None, f"無 {day_str} 收盤快照（最新快照 {snap_day or '無'}），跳過稽核"

    morning_stocks = parse_forecast(morning_md) if morning_md else []
    evening_stocks = parse_forecast(evening_md) if evening_md else []

    rec = {"date": day_str, "snapshot": stamp}
    if evening_md:
        ep, es = _score_stocks(evening_stocks, cmap)
        rec["evening"] = {"stats": es, "per": ep}
    if morning_md:
        mp, ms = _score_stocks(morning_stocks, cmap)
        rec["morning"] = {"stats": ms, "per": mp}
    if evening_md and morning_md:
        rec["changes"] = _diff(evening_stocks, morning_stocks)
    return rec, None


def load_history():
    if not os.path.isfile(AUDIT_FILE):
        return []
    try:
        with io.open(AUDIT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def append_history(rec):
    os.makedirs(AUDIT_DIR, exist_ok=True)
    hist = load_history()
    hist = [h for h in hist if h.get("date") != rec.get("date")]
    hist.append(rec)
    hist.sort(key=lambda h: h.get("date", ""))
    with io.open(AUDIT_FILE, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)


def _rate(hit, n):
    return f"{hit}/{n}（{hit / n * 100:.0f}%）" if n else "—"


def _merge_stats(recent):
    """合併最近 N 天的 morning stats。"""
    m = {"dir_hit": 0, "dir_n": 0, "rel": {"高": [0, 0], "中": [0, 0], "低": [0, 0]},
         "size": {}, "by_dir": {"偏多": [0, 0], "偏空": [0, 0]},
         "range": {"total": 0, "hit": 0}, "prob": {"n": 0, "hit": 0}, "prob_sum": 0}
    for r in recent:
        st = r.get("morning", {}).get("stats", {})
        m["dir_hit"] += st.get("dir_hit", 0)
        m["dir_n"] += st.get("dir_n", 0)
        for k in m["rel"]:
            m["rel"][k][0] += st.get("rel", {}).get(k, [0, 0])[0]
            m["rel"][k][1] += st.get("rel", {}).get(k, [0, 0])[1]
        for k, v in st.get("size", {}).items():
            s = m["size"].setdefault(k, [0, 0])
            s[0] += v[0]; s[1] += v[1]
        for k in m["by_dir"]:
            m["by_dir"][k][0] += st.get("by_dir", {}).get(k, [0, 0])[0]
            m["by_dir"][k][1] += st.get("by_dir", {}).get(k, [0, 0])[1]
        m["range"]["total"] += st.get("range", {}).get("total", 0)
        m["range"]["hit"] += st.get("range", {}).get("hit", 0)
        m["prob"]["n"] += st.get("prob", {}).get("n", 0)
        m["prob"]["hit"] += st.get("prob", {}).get("hit", 0)
        m["prob_sum"] += st.get("prob_sum", 0)
    return m


def recent_summary(days=5):
    """歸納引擎：從稽核數據歸納錯誤模式，產生具體修正指令（供 Gemini 回饋）。"""
    hist = load_history()
    if not hist:
        return "（尚無預測績效紀錄）"
    recent = hist[-days:]
    m = _merge_stats(recent)
    lines = []
    # 0. 總命中率
    if m["dir_n"]:
        rate = m["dir_hit"] / m["dir_n"] * 100
        lines.append(f"你過去 {len(recent)} 天方向命中率 {m['dir_hit']}/{m['dir_n']}（{rate:.0f}%）。")
        if rate < 50:
            lines.append("命中率低於擲銅板 50%，代表方向判斷有系統性偏差，必須依下方檢討逐項修正。")
    # 1. 方向偏差（偏多 vs 偏空）
    bull = m["by_dir"].get("偏多", [0, 0])
    bear = m["by_dir"].get("偏空", [0, 0])
    if bull[1] and bear[1]:
        br = bull[0] / bull[1] * 100
        sr = bear[0] / bear[1] * 100
        lines.append(f"偏多命中 {bull[0]}/{bull[1]}（{br:.0f}%）、偏空命中 {bear[0]}/{bear[1]}（{sr:.0f}%）。")
        if br < 40 and sr >= 60:
            lines.append("⚠ 嚴重過度看多：偏多幾乎全錯、偏空幾乎全對。修正＝大盤偏弱時偏多檔減半、偏空檔加倍；每檔偏多必須有逆勢抗跌的獨立依據，否則改列偏空或中性。")
        elif br >= 60 and sr < 40:
            lines.append("⚠ 過度看空：偏空幾乎全錯、偏多幾乎全對。修正＝大盤偏強時偏空檔減半、偏多檔加倍。")
    # 2. 可靠度校準
    rel = m["rel"]
    if rel.get("高", [0, 0])[1] and rel.get("中", [0, 0])[1]:
        hr = rel["高"][0] / rel["高"][1] * 100
        mr = rel["中"][0] / rel["中"][1] * 100
        if hr <= mr:
            lines.append(f"⚠ 可靠度「高」命中 {hr:.0f}% 未優於「中」{mr:.0f}%，可靠度失真。修正＝只有多指標（資金＋法人＋籌碼）同步同向才標「高」，單一指標一律標中/低。")
        else:
            lines.append(f"可靠度「高」{hr:.0f}% >「中」{mr:.0f}%，區分力正常，維持。")
    # 3. 規模偏差
    sz = m["size"]
    worst = None
    for k, v in sz.items():
        if v[1] >= 3 and (worst is None or v[0] / v[1] < worst[0][0] / worst[0][1]):
            worst = (v, k)
    if worst and worst[0][0] / worst[0][1] < 0.4:
        lines.append(f"⚠ 規模「{worst[1]}」命中率 {worst[0][0]}/{worst[0][1]}（{worst[0][0] / worst[0][1] * 100:.0f}%）偏低。修正＝該規模沒把握就列中性或刪除，不要硬湊檔數。")
    # 4. 區間命中
    if m["range"]["total"]:
        rr = m["range"]["hit"] / m["range"]["total"] * 100
        if rr < 40:
            lines.append(f"⚠ 價位區間命中率僅 {m['range']['hit']}/{m['range']['total']}（{rr:.0f}%）。修正＝區間改用技術位階 ±3%~5%，不要給 ±10% 的寬鬆區間。")
    # 5. 概率膨脹
    if m["prob"]["n"]:
        pr = m["prob"]["hit"] / m["prob"]["n"] * 100
        avg = m["prob_sum"] / m["prob"]["n"]
        if avg - pr > 15:
            lines.append(f"⚠ 你標的平均概率 {avg:.0f}% 但實際命中 {pr:.0f}%，概率膨脹。修正＝概率平均下修約 {avg - pr:.0f}pp，只有強訊號才標 ≥60%。")
    if len(lines) <= 1 and m["dir_n"]:
        lines.append("各維度無明顯系統性偏差，維持現有選股邏輯。")
    return "\n".join(lines)


def intraday_summary(days=2):
    """讀 monitor_log.json，歸納盤中 15 分兌現軌跡的失敗模式，回饋 Gemini 修正。

    monitor_log 每輪每檔存 {t, open, high, low, close, vol, val, s(兌現/觀望/破位)}，
    另每檔帶 support/resistance 實際價位。這裡只挑「有問題」的檔回饋：
    早破位（前 3 輪就破）＝支撐/壓力價位錯；終日觀望＝方向訊號不足。
    """
    p = os.path.join(ROUTINES, "outputs", "monitor", "monitor_log.json")
    if not os.path.isfile(p):
        return ""
    try:
        with io.open(p, "r", encoding="utf-8") as f:
            log = json.load(f)
    except Exception:
        return ""
    if not log:
        return ""
    prob, good = [], 0
    for dkey in sorted(log.keys())[-days:]:
        rec = log[dkey]
        for st in rec.get("stocks", []):
            series = st.get("series", [])
            if len(series) < 2:
                continue
            d = st.get("dir", "")
            sup = st.get("support")
            res = st.get("resistance")
            sr = sup if "偏多" in d else res
            sr_label = "支撐" if "偏多" in d else "壓力"
            statuses = [p.get("s", "") for p in series]
            first_break = next((i for i, s in enumerate(statuses) if s == "break"), None)
            hit_n = statuses.count("hit")
            if first_break is not None:
                bp = series[first_break]
                tag = "早破位" if first_break <= 3 else "盤中才破位"
                if sr is not None:
                    reason = f"{sr_label} {sr} 設{'太高' if '偏多' in d else '太低'}或方向判錯"
                else:
                    reason = "方向判錯"
                prob.append(f"{st.get('code')} {st.get('name')}（{d}）：{bp.get('t')} {tag}，收 {bp.get('close')}（當輪高 {bp.get('high')}/低 {bp.get('low')}）→ {reason}")
            elif hit_n == 0:
                prob.append(f"{st.get('code')} {st.get('name')}（{d}）：終日觀望從未兌現 → 方向訊號不足或未標支撐壓力")
            else:
                good += 1
    if not prob:
        return ""
    tail = f"\n（另有 {good} 檔全日兌現）" if good else ""
    return "【盤中 15 分兌現檢討】（依 monitor_log 軌跡）\n" + "\n".join("- " + l for l in prob[:15]) + tail


def intraday_direction_accuracy(days=2):
    """讀 prediction_log.json，統計「15分K 下一方向預判」正確率＋誤判狀態分布。

    回 (summary_str, stats_dict)。stats：
      overall: {total, correct}
      by_pred: {續漲:[c,t], ...}
      by_Q:    {Q: {n, up, down, pc}}  ← 狀態轉換分布（量化可靠度）
    """
    p = os.path.join(ROUTINES, "outputs", "monitor", "prediction_log.json")
    if not os.path.isfile(p):
        return "", {}
    try:
        with io.open(p, "r", encoding="utf-8") as f:
            log = json.load(f)
    except Exception:
        return "", {}
    if not log:
        return "", {}

    by_pred = {}
    by_Q = {}
    total = correct = 0
    for dkey in sorted(log.keys())[-days:]:
        for st in log[dkey].get("stocks", []):
            for r in st.get("records", []):
                if r.get("correct") is None:
                    continue
                total += 1
                if r["correct"]:
                    correct += 1
                bp = by_pred.setdefault(r["pred"], [0, 0])
                bp[1] += 1
                if r["correct"]:
                    bp[0] += 1
                Q = r.get("Q", "?")
                bq = by_Q.setdefault(Q, {"n": 0, "up": 0, "down": 0, "pc": 0})
                bq["n"] += 1
                if r["actual"] == "up":
                    bq["up"] += 1
                elif r["actual"] == "down":
                    bq["down"] += 1
                if r["correct"]:
                    bq["pc"] += 1

    stats = {"overall": {"total": total, "correct": correct},
             "by_pred": by_pred, "by_Q": by_Q}
    if not total:
        return "", stats

    lines = []
    lines.append(f"15分K 下一方向預判正確率：{correct}/{total}（{correct / total * 100:.0f}%）")
    for pred in ("續漲", "續跌", "轉漲", "轉跌"):
        if pred in by_pred:
            c, t = by_pred[pred]
            lines.append(f"  {pred}：{c}/{t}（{c / t * 100:.0f}%）")
    bad = []
    for Q, bq in sorted(by_Q.items(), key=lambda kv: -kv[1]["n"]):
        if bq["n"] >= 3:
            up_pct = bq["up"] / bq["n"] * 100
            dn_pct = bq["down"] / bq["n"] * 100
            acc = bq["pc"] / bq["n"] * 100
            if acc < 50:
                bad.append(f"    {Q}：樣本 {bq['n']}，實際 漲 {up_pct:.0f}%/跌 {dn_pct:.0f}%，預判正確 {acc:.0f}% ← 誤判高發")
    if bad:
        lines.append("  誤判高發狀態（正確率<50%，供修正八象限 _Q_DIR 權重）：")
        lines.extend(bad)
    else:
        lines.append("  （樣本仍少，暫無誤判高發象限）")
    return "【15分K 預判稽核】\n" + "\n".join(lines), stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="稽核交易日 YYYYMMDD（預設＝今天）")
    ap.add_argument("--summary", action="store_true", help="印最近 5 天績效摘要")
    args = ap.parse_args()

    if args.summary:
        print(recent_summary(5))
        return

    day = args.date or date.today().strftime("%Y%m%d")
    rec, err = audit_day(day)
    if err:
        print(f"[audit] {err}")
        return
    append_history(rec)

    m = rec.get("morning", {}).get("stats", {})
    print(f"[audit] {day} 稽核完成（快照 {rec['snapshot']}）")
    print(f"  morning 方向命中率：{_rate(m.get('dir_hit', 0), m.get('dir_n', 0))}（{m.get('dir_n', 0)} 檔可判）")
    ch = rec.get("changes", [])
    if ch:
        print(f"  初稿→定稿變動 {len(ch)} 檔：")
        for c in ch[:10]:
            print(f"    {c['code']} {c['name']}：{c['change']}")
    print(f"  已累積 {len(load_history())} 天稽核紀錄")


if __name__ == "__main__":
    main()
