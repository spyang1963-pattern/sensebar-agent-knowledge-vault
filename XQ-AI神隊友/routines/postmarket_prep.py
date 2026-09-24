# -*- coding: utf-8 -*-
"""
postmarket_prep.py — 盤後綜合分析「資料彙整」

把五路資料彙整成一份結構化 Markdown input 檔（餵給 postmarket_report.py 呼叫模型）：

  1. XQ 當日快照（族群資金排行 / 齊漲分歧 / 盤中觀察三段）— routines/snapshots 目錄下
  2. stock-monitor 融資券 / 三大法人 / 千張大戶 — stock-monitor/output/cache/
  3. 美股連動（費半 / 四大指數 / 台積電ADR / 匯率 / 原物料）— financial_news market_data（Yahoo）
  4. financial_news 行事曆排期事件 — calendar_engine
  5. financial_news 每日/深度報告 .md — knowledge-base/金融/

用法：
  python postmarket_prep.py --slot evening      # 前一晚 22:00 初版
  python postmarket_prep.py --slot morning      # 開盤前 06:30 更新版
  python postmarket_prep.py --slot morning --no-fetch  # 不重新抓美股（快取）

輸出：routines/postmarket/input_{YYYYMMDD}_{slot}.md
"""
import os
import re
import sys
import glob
import csv
import json
import argparse
import io
from datetime import datetime, date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))          # XQ-AI神隊友
ROUTINES = os.path.join(ROOT, "routines")
WORKSPACE = os.path.dirname(ROOT)                                            # AI-Agent-Workspace
sys.path.insert(0, ROUTINES)

STOCK_MONITOR = os.path.join(WORKSPACE, "stock-monitor")
FINANCIAL_DIR = os.path.join(WORKSPACE, "financial_news")
KB_FIN = os.path.join(WORKSPACE, "knowledge-base", "金融")
FIN_DB = os.path.join(FINANCIAL_DIR, "finance.db")

POSTMARKET_DIR = os.path.join(ROUTINES, "postmarket")
SNAPSHOT_DIR = os.path.join(ROUTINES, "snapshots")

try:
    import render_html as rh
except Exception:
    rh = None


# ============================================================
#  1. XQ 當日快照摘要
# ============================================================
root = 0  # dummy（避免命名衝突）
_PX = {}  # code -> close（最新 breadth 快照現價，供撐壓基準與速查表）


def _load_price_map():
    """從最新 breadth 快照建立 {code: close} 現價 map。失敗時保留空 dict。"""
    global _PX
    if _PX:
        return
    try:
        snaps = rh.list_snapshots("breadth") if rh else {}
        if not snaps:
            return
        _, path = snaps.popitem()
        rows = rh.load_csv(path)
        _PX = {r["Code"]: r["Close"] for r in rows if r.get("Code")}
    except Exception as e:
        print(f"[prep] 現價 map 讀取失敗：{e}", file=sys.stderr)


def _px_format(code):
    v = _PX.get(code)
    if v is None:
        return "?"
    return f"{v:,.0f}元" if float(v) == int(v) else f"{v:,.2f}元"


def _price_table():
    """現價速查表：成交值前 80 檔快照（代碼 名稱 現價 市值），供撐壓推算＋規模分類用。"""
    _load_price_map()
    if not _PX or rh is None:
        return "（無快照現價 — 支撐/壓力請自行保守估計，或明說資料不足）"
    try:
        snap_rows = rh.load_csv(next(iter(rh.list_snapshots("breadth").values())))
    except Exception:
        snap_rows = []
    # 依成交值排序取前 80
    order = [r for r in snap_rows if r.get("Code") in _PX and r.get("Val", 0)]
    order.sort(key=lambda r: r.get("Val", 0), reverse=True)
    order = order[:80]
    if not order:
        return "（本次快照無現價資料）"
    rows = []
    for r in order:
        c = r["Code"]
        v = _PX.get(c)
        if v is None:
            continue
        px = f"{v:,.0f}元" if float(v) == int(v) else f"{v:,.2f}元"
        mcap = ""
        try:
            cap = float(r.get("Cap") or 0)
            if cap > 0:
                mcap = f" 市值{cap * float(v) / 10:,.0f}億"
        except (ValueError, TypeError):
            pass
        rows.append(f"- {c} {r.get('Name', '')} 現價{px}{mcap}")
    return "### 現價速查表（成交值前80 · 含市值 · 支撐/壓力與規模分類以此為基準）\n" + "\n".join(rows)


