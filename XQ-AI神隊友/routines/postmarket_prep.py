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
  python postmarket_prep.py --slot morning      # 開盤前 08:35 更新版
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
def _xq_summary():
    if rh is None:
        return "（無法載入 render_html 模組）"
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
                            lines.append(f"- {s.get('Code')} {s.get('Name')} 漲幅{s.get('Chg',0):+.2f}% 成交值{s.get('Val',0):.1f}億")
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
        if fetch:
            import market_data
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
    # 深度報告（最近兩份 .md）
    deep_dir = os.path.join(KB_FIN, "深度報告")
    deep_files = sorted(glob.glob(os.path.join(deep_dir, "*.md"))) if os.path.isdir(deep_dir) else []
    for f in deep_files[-2:]:
        out.append(f"\n### 深度分析報告（{os.path.basename(f)}）")
        with io.open(f, "r", encoding="utf-8", errors="replace") as fh:
            out.append(fh.read()[:5000])
    return "\n\n".join(out) if out else "（無報告 md）"


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
    slot_label = "前一晚初版（22:00）" if args.slot == "evening" else "開盤前更新版（08:35）"

    parts = []
    parts.append(f"# 盤後綜合分析 input — {today.isoformat()}（{slot_label}）\n")
    parts.append(f"## 1. XQ 盤中快照摘要\n{_xq_summary()}\n")
    parts.append(f"## 2. 融資券\n{_margin_summary()}\n")
    parts.append(f"## 3. 三大法人\n{_institutional_summary()}\n")
    parts.append(f"## 4. 千張大戶\n{_tdcc_summary()}\n")
    parts.append(f"## 5. 美股與國際盤（Yahoo 抓取）\n{_us_summary(fetch=not args.no_fetch)}\n")
    parts.append(f"## 6. 行事曆排期事件\n{_calendar_summary(today)}\n")
    parts.append(f"## 7. 金融報告摘錄\n{_report_summary()}\n")

    body = "\n".join(parts)
    out_path = os.path.join(POSTMARKET_DIR, f"input_{stamp}_{args.slot}.md")
    with io.open(out_path, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"[prep] {slot_label} 彙整完成 -> {out_path}（{len(body)} 字元）")


if __name__ == "__main__":
    main()