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
                "strength": sm.group(1) if sm else "",
                "size": szm.group(1) if szm else "",
                "rel": "", "support": None, "resistance": None,
                "prob": None, "range_lo": None, "range_hi": None, "vs_market": "",
            }
        elif cur and (s.startswith("-") or s.startswith("·")):
            raw = s.lstrip("-· ").strip()
            mm = re.match(r"^([^：]+)：\s*(.*)$", raw, re.S)
            if not mm:
                continue
            lab = mm.group(1).strip().replace("**", "")
            val = mm.group(2).strip()
            if "可靠度" in lab:
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
    """方向命中：偏多→chg>0、偏空→chg<0、中性/無→None（不計）。"""
    d = stock.get("dir", "")
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
            "size": {}, "price": {"total": 0, "score": 0, "break": 0},
            "range": {"total": 0, "hit": 0}, "prob": {"n": 0, "hit": 0}}
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
            if s.get("prob") is not None:
                stat["prob"]["n"] += 1
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


def recent_summary(days=5):
    """最近 N 天績效摘要（供 Gemini 回饋）。"""
    hist = load_history()
    if not hist:
        return "（尚無預測績效紀錄）"
    recent = hist[-days:]
    m_hit = m_n = 0
    for r in recent:
        m = r.get("morning", {}).get("stats", {})
        m_hit += m.get("dir_hit", 0)
        m_n += m.get("dir_n", 0)
    lines = [f"你過去 {len(recent)} 個交易日的預測榜（morning 定稿）方向命中率：{_rate(m_hit, m_n)}。"]
    # 可靠度校準（合併最近）
    rel = {"高": [0, 0], "中": [0, 0], "低": [0, 0]}
    for r in recent:
        m = r.get("morning", {}).get("stats", {}).get("rel", {})
        for k in rel:
            rel[k][0] += m.get(k, [0, 0])[0]
            rel[k][1] += m.get(k, [0, 0])[1]
    for k in ("高", "中", "低"):
        if rel[k][1]:
            lines.append(f"可靠度「{k}」命中率：{_rate(rel[k][0], rel[k][1])}。")
    if m_n:
        if m_hit / m_n < 0.5:
            lines.append("你的方向命中率低於擲銅板（50%），請檢討選股邏輯，勿再過度依賴單一指標。")
        if rel["高"][1] and rel["低"][1]:
            hr, ln = rel["高"][0] / rel["高"][1], rel["低"][0] / rel["低"][1]
            if hr <= ln:
                lines.append("你的「高可靠度」命中率未高於「低可靠度」，可靠度評級缺乏區分力，請據實標示。")
    # 區間命中率 + 概率校準
    r_hit = r_n = p_hit = p_n = 0
    for r in recent:
        m = r.get("morning", {}).get("stats", {})
        r_hit += m.get("range", {}).get("hit", 0)
        r_n += m.get("range", {}).get("total", 0)
        p_hit += m.get("prob", {}).get("hit", 0)
        p_n += m.get("prob", {}).get("n", 0)
    if r_n:
        lines.append(f"預期區間命中率（實際漲跌落在你給的區間內）：{_rate(r_hit, r_n)}。")
    if p_n:
        lines.append(f"你標注概率的檔，實際方向命中率：{_rate(p_hit, p_n)}（若遠低於你標的平均概率，代表概率膨脹，請據實下修）。")
    return "\n".join(lines)


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