def _tech_levels():
    """技術位階速查表：從 stock-monitor K 線算每檔 前收/前高/前低/MA5/MA20/前20日高低，供支撐壓力引用。"""
    _load_price_map()
    if not _PX or rh is None:
        return "（無快照現價，無法算技術位階）"
    kline_dir = os.path.join(STOCK_MONITOR, "output", "cache", "kline")
    try:
        snap_rows = rh.load_csv(next(iter(rh.list_snapshots("breadth").values())))
    except Exception:
        snap_rows = []
    order = [r for r in snap_rows if r.get("Code") in _PX and r.get("Val", 0)]
    order.sort(key=lambda r: r.get("Val", 0), reverse=True)
    order = order[:80]
    if not order:
        return "（本次快照無資料）"

    def _fmt(v):
        return f"{v:,.0f}" if float(v) == int(v) else f"{v:,.1f}"

    rows = []
    for r in order:
        c = str(r["Code"]).zfill(4)
        path = os.path.join(kline_dir, f"{c}.json")
        if not os.path.isfile(path):
            continue
        try:
            with io.open(path, "r", encoding="utf-8") as f:
                data = json.load(f).get("data", [])
        except Exception:
            continue
        if not data:
            continue
        closes = [float(d.get("close", 0)) for d in data if d.get("close")]
        highs = [float(d.get("high", 0)) for d in data if d.get("high")]
        lows = [float(d.get("low", 0)) for d in data if d.get("low")]
        if not closes:
            continue
        last = data[-1]
        prev_close = float(last.get("close", 0))
        prev_high = float(last.get("high", 0))
        prev_low = float(last.get("low", 0))
        ma5 = sum(closes[-5:]) / len(closes[-5:]) if closes[-5:] else 0
        ma20 = sum(closes[-20:]) / len(closes[-20:]) if closes[-20:] else 0
        h20 = max(highs[-20:]) if highs else 0
        l20 = min(lows[-20:]) if lows else 0
        bias = (prev_close - ma20) / ma20 * 100 if ma20 else 0
        rows.append(f"- {c} {r.get('Name', '')} 前收{_fmt(prev_close)} 前高{_fmt(prev_high)} 前低{_fmt(prev_low)} "
                    f"MA5={_fmt(ma5)} MA20={_fmt(ma20)} 前20日高{_fmt(h20)} 前20日低{_fmt(l20)} 乖離率{bias:+.1f}%")
    if not rows:
        return "（無 K 線資料）"
    return ("### 技術位階速查表（成交值前80 · 支撐/壓力必須引用這些位階並括號標明依據；乖離率＝前收相對 MA20 偏離，正值＝漲高於均線有回檔壓力、負值＝跌低於均線有反彈空間）\n"
            + "\n".join(rows))


def _ma_alignment():
    """均線排列速查表：日K MA8/21/55 斜率 → 全多排列(強勢)/全空排列(弱勢)/糾結。

    供 Gemini 從強勢/弱勢股挑選，排除盤整糾結的權值股。
    全多＝MA8>MA21>MA55 且三者向上；全空＝MA8<MA21<MA55 且三者向下。
    """
    kline_dir = os.path.join(STOCK_MONITOR, "output", "cache", "kline")
    try:
        snap_rows = rh.load_csv(next(iter(rh.list_snapshots("breadth").values())))
    except Exception:
        snap_rows = []
    order = [r for r in snap_rows if r.get("Code") and r.get("Val", 0)]
    order.sort(key=lambda r: r.get("Val", 0), reverse=True)
    order = order[:200]
    if not order:
        return "（本次快照無資料）"

    strong, weak = [], []
    for r in order:
        c = str(r["Code"]).zfill(4)
        path = os.path.join(kline_dir, f"{c}.json")
        if not os.path.isfile(path):
            continue
        try:
            with io.open(path, "r", encoding="utf-8") as f:
                data = json.load(f).get("data", [])
        except Exception:
            continue
        closes = [float(d.get("close", 0)) for d in data if d.get("close")]
        vols = [float(d.get("volume", 0)) for d in data if d.get("volume")]
        if len(closes) < 60:
            continue
        ma8 = sum(closes[-8:]) / 8
        ma21 = sum(closes[-21:]) / 21
        ma55 = sum(closes[-55:]) / 55
        ma8p = sum(closes[-9:-1]) / 8
        ma21p = sum(closes[-22:-1]) / 21
        ma55p = sum(closes[-56:-1]) / 55
        up8, up21, up55 = ma8 > ma8p, ma21 > ma21p, ma55 > ma55p
        prev = closes[-2] if len(closes) >= 2 else closes[-1]
        chg = (closes[-1] - prev) / prev * 100 if prev else 0
        vol_today = vols[-1] if vols else 0
        vol_yest = vols[-2] if len(vols) >= 2 else 0
        vol_up = vol_today > vol_yest
        # 強勢＝全多排列＋量增＋漲幅≥5%（正要/剛起漲，排除量縮反轉階段）
        if ma8 > ma21 > ma55 and up8 and up21 and up55 and vol_up and chg >= 5:
            strong.append((c, r.get("Name", ""), chg))
        # 弱勢＝全空排列（不需資金/量：無需求價自然跌）
        elif ma8 < ma21 < ma55 and not up8 and not up21 and not up55:
            weak.append((c, r.get("Name", ""), chg))

    strong.sort(key=lambda x: -x[2])
    weak.sort(key=lambda x: x[2])
    lines = ["### 均線排列速查表（強勢＝日K 全多排列＋量增＋今日漲幅≥5%；弱勢＝日K 全空排列，不要求資金/量；其餘＝糾結盤整或反轉疑慮，勿選入預測榜）"]
    if strong:
        lines.append("- 強勢股（全多排列 {} 檔，依今日漲幅）：".format(len(strong))
                    + "、".join(f"{c} {n}({chg:+.1f}%)" for c, n, chg in strong[:30]))
    if weak:
        lines.append("- 弱勢股（全空排列 {} 檔，依今日跌幅）：".format(len(weak))
                    + "、".join(f"{c} {n}({chg:+.1f}%)" for c, n, chg in weak[:30]))
    if not strong and not weak:
        return "（無明確多空排列個股）"
    return "\n".join(lines)


def _xq_summary():
    if rh is None:
        return "（無法載入 render_html 模組）"
    _load_price_map()
    groups = rh.build_group_map()
    lines = []
    for kind, label in (("rank", "族群資金排行"), ("breadth", "齊漲分歧診斷"), ("notes", "盤中觀察三段")):
        snaps = rh.list_snapshots(kind)
        if not snaps:
            lines.append(f"### {label}\n無快照")
            continue
        stamp, path = snaps.popitem()
        lines.append(f"### {label}（最新快照 {stamp[:8]} {stamp[9:11]}:{stamp[11:13]}）")
        try:
            if kind == "rank":
                d = rh.build_rank(groups, path)
                one = rh.one_line_rank(d)
                rows = []
                for g in d.get("groups", []):
                    rows.append(f"- {g.get('G')} 成交值{g.get('Val', 0):.1f}億 佔比{g.get('Pct', 0):.1f}% "
                                f"{g.get('Up', 0)}漲{g.get('Dn', 0)}跌 平均漲幅{g.get('Avg', 0):+.2f}%")
                lines.append(f"一句話結論：{one}")
                lines.extend(rows[:12])
                # 資金位移 top (跟上一份比)
                try:
                    trend = rh.compare_rank(rh.load_previous("rank", path), d.get("top", []), d.get("top", []))
                    lines.append("資金位移（成交值增減前8）：")
                    for it in trend[:8]:
                        lines.append(f"- {it.get('Code')} {it.get('label')} verdict={it.get('verdict')}：{it.get('text')}")
                except Exception:
                    pass
            elif kind == "breadth":
                d = rh.build_breadth(groups, path)
                one = rh.one_line_breadth(d)
                lines.append(f"一句話結論：{one}")
                tag_names = {"RALLY": "齊漲", "SELLOFF": "齊跌", "SPLIT": "內部分歧", "SOLO": "個別表現", "THIN": "樣本不足"}
                for tag, label in tag_names.items():
                    arr = [r for r in d.get("rows", []) if tag in r.get("Tags", [])]
                    if arr:
                        lines.append(f"{label}族群（依成交值）：")
                        for g in arr[:6]:
                            mem = "、".join(f"{m.get('Name')}{m.get('Chg',0):+.1f}%" for m in g.get("Mem", [])[:6])
                            lines.append(f"- {g.get('G')} 檔數{g.get('N')} {g.get('Up')}漲{g.get('Dn')}跌 平均{g.get('Avg',0):+.2f}% 成交值{g.get('Val',0):.1f}億 成員：{mem}")
                for sig in d.get("signals", []):
                    items = sig.get("items", [])
                    if items:
                        lines.append(f"個股訊號【{sig.get('title')}】：")
                        for s in items[:8]:
                            lines.append(f"- {s.get('Code')} {s.get('Name')} 現價{_px_format(s.get('Code'))} 漲幅{s.get('Chg',0):+.2f}% 成交值{s.get('Val',0):.1f}億")
            else:
                d = rh.build_notes(groups, path)
                one = rh.one_line_notes(d)
                lines.append(f"一句話結論：{one}")
                lines.append("族群成交值前8：")
                for g in d.get("groups", [])[:8]:
                    dv_label = f" 成交值增減{g.get('DV',0):+.1f}億" if g.get('DV') else ""
                    lines.append(f"- {g.get('G')} 成交值{g.get('V',0):.1f}億（佔比{g.get('Pct',0):.1f}%） 平均{g.get('A',0):+.2f}% {g.get('U',0)}漲{g.get('D',0)}跌{dv_label}")
                for lock in d.get("locks", []):
                    items = lock.get("items", [])
                    if items:
                        lines.append(f"{lock.get('title')}：")
                        for s in items[:6]:
                            r = s.get("r", {})
                            lines.append(f"- {r.get('Code')} {r.get('Name')} 漲幅{r.get('Chg',0):+.2f}% 換手{r.get('Turn',0):.1f}%")
                for nm, arr in (("翻紅", d.get("flipped_red")), ("翻黑", d.get("flipped_green"))):
                    if arr:
                        lines.append(f"{nm}：{arr.get('Code')} {arr.get('Name')} 漲幅{arr.get('Chg',0):+.2f}%")
                big = d.get("big_movers", [])
                if big:
                    lines.append("大幅位移：")
                    if isinstance(big, dict):
                        lines.append(f"- {big}")
                    else:
                        for s in big[:8]:
                            lines.append(f"- {s}")
        except Exception as e:
            lines.append(f"（解析失敗：{e}）")
    return "\n".join(lines)


# ============================================================
#  2. 融資券 / 三大法人 / 千張大戶
# ============================================================
def _latest_dates_csv(path, date_col="date"):
    rows = []
    if os.path.isfile(path):
        with io.open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            rows = list(csv.DictReader(f))
    date_re = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    rows = [r for r in rows if date_re.match(r.get(date_col, ""))]
    dates = sorted(set(r.get(date_col, "") for r in rows))
    return rows, dates


def _as_int(v):
    try:
        return int(str(v).replace(",", "").strip() or 0)
    except (ValueError, AttributeError):
        return 0


def _margin_summary():
    path = os.path.join(STOCK_MONITOR, "output", "cache", "margin_history.csv")
    rows, dates = _latest_dates_csv(path)
    if len(dates) < 1:
        return "（無融資券資料）"
    d0, d1 = dates[-1], (dates[-2] if len(dates) >= 2 else None)
    today = {r["stock_id"]: r for r in rows if r.get("date") == d0}
    prev = {r["stock_id"]: r for r in rows if r.get("date") == d1} if d1 else {}
    out = [f"（最新日期 {d0}，前一日 {d1 or '無'}，共{len(today)}檔）"]
    total_m0 = sum(_as_int(r.get("margin_balance")) for r in today.values())
    total_m1 = sum(_as_int(p.get("margin_balance")) for p in prev.values())
    if total_m1:
        chg_total = total_m0 - total_m1
        out.append(f"全市場融資餘額 {total_m0:,} 張（前一日 {total_m1:,}，變化 {chg_total:+,} 張，{chg_total / total_m1 * 100:+.2f}%）→ 散戶整體{'加碼槓桿' if chg_total > 0 else '退場去槓桿'}")
    deltas = []
    for sid, r in today.items():
        m0 = _as_int(r.get("margin_balance"))
        p = prev.get(sid, {})
        m1 = _as_int(p.get("margin_balance"))
        # 前一日無此檔資料時不當「大增/大減」處理（可能是新增上市）
        if not p or not m1:
            continue
        chg = m0 - m1
        pct = chg / m1 * 100 if m1 else 0
        if abs(chg) >= 500:
            deltas.append((chg, -abs(pct), sid, r.get("stock_name", ""), m0, pct))
    deltas.sort(key=lambda x: x[1])
    if not deltas:
        out.append("（本次無明顯融資增減，|變動| < 500 張）")
    else:
        out.append("融資大增（前8）：")
        for chg, _, sid, nm, m0, pct in deltas[:8]:
            out.append(f"- {sid} {nm} 融資 {m0:,} 張（{chg:+,} 張，{pct:+.1f}%）")
        out.append("融資大減（前8）：")
        for chg, _, sid, nm, m0, pct in deltas[-8:]:
            out.append(f"- {sid} {nm} 融資 {m0:,} 張（{chg:+,} 張，{pct:+.1f}%）")
    # 融券增減
    shorts = []
    for sid, r in today.items():
        s0 = _as_int(r.get("short_balance"))
        p = prev.get(sid, {})
        s1 = _as_int(p.get("short_balance"))
        if not p:
            continue
        chg = s0 - s1
        if abs(chg) >= 100:
            shorts.append((chg, sid, r.get("stock_name", ""), s0))
    shorts.sort(key=lambda x: -x[0])
    if shorts:
        out.append("融券大增（前5）：")
        for chg, sid, nm, s0 in shorts[:5]:
            out.append(f"- {sid} {nm} 融券 {s0:,} 張（{chg:+,} 張）")
        out.append("融券大減（前5）：")
        for chg, sid, nm, s0 in shorts[-5:]:
            out.append(f"- {sid} {nm} 融券 {s0:,} 張（{chg:+,} 張）")
    # 券資比（融券/融資，≥8% 有軋空潛力）
    sbr = []
    for sid, r in today.items():
        m0 = _as_int(r.get("margin_balance"))
        s0 = _as_int(r.get("short_balance"))
        if m0 > 0 and s0 > 0:
            ratio = s0 / m0 * 100
            if ratio >= 8:
                sbr.append((ratio, sid, r.get("stock_name", ""), s0, m0))
    sbr.sort(key=lambda x: -x[0])
    if sbr:
        out.append("券資比偏高（前5，≥8% 有軋空潛力）：")
        for ratio, sid, nm, s0, m0 in sbr[:5]:
            out.append(f"- {sid} {nm} 券資比 {ratio:.1f}%（融券{s0:,}/融資{m0:,}）")
    return "\n".join(out)


_CHG = {}


def _breadth_chg_map():
    """最新 breadth 快照 {code: chg_pct}，供三大觸發（漲跌×融資變動）計算。"""
    global _CHG
    if _CHG:
        return _CHG
    if rh is None:
        return _CHG
    try:
        snaps = rh.list_snapshots("breadth")
        if not snaps:
            return _CHG
        _, path = snaps.popitem()
        for r in rh.load_csv(path):
            c = r.get("Code")
            if c:
                try:
                    _CHG[str(c).zfill(4)] = float(r.get("Chg", 0) or 0)
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass
    return _CHG


def _margin_triggers():
    """三大觸發（簡化：漲跌幅 × 融資變動），對齊 stock-monitor 的法人吃貨/恐慌殺出/斷頭語義。"""
    path = os.path.join(STOCK_MONITOR, "output", "cache", "margin_history.csv")
    rows, dates = _latest_dates_csv(path)
    if len(dates) < 1:
        return "（無融資券資料，無法計算三大觸發）"
    d0, d1 = dates[-1], (dates[-2] if len(dates) >= 2 else None)
    if not d1:
        return "（僅單日融資券資料，無法計算變動）"
    today = {str(r["stock_id"]).zfill(4): r for r in rows if r.get("date") == d0}
    prev = {str(r["stock_id"]).zfill(4): r for r in rows if r.get("date") == d1}
    chg_map = _breadth_chg_map()
    ib, ps, mc = [], [], []
    for code, r in today.items():
        p = prev.get(code)
        if not p:
            continue
        m0 = _as_int(r.get("margin_balance"))
        m1 = _as_int(p.get("margin_balance"))
        d_margin = m0 - m1
        chg = chg_map.get(code)
        if chg is None:
            continue
        nm = r.get("stock_name", "")
        if chg >= 2.0 and d_margin <= -80:
            ib.append((chg, d_margin, code, nm))
        if chg <= -4.0 and d_margin <= -100:
            ps.append((chg, d_margin, code, nm))
        if chg <= -6.0 and d_margin <= -500:
            mc.append((chg, d_margin, code, nm))
    if not (ib or ps or mc):
        return "三大觸發：今日無明顯觸發訊號（法人吃貨／恐慌殺出／斷頭均無）。"
    ib.sort(key=lambda x: -x[0])
    ps.sort(key=lambda x: x[0])
    mc.sort(key=lambda x: x[0])
    out = ["三大觸發（漲跌 × 融資變動）："]
    if ib:
        out.append("① 法人吃貨（股漲≥2% 且融資減，散戶賣法人接，前6）：")
        for chg, dm, code, nm in ib[:6]:
            out.append(f"- {code} {nm} 漲{chg:+.1f}% 融資{dm:+,} 張")
    if ps:
        out.append("② 恐慌殺出（股跌≤-4% 且融資減，前6）：")
        for chg, dm, code, nm in ps[:6]:
            out.append(f"- {code} {nm} 跌{chg:+.1f}% 融資{dm:+,} 張")
    if mc:
        out.append("③ 斷頭壓力（股跌≤-6% 且融資大減≤-500，前6）：")
        for chg, dm, code, nm in mc[:6]:
            out.append(f"- {code} {nm} 跌{chg:+.1f}% 融資{dm:+,} 張")
    return "\n".join(out)


def _institutional_summary():
    path = os.path.join(STOCK_MONITOR, "output", "cache", "institutional_history.csv")
    rows, dates = _latest_dates_csv(path)
    if len(dates) < 1:
        return "（無三大法人資料）"
    d0 = dates[-1]
    today = [r for r in rows if r.get("date") == d0]
    def tn(r):
        return _as_int(r.get("total_net"))
    buys = [r for r in today if tn(r) > 0]
    sells = [r for r in today if tn(r) < 0]
    buys.sort(key=tn, reverse=True)
    sells.sort(key=tn)
    out = [f"（最新日期 {d0}，共{len(today)}檔有資料）"]
    out.append("三大法人淨買超前10：")
    for r in buys[:10]:
        out.append(f"- {r['stock_id']} {r.get('stock_name','')} 外資{_as_int(r.get('foreign_net')):,} 投信{_as_int(r.get('trust_net')):,} 自營{_as_int(r.get('dealer_net')):,} 合計{tn(r):,}")
    out.append("三大法人淨賣超前10：")
    for r in sells[:10]:
        out.append(f"- {r['stock_id']} {r.get('stock_name','')} 外資{_as_int(r.get('foreign_net')):,} 投信{_as_int(r.get('trust_net')):,} 自營{_as_int(r.get('dealer_net')):,} 合計{tn(r):,}")
    return "\n".join(out)


def _tdcc_summary():
    path = os.path.join(STOCK_MONITOR, "output", "cache", "tdcc_shareholding.json")
    if not os.path.isfile(path):
        return "（無千張大戶資料）"
    with io.open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    cur = data.get("cur", {})
    prev = data.get("prev", {})
    week = data.get("week", "?")
    deltas = []
    for k, v in cur.items():
        try:
            p = prev.get(k)
            d = float(v) - (float(p) if p is not None else float(v))
        except (TypeError, ValueError):
            continue
        if abs(d) >= 1.0:
            deltas.append((d, k))
    gains = sorted([x for x in deltas if x[0] > 0], key=lambda x: -x[0])
    losses = sorted([x for x in deltas if x[0] < 0], key=lambda x: x[0])
    out = [f"（集保週 {week}，千張以上持股比例增減）"]
    out.append("千張大戶占比增加（前8）：")
    for d, k in gains[:8]:
        out.append(f"- {k} +{d:.1f}pp（現在{cur[k]:.1f}%）")
    out.append("千張大戶占比下降（前8）：")
    for d, k in losses[:8]:
        out.append(f"- {k} {d:+.1f}pp（現在{cur[k]:.1f}%）")
    if not deltas:
        out.append("（本週無明顯變化）")
    return "\n".join(out)


# ============================================================
#  3. 美股連動（financial_news market_data）
# ============================================================
def _us_summary(fetch=True):
    sys.path.insert(0, FINANCIAL_DIR)
    try:
        from db import latest_market_snapshot, init_db, ensure_schema
        import market_data
        if fetch:
            market_data.collect_snapshot()
        symbols = [
            ("^TWII", "加權指數"), ("^SOX", "費城半導體"), ("^DJI", "道瓊"), ("^GSPC", "S&P 500"),
            ("^IXIC", "納斯達克"), ("2330.TW", "台積電"), ("NVDA", "NVIDIA"), ("TSLA", "Tesla"),
            ("^TNX", "美債10年殖利率"), ("USDTWD=X", "美元/台幣"), ("GC=F", "黃金"),
            ("^N225", "日經225"), ("HSI", "恒生指數"),
        ]
        out = []
        for sym, nm in symbols:
            s = latest_market_snapshot(sym)
            if not s or s.get("price") is None:
                continue
            chg = s.get("change_pct")
            arrow = "▲" if chg and chg > 0 else ("▼" if chg and chg < 0 else "―")
            asof = (s.get("asof_at") or s.get("captured_at") or "")[:16]
            out.append(f"- {nm}: {s['price']:,.2f} {arrow}{chg if chg is not None else 0:+.2f}%（{asof}）")
        # 明日開盤領先指標：台積電 ADR + EWT 台灣 ETF（皆美股收盤後反映對台股預期）
        for sym, nm in (("TSM", "台積電ADR"), ("EWT", "台灣ETF EWT")):
            try:
                res = market_data.fetch_symbol(sym)
                if res and res[1] is not None:
                    _, price, chg, _asof = res
                    arrow = "▲" if chg > 0 else ("▼" if chg < 0 else "―")
                    out.append(f"- {nm}: {price:,.2f} {arrow}{chg:+.2f}%")
            except Exception:
                pass
        return "\n".join(out) if out else "（美股行情無資料）"
    except Exception as e:
        return f"（美股行情抓取失敗：{e}）"


# ============================================================
#  4. 行事曆
# ============================================================
def _calendar_summary(today, days=3):
    sys.path.insert(0, FINANCIAL_DIR)
    try:
        from calendar_engine import event_summary_for_prompt
        txt = event_summary_for_prompt(today, days=days)
        return txt or "（近期行事曆無排期事件）"
    except Exception as e:
        return f"（行事曆讀取失敗：{e}）"


# ============================================================
#  5. 每日/深度報告 .md
# ============================================================
def _report_summary():
    out = []
    # 每日報告
    daily_dir = os.path.join(KB_FIN, "每日報告")
    daily_files = sorted(glob.glob(os.path.join(daily_dir, "*.md"))) if os.path.isdir(daily_dir) else []
    if daily_files:
        f = daily_files[-1]
        out.append(f"### 每日金融報告（{os.path.basename(f)}）")
        with io.open(f, "r", encoding="utf-8", errors="replace") as fh:
            out.append(fh.read()[:6000])
    else:
        out.append("（此環境無每日報告 .md — 每日/深度報告由 PC3 的 financial_news 排程生成，本機只有手動/舊檔）")
    # 深度報告（最近兩份 .md）
    deep_dir = os.path.join(KB_FIN, "深度報告")
    deep_files = sorted(glob.glob(os.path.join(deep_dir, "*.md"))) if os.path.isdir(deep_dir) else []
    if deep_files:
        for f in deep_files[-2:]:
            out.append(f"\n### 深度分析報告（{os.path.basename(f)}）")
            with io.open(f, "r", encoding="utf-8", errors="replace") as fh:
                out.append(fh.read()[:5000])
    else:
        out.append("\n（此環境無深度分析報告 .md — 同上，唯有 PC3 才有）")
    # 提醒：檔名日期才是報告時效基準，舊報告僅作長期背景，不可當當天事件
    date_re = re.compile(r"(\d{4}-\d{2}-\d{2})")
    dates = []
    for f in (daily_files[-1:] + deep_files[-2:]):
        m = date_re.search(os.path.basename(f))
        if m:
            dates.append(m.group(1))
    if dates:
        out.append(f"\n> 報告時效：以上報告檔名日期為 {sorted(set(dates))}，若遠早於今日，僅供長期背景參考，不可視為當日最新事件。")
    return "\n\n".join(out)


def _news_sentiment_summary():
    """從 financial_news 的 finance.db 摘要近期重要新聞（severity≥2），反映市場情緒。"""
    sys.path.insert(0, FINANCIAL_DIR)
    try:
        import sqlite3
        if not os.path.isfile(FIN_DB):
            return "（無新聞資料庫）"
        conn = sqlite3.connect(FIN_DB)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT title, severity, sentiment, published FROM events "
            "WHERE is_noise=0 AND is_duplicate=0 AND severity>=2 "
            "ORDER BY published DESC LIMIT 20"
        ).fetchall()
        conn.close()
        if not rows:
            return "（近期無 severity≥2 的重要新聞）"
        out = [f"近期重要新聞（severity≥2，最新 {len(rows)} 則）："]
        for r in rows:
            sent = r["sentiment"] or "—"
            pub = (r["published"] or "")[:10]
            out.append(f"- [{pub}][severity {r['severity']}][{sent}] {r['title']}")
        return "\n".join(out)
    except Exception as e:
        return f"（新聞情緒讀取失敗：{e}）"


# ============================================================
#  主流程
# ============================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slot", choices=["evening", "morning"], default="evening")
    ap.add_argument("--no-fetch", action="store_true", help="不重新抓美股（讀既有 db）")
    args = ap.parse_args()

    os.makedirs(POSTMARKET_DIR, exist_ok=True)
    today = date.today()
    stamp = today.strftime("%Y%m%d")
    slot_label = "前一晚初版（22:00）" if args.slot == "evening" else "開盤前更新版（06:30）"

    parts = []
    parts.append(f"# 盤後綜合分析 input — {today.isoformat()}（{slot_label}）\n")
    parts.append(f"## 0. 現價速查表（支撐/壓力必須以此為基準）\n{_price_table()}\n")
    parts.append(f"## 0b. 技術位階速查表（支撐/壓力必須引用這些位階）\n{_tech_levels()}\n")
    parts.append(f"## 0c. 均線排列速查表（強勢/弱勢選股用）\n{_ma_alignment()}\n")
    parts.append(f"## 1. XQ 盤中快照摘要\n{_xq_summary()}\n")
    try:
        import eight_quadrant
        eq_block = eight_quadrant.build_md() or "（未取得量價判讀 feed）"
    except Exception:
        eq_block = "（量價判讀模組載入失敗）"
    parts.append(f"## 1b. 量價結構判讀（v2 L0~L3，程式計算）\n{eq_block}\n")
    parts.append(f"## 2. 融資券\n{_margin_summary()}\n\n{_margin_triggers()}\n")
    parts.append(f"## 3. 三大法人\n{_institutional_summary()}\n")
    parts.append(f"## 4. 千張大戶\n{_tdcc_summary()}\n")
    parts.append(f"## 5. 美股與國際盤（Yahoo 抓取）\n{_us_summary(fetch=not args.no_fetch)}\n")
    parts.append(f"## 6. 行事曆排期事件\n{_calendar_summary(today)}\n")
    parts.append(f"## 7. 金融報告摘錄\n{_report_summary()}\n")
    parts.append(f"## 7b. 當日新聞情緒（severity≥2 重要新聞）\n{_news_sentiment_summary()}\n")

    body = "\n".join(parts)
    out_path = os.path.join(POSTMARKET_DIR, f"input_{stamp}_{args.slot}.md")
    with io.open(out_path, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"[prep] {slot_label} 彙整完成 -> {out_path}（{len(body)} 字元）")


if __name__ == "__main__":
    main()