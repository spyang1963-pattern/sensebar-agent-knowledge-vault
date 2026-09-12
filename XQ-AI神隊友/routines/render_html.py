# ============================================================
#  render_html.py ─ XQ-AI神隊友 盤中報告 HTML 看板產生器
#
#  作用：把 snapshots\ 的即時快照 CSV 轉成「一眼抓到關鍵」的互動 HTML。
#        （取代原本只有純文字 .md 的報告呈現方式）
#
#  用法：
#    python render_html.py --kind rank
#    python render_html.py --kind breadth
#    python render_html.py --kind notes
#    python render_html.py --all
#    python render_html.py --kind rank --csv <某快照.csv> --out <輸出路徑.html>   # 指定檔案
#
#  設計原則（對應 CLAUDE.md「文體通用規則」）：
#    1. 頂部「一句話結論」大字
#    2. 資金相關用橫條視覺化，顏色＝漲跌（紅漲綠跌）
#    3. 技術欄位 hover 顯示口語解釋
#    4. 矛盾／反差做成紅色警示卡，並附「這代表什麼」
#    5. 結尾「該盯的變數」
#
#  歷史與比較：自動掃 snapshots\{kind}_*.csv 全部同類檔，
#       取得「上一份」做「與前份比」，故每次快照就自然累積歷史。
#
#  輸出：routines\outputs\{kind}_{yyyyMMdd_HHmmss}.html
#  （之後可上 GitHub Pages，見 README 的部署段落）
# ============================================================
import argparse
import io
import html
import json
import os
import re
import sys
from datetime import datetime

# ---------- 路徑 ----------
ROOT = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_DIR = os.path.join(ROOT, "snapshots")
OUTPUT_DIR = os.path.join(ROOT, "outputs")
GROUPS_FILE = os.path.join(ROOT, "groups.ps1")
GROUPS_EXTRA = os.path.join(ROOT, "groups_extra.ps1")
POSTMARKET_OUT = os.path.join(ROOT, "outputs", "postmarket")

# ---------- 參數（對齊 analyze_breadth.ps1 的判定門檻） ----------
MIN_MEMBERS = 3
ALIGN_RATIO = 0.75
SPLIT_PCT = 3
SOLO_STRONG_PCT = 5
SOLO_REST_PCT = 2
LIMIT_PCT = 9.5
HOT_TURN = 10
FAKE_DEV = -1.5
HIDDEN_DEV = 1.5
WEAK_TOP = 30
WEAK_PCT = -2
# 以下是 notes（作法三）的門檻（對齊 analyze_notes.ps1）
NEAR_UP_PCT = 8.0      # 接近漲停：漲幅 ≥ +8% 但未鎖死
NEAR_DOWN_PCT = -8.5   # 接近跌停：漲幅 ≤ -8.5%
BIG_MOVE_PCT = 2.5     # 大幅位移：與上一份相比漲幅變化 ≥ |2.5%|
KEY_CODES = ['2330', '2454', '2317', '3037', '2408', '2492', '6173', '3653']

# 各 kind 的分析範圍（成交值前 N 名）
UNIVERSE = {"rank": 50, "breadth": 200, "notes": 160}


# ============================================================
#  族群分類：解析 groups.ps1 / groups_extra.ps1
# ============================================================
def parse_groups_file(path):
    """解析 '代碼'='族群名' 格式，回傳 {code: name}。忽略註解與 $Global 行。"""
    groups = {}
    if not os.path.exists(path):
        return groups
    try:
        with io.open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.split("#")[0].strip()
                m = re.match(r"^'([A-Za-z0-9\-]+)'\s*=\s*'(.+?)'$", line)
                if m:
                    groups[m.group(1).strip()] = m.group(2).strip()
    except Exception as e:
        print(f"WARN 讀取 {path} 失敗: {e}", file=sys.stderr)
    return groups


def build_group_map():
    g = parse_groups_file(GROUPS_FILE)
    extra = parse_groups_file(GROUPS_EXTRA)
    g.update(extra)  # groups_extra 覆蓋主檔
    return g


# ============================================================
#  讀取快照
# ============================================================
def list_snapshots(kind):
    """回傳同 kind 的 {stamp: path}，依時間排序（stamp = yyyyMMdd_HHmmss）。"""
    pat = re.compile(r"^" + re.escape(kind) + r"_(\d{8}_\d{6})\.csv$")
    found = {}
    if os.path.isdir(SNAPSHOT_DIR):
        for fn in os.listdir(SNAPSHOT_DIR):
            m = pat.match(fn)
            if m:
                found[m.group(1)] = os.path.join(SNAPSHOT_DIR, fn)
    return dict(sorted(found.items()))


def load_csv(path):
    """讀快照 CSV，回傳 list[dict]，欄位轉 double。"""
    rows = []
    with io.open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        header = f.readline().strip().replace("\ufeff", "").split(",")
        header = [h.strip().strip('"') for h in header]
        for line in f:
            if not line.strip():
                continue
            cells = [c.strip().strip('"') for c in line.rstrip("\n").split(",")]
            d = dict(zip(header, cells))
            for k in ("Close", "Chg", "Vol", "Turn", "Dev", "IO", "BidQ", "AskQ", "Cap", "Val"):
                try:
                    d[k] = float(d[k])
                except (KeyError, ValueError):
                    d[k] = 0.0
            rows.append(d)
    return rows


# ============================================================
#  數值格式化
# ============================================================
def fmt(v, nd=1):
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return "0"


def fmt_chg(v):
    v = float(v)
    return f"+{v:.2f}%" if v > 0 else (f"{v:.2f}%" if v < 0 else "0.00%")


def chg_class(v):
    """成交量/漲幅的紅綠 class。台股紅漲綠跌。"""
    v = float(v)
    if v > 0:
        return "up"
    if v < 0:
        return "down"
    return "flat"


# 欄位 hover 口語翻譯（對應 CLAUDE.md「欄位口語翻譯」）
FIELD_TIPS = {
    "IO": "內外盤比：委買/委賣掛單比值，>50 表示買方掛單多（偏多），<50 賣方掛單多（偏空）。不是成交方向，是掛單厚度。",
    "Dev": "乖離：成交價相對「當日均價」的差距%。正值＝收在均價上方，負值＝收在均價下方。負很多＝開高走低或殺到尾盤。",
    "Turn": "換手率：當日總量 ÷ 股本。越高表示籌碼換手越激烈；低換手鎖漲停＝籌碼極輕，高換手才漲停＝激烈對戰。",
    "BidQ": "委買：買盤排隊張數。",
    "AskQ": "委賣：賣盤排隊張數。",
    "Val": "成交值：該股成交總額（億元）。",
}


# ============================================================
#  作法一：族群資金排行資料
# ============================================================
def build_rank(groups, path, top_n=50):
    all_rows = [r for r in load_csv(path) if r["Code"] not in ("TSE", "OTC")]
    all_rows.sort(key=lambda r: r["Val"], reverse=True)
    top = all_rows[:top_n]
    for i, r in enumerate(top, 1):
        r["Rk"] = i
        r["Grp"] = groups.get(r["Code"], "未分類")

    tot = sum(r["Val"] for r in top)

    # 族群彙總
    grp = {}
    for r in top:
        grp.setdefault(r["Grp"], []).append(r)
    groups_rows = []
    for g, mem in grp.items():
        val = sum(r["Val"] for r in mem)
        avg = sum(r["Chg"] for r in mem) / len(mem)
        up = sum(1 for r in mem if r["Chg"] > 0)
        dn = sum(1 for r in mem if r["Chg"] < 0)
        mem_sorted = sorted(mem, key=lambda r: r["Val"], reverse=True)
        groups_rows.append({
            "G": g, "N": len(mem), "Val": val, "Pct": val / tot * 100 if tot else 0,
            "Avg": avg, "Up": up, "Dn": dn,
            "Mem": mem_sorted,
        })
    groups_rows.sort(key=lambda r: r["Val"], reverse=True)
    tot = round(tot, 1)

    unclassified = [r for r in top if r["Grp"] == "未分類"]

    # 前 3 大資金族群
    top3 = groups_rows[:3]

    # 矛盾股：成交值 top 但收黑（量最大卻綠的）
    contradictions = [r for r in top if r["Chg"] < 0][:3]

    # ---------- ① 各筆意義：把 raw 欄位轉成「這代表什麼」 ----------
    for r in top:
        r["Why"] = interpret_stock(r, tot)

    # ---------- ② 整體結構診斷 ----------
    structure = diagnose_structure(groups_rows, all_rows, tot)

    # ---------- ③ 趨勢：與前一份同 kind 快照比較 ----------
    prev_rows = load_previous(kind="rank", path=path)
    trend = compare_rank(prev_rows, top, all_rows) if prev_rows else None
    history_count = len(list_snapshots("rank"))

    return {
        "kind": "rank", "file": os.path.basename(path), "stamp": guess_stamp(path),
        "total": len(all_rows), "top_n": top_n, "top_total": tot,
        "top": top, "groups": groups_rows, "unclassified": unclassified,
        "top3": top3, "contradictions": contradictions,
        "structure": structure, "trend": trend, "history_count": history_count,
    }


# ============================================================
#  作法二：齊漲分歧診斷資料（對齊 analyze_breadth.ps1 的口徑）
# ============================================================
def build_breadth(groups, path, top_n=None):
    top_n = top_n or UNIVERSE["breadth"]
    all_rows = [r for r in load_csv(path) if r["Code"] not in ("TSE", "OTC")]
    all_rows.sort(key=lambda r: r["Val"], reverse=True)
    top = all_rows[:top_n]
    rank_map = {r["Code"]: i + 1 for i, r in enumerate(top)}

    # 族群歸類
    grp = {}
    unclassified = []
    for r in top:
        g = groups.get(r["Code"])
        if not g:
            unclassified.append(r)
            continue
        grp.setdefault(g, []).append(r)

    rows = []
    for g, mem in grp.items():
        mem = sorted(mem, key=lambda r: r["Chg"], reverse=True)
        n = len(mem)
        up = sum(1 for r in mem if r["Chg"] > 0)
        dn = sum(1 for r in mem if r["Chg"] < 0)
        val = round(sum(r["Val"] for r in mem), 1)
        lu = sum(1 for r in mem if r["Chg"] >= LIMIT_PCT and r["AskQ"] == 0)
        ld = sum(1 for r in mem if r["Chg"] <= -LIMIT_PCT and r["BidQ"] == 0)
        hi = max(r["Chg"] for r in mem)
        lo = min(r["Chg"] for r in mem)
        tags = []
        if n >= MIN_MEMBERS:
            if up / n >= ALIGN_RATIO and up >= MIN_MEMBERS:
                tags.append("RALLY")
            if dn / n >= ALIGN_RATIO and dn >= MIN_MEMBERS:
                tags.append("SELLOFF")
            if hi >= SPLIT_PCT and lo <= -SPLIT_PCT:
                tags.append("SPLIT")
            strong = [r for r in mem if r["Chg"] >= SOLO_STRONG_PCT]
            rest = [r for r in mem if r["Chg"] < SOLO_STRONG_PCT]
            if len(strong) == 1 and sum(1 for r in rest if abs(r["Chg"]) > SOLO_REST_PCT) == 0:
                tags.append("SOLO")
        else:
            tags.append("THIN")
        rows.append({
            "G": g, "N": n, "Up": up, "Dn": dn, "Val": val, "LU": lu, "LD": ld,
            "Hi": hi, "Lo": lo, "Ratio": round(up / n, 3), "Avg": round(sum(r["Chg"] for r in mem) / n, 2),
            "Tags": tags, "Mem": mem,
        })
    rows.sort(key=lambda r: r["Val"], reverse=True)

    # 個股訊號
    def sig(title, cond, sort_key, detail):
        items = [r for r in top if cond(r)]
        items.sort(key=sort_key, reverse=True)
        return {"title": title, "items": items, "detail": detail}

    signals = [
        sig("漲停鎖死", lambda r: r["Chg"] >= LIMIT_PCT and r["AskQ"] == 0,
            lambda r: r["Val"], "漲幅 ≥ +9.5% 且委賣挂 0，買不到＝籌碼極度稀缺"),
        sig("跌停鎖死", lambda r: r["Chg"] <= -LIMIT_PCT and r["BidQ"] == 0,
            lambda r: r["Val"], "跌幅 ≤ -9.5% 且委買挂 0，想走也賣不掉"),
        sig("換手異常", lambda r: r["Turn"] >= HOT_TURN,
            lambda r: r["Turn"], f"換手率 ≥ {HOT_TURN}%，籌碼激烈交換"),
        sig("假強勢", lambda r: r["Chg"] > 0 and r["Dev"] <= FAKE_DEV,
            lambda r: r["Val"], "漲幅為正但收在均價下方（開高走低），漲是假象"),
        sig("隱藏買盤", lambda r: r["Chg"] < 0 and r["Dev"] >= HIDDEN_DEV,
            lambda r: r["Val"], "漲幅為負但收在均價上方（低開走高），有人在偷接"),
        sig("量大走弱", lambda r: rank_map.get(r["Code"], 999) <= WEAK_TOP and r["Chg"] <= WEAK_PCT,
            lambda r: r["Val"], f"成交值前 {WEAK_TOP} 名且漲幅 ≤ {WEAK_PCT}%，大資金壓著往下走"),
    ]

    up_top = len([r for r in top if r["Chg"] > 0])
    dn_top = len([r for r in top if r["Chg"] < 0])
    flat_top = len([r for r in top if r["Chg"] == 0])
    up_all = len([r for r in all_rows if r["Chg"] > 0])
    dn_all = len([r for r in all_rows if r["Chg"] < 0])
    cut = top[-1] if top else None

    # 最反直覺的一件事：找標籤中的關鍵矛盾
    counter = []
    if rows:
        biggest = rows[0]
        if "SELLOFF" in biggest["Tags"]:
            counter.append(f"成交值最大的族群「{biggest['G']}」（{biggest['Val']:.0f}億）竟然齊跌 {biggest['Dn']}/{biggest['N']}——大資金在主軸退潮")
        elif "SPLIT" in biggest["Tags"] and biggest["Val"] >= rows[1]["Val"] * 1.2 if len(rows) > 1 else False:
            counter.append(f"成交值最大的族群「{biggest['G']}」內部嚴重分歧（高點 {biggest['Hi']:+g}% / 低點 {biggest['Lo']:+g}%）——這不是族群行情，是資金在族內挑股")

    return {
        "kind": "breadth", "file": os.path.basename(path), "stamp": guess_stamp(path),
        "top_n": top_n, "total": len(all_rows), "cut": cut,
        "up_top": up_top, "dn_top": dn_top, "flat_top": flat_top,
        "up_all": up_all, "dn_all": dn_all,
        "rows": rows, "unclassified": unclassified, "signals": signals,
        "counter": counter,
    }


# ============================================================
#  作法三：盤中觀察三段資料（對齊 analyze_notes.ps1 的口徑）
# ============================================================
def build_notes(groups, path):
    all_rows = load_csv(path)
    idx = [r for r in all_rows if r["Code"] in ("TSE", "OTC")]
    s = [r for r in all_rows if r["Code"] not in ("TSE", "OTC")]
    s.sort(key=lambda r: r["Val"], reverse=True)
    s = s[:UNIVERSE["notes"]]

    for r in s:
        r["G"] = groups.get(r["Code"])

    prev = load_previous(kind="notes", path=path)
    pmap = {r["Code"]: r for r in prev} if prev else {}

    up_all = sum(1 for r in s if r["Chg"] > 0)
    dn_all = sum(1 for r in s if r["Chg"] < 0)
    flat_all = sum(1 for r in s if r["Chg"] == 0)
    tot_val = round(sum(r["Val"] for r in s), 1)

    prev_stat = None
    if prev:
        pu = sum(1 for r in prev if r["Chg"] > 0)
        pd = sum(1 for r in prev if r["Chg"] < 0)
        pv = round(sum(r["Val"] for r in prev), 1)
        prev_stat = {"up": pu, "dn": pd, "total_val": pv,
                     "d_up": up_all - pu, "d_dn": dn_all - pd, "d_val": round(tot_val - pv, 1)}

    # 族群全樣本（含與前份增量）
    grp = {}
    for r in s:
        if r["G"]:
            grp.setdefault(r["G"], []).append(r)
    grp_rows = []
    for g, mem in grp.items():
        n = len(mem)
        v = round(sum(r["Val"] for r in mem), 2)
        u = sum(1 for r in mem if r["Chg"] > 0)
        d = sum(1 for r in mem if r["Chg"] < 0)
        f = sum(1 for r in mem if r["Chg"] == 0)
        av = round(sum(r["Chg"] for r in mem) / n, 2)
        sorted_c = sorted(r["Chg"] for r in mem)
        md = round(sorted_c[n // 2], 2)
        dv = da = 0.0
        if prev:
            pg = [r for r in prev if groups.get(r["Code"]) == g]
            if pg:
                dv = round(v - round(sum(r["Val"] for r in pg), 2), 2)
                da = round(av - round(sum(r["Chg"] for r in pg) / len(pg), 2), 2)
        grp_rows.append({"G": g, "N": n, "V": v, "U": u, "D": d, "F": f,
                         "A": av, "M": md, "DV": dv, "DA": da,
                         "Pct": round(v / tot_val * 100, 2) if tot_val else 0})
    grp_rows.sort(key=lambda r: r["V"], reverse=True)

    def parted(title, cond, key, prevkey=None):
        out = []
        for r in s:
            if cond(r):
                item = {"r": r}
                p = pmap.get(r["Code"])
                if prev and p:
                    item["prev_chg"] = p["Chg"]
                    item["prev_vol"] = p["Vol"]
                else:
                    item["is_new"] = True
                out.append(item)
        out.sort(key=lambda x: x["r"][key], reverse=True)
        return {"title": title, "items": out}

    locks = [
        parted("漲停鎖死", lambda r: r["Chg"] >= LIMIT_PCT and r["AskQ"] == 0, "Val"),
        parted("接近漲停", lambda r: r["Chg"] >= NEAR_UP_PCT and r["AskQ"] > 0, "Chg"),
        parted("跌停鎖死", lambda r: r["Chg"] <= -LIMIT_PCT and r["BidQ"] == 0, "Val"),
        parted("接近跌停", lambda r: r["Chg"] <= NEAR_DOWN_PCT, "Chg"),
        parted("換手異常", lambda r: r["Turn"] >= HOT_TURN, "Turn"),
        parted("假強勢", lambda r: r["Chg"] > 0 and r["Dev"] <= FAKE_DEV, "Val"),
        parted("重挫", lambda r: r["Chg"] <= WEAK_PCT, "Val"),
    ]

    # 翻紅翻黑（與前份比較）
    flipped_red = [r for r in s if r["Chg"] < 0 and r["Code"] in pmap and pmap[r["Code"]]["Chg"] > 0]
    flipped_green = [r for r in s if r["Chg"] > 0 and r["Code"] in pmap and pmap[r["Code"]]["Chg"] < 0]
    flipped_red.sort(key=lambda r: r["Val"], reverse=True)
    flipped_green.sort(key=lambda r: r["Val"], reverse=True)

    # 大幅位移（與前份比）
    big_movers = []
    if prev:
        for r in s:
            p = pmap.get(r["Code"])
            if p and abs(r["Chg"] - p["Chg"]) >= BIG_MOVE_PCT:
                big_movers.append({"r": r, "prev_chg": p["Chg"], "d": round(r["Chg"] - p["Chg"], 2)})
        big_movers.sort(key=lambda x: x["r"]["Val"], reverse=True)
        big_movers = big_movers[:20]

    key_codes = []
    for c in KEY_CODES:
        for r in s:
            if r["Code"] == c:
                p = pmap.get(c)
                key_codes.append({"r": r, "prev_chg": p["Chg"] if p else None,
                                  "prev_vol": p["Vol"] if p else None})
                break

    return {
        "kind": "notes", "file": os.path.basename(path), "stamp": guess_stamp(path),
        "total": len(s), "idx": idx, "up_all": up_all, "dn_all": dn_all,
        "flat_all": flat_all, "tot_val": tot_val, "prev_stat": prev_stat,
        "groups": grp_rows, "locks": locks, "flipped_red": flipped_red,
        "flipped_green": flipped_green, "big_movers": big_movers, "key_codes": key_codes,
        "unclassified": [r for r in s if not r["G"]][:15],
    }


# ============================================================
#  ① 各筆意義判讀：把 raw 欄位轉成「這代表什麼」
# ============================================================
def interpret_stock(r, tot):
    """回傳一串短句，說明這檔的量/價/掛單合起來代表什麼。"""
    tags = []
    chg = r["Chg"]
    val = r["Val"]
    io = r["IO"]
    dev = r["Dev"]
    turn = r["Turn"]
    cap = r["Cap"]

    # 量 vs 漲跌
    is_mega = val >= tot * 0.05  # 前50名某檔佔5%以上，算重磅
    if is_mega and chg < 0:
        tags.append(f"重磅量卻收黑 {fmt_chg(chg)}：資金留在這檔但股價不認帳，偏出貨")
    elif is_mega and chg > 0:
        tags.append(f"重磅量+收紅 {fmt_chg(chg)}：真金白銀在接，是承接型量")
    elif chg < -2 and val >= 20:
        tags.append(f"量大走弱 {fmt_chg(chg)}：量出來方向卻向下")
    elif chg > 2 and val >= 20:
        tags.append(f"量大走強 {fmt_chg(chg)}：有量又有方向")

    # 內外盤比（掛單厚度）
    if 0 < io < 40:
        tags.append(f"內外盤比 {fmt(io,0)}：賣方掛單厚，上檔有壓力")
    elif io > 60:
        tags.append(f"內外盤比 {fmt(io,0)}：買方掛單厚，下檔有撐")

    # 乖離（收盤相對均價）
    if dev <= -2.5:
        tags.append(f"乖離 {fmt(dev,1)}：收在均價下方很多，開高走低、動能弱")
    elif dev >= 2.5:
        tags.append(f"乖離 +{fmt(dev,1)}：收在均價上方很多，尾盤有買盤承接")

    # 換手
    if turn >= 10:
        tags.append(f"換手 {fmt(turn,1)}%：爆量對戰")
    elif turn >= 3 and chg > 5:
        tags.append(f"換手 {fmt(turn,1)}% 高換手卻大漲：籌碼激烈但有人願意接")
    elif turn <= 0.3 and chg >= 9:
        tags.append(f"換手僅 {fmt(turn,2)}% 卻鎖漲：籌碼極輕")

    # 委買委賣極端
    delta = (r["BidQ"] - r["AskQ"]) if (r["BidQ"] + r["AskQ"]) > 0 else 0.0
    total_q = r["BidQ"] + r["AskQ"]
    if total_q > 0 and abs(delta) / total_q > 0.8:
        tags.append("委買/委賣掛單嚴重失衡" + ("（買方厚）" if delta > 0 else "（賣方厚）"))

    return "; ".join(tags) if tags else "量價動能平淡，暫無明顯訊號"


# ============================================================
#  ② 整體結構診斷：整張盤的資金涵義
# ============================================================
def diagnose_structure(groups_rows, all_rows, tot):
    findings = []
    if not groups_rows:
        return []

    biggest = groups_rows[0]
    # 集中度：前50名 vs 全表
    total_all = sum(r["Val"] for r in all_rows) or 1
    concentration = tot / total_all * 100
    if concentration >= 60:
        findings.append(("資金集中度", f"前{50}名成交值 {tot:.0f}億占全表 {concentration:.0f}%，屬高度集中——少數族群在撐盤，像單一主軸行情"))
    elif concentration >= 40:
        findings.append(("資金集中度", f"前{50}名占全表 {concentration:.0f}%，中度集中，資金分散在幾個族群"))

    # 最大族群：量 vs 方向
    if biggest["Avg"] < 0:
        findings.append(("主軸訊號", f"最大資金族群「{biggest['G']}」成交值 {biggest['Val']:.0f}億（佔 {biggest['Pct']:.0f}%）卻收黑（平均 {fmt_chg(biggest['Avg'])}）——主軸在退潮，資金留在原地但方向不認帳，這是今天最重要的盤面訊息"))
    else:
        findings.append(("主軸訊號", f"最大資金族群「{biggest['G']}」成交值 {biggest['Val']:.0f}億（佔 {biggest['Pct']:.0f}%）且收紅（平均 {fmt_chg(biggest['Avg'])}）——有人真金白銀在接，主軸正向"))

    # 上中下游結構：找成交值前幾名的族群是否屬於同一條供應鏈
    # （用族群名關鍵字粗略分層）
    LAYER_MAP = {
        "ABF載板": "基板層", "銅箔基板CCL": "材料層", "PCB": "板廠層",
        "PCB鑽孔設備耗材": "設備層", "記憶體": "顆粒層", "矽晶圓": "材料層",
        "晶圓代工": "生產層", "封測": "封測層", "IP矽智財": "設計層",
    }
    layer_hit = {}
    for g in groups_rows[:10]:
        layer = LAYER_MAP.get(g["G"])
        if layer:
            layer_hit.setdefault(layer, []).append(g["G"])
    if len(layer_hit) >= 3:
        layers = "、".join(f"{l}({'、'.join(v)})" for l, v in layer_hit.items())
        findings.append(("上下游結構", f"資金同時出現在 {layers}——多層供應鏈都有錢，屬「題材型」整鏈定價；反之若只集中在單層，則偏個股消息"))

    # 量小但全紅的族群（小盤輪動）
    small_red = [g for g in groups_rows if g["N"] >= 2 and g["Up"] == g["N"] and g["Val"] <= biggest["Val"] * 0.6]
    small_red.sort(key=lambda g: g["Val"], reverse=True)
    if small_red:
        names = "、".join(g["G"] for g in small_red[:3])
        findings.append(("小盤輪動", f"量較小的「{names}」全紅在走——資金除了穩住主軸，也在往小盤/二線切，屬高低切換手信號"))

    # 全場漲跌家數
    up = sum(1 for r in all_rows if r["Chg"] > 0)
    dn = sum(1 for r in all_rows if r["Chg"] < 0)
    if up > dn * 1.5:
        findings.append(("漲跌家數", f"全表上漲 {up} / 下跌 {dn}，多方家數明顯較多，但散落在中小型（大資金主軸反而收黑）"))
    elif dn > up:
        findings.append(("漲跌家數", f"全表上漲 {up} / 下跌 {dn}，空方家數較多"))

    return findings


# ============================================================
#  ③ 趨勢：載入「前一份」同 kind 快照
# ============================================================
def load_previous(kind, path):
    """回傳前一份快照的 list[dict]，沒有就回傳 None。"""
    snaps = list_snapshots(kind)
    stamps = list(snaps.keys())
    cur = guess_stamp(path)
    if cur not in snaps:
        snaps[cur] = path  # 指定的檔案可能不在目錄清單
        stamps = sorted(snaps.keys())
    idx = stamps.index(cur) if cur in stamps else -1
    if idx <= 0:
        return None
    prev_stamp = stamps[idx - 1]
    return load_csv(snaps[prev_stamp])


def compare_rank(prev_rows, cur_top, cur_all):
    """比較這輪與前輪的資金位移，回傳 list[dict]（依「成交值增減幅度」由大到小，取前 20 檔）。

    verdict：把「資金(成交值)增減」與「股價方向(收紅/收黑)」合看，
    - 量增價漲 → 進貨（資金進場且股價跟漲，多方主導）
    - 量增價跌 → 疑似出貨（有人在這個量出，價不漲反跌）
    - 量縮價漲 → 惜售（沒人賣，但也沒有新資金推）
    - 量縮價跌 → 退潮（資金撤、價走弱）
    """
    prev = [r for r in prev_rows if r["Code"] not in ("TSE", "OTC")]
    prev_map = {r["Code"]: r for r in prev}
    out = []

    def verdict(dv, chg):
        if dv > 0 and chg >= 0:
            return "進貨", "key-red"
        if dv > 0 and chg < 0:
            return "疑似出貨", "key-green"
        if dv < 0 and chg >= 0:
            return "惜售", "key-yellow"
        return "退潮", "key-green"

    # 以「成交值增減幅度」為主角：對前 50 名逐檔與前輪比，幅度大的優先解析
    for r in cur_top:
        p = prev_map.get(r["Code"])
        if not p:
            continue
        dv = r["Val"] - p["Val"]
        dchg = r["Chg"] - p["Chg"]
        if abs(dv) < 2:
            continue  # 成交值變動不到 2 億的跳過（避免雜訊）
        v, cls = verdict(dv, r["Chg"])
        arrow = "▲" if dv > 0 else "▼"
        price_dir = "股價收紅" if r["Chg"] >= 0 else "股價收黑"
        out.append({
            "type": "money",
            "label": r["Name"], "Code": r["Code"],
            "verdict": v, "vcls": cls, "dv": dv,
            "text": f"成交值 {fmt(p['Val'])}({fmt_chg(p['Chg'])}) → {fmt(r['Val'])}億({fmt_chg(r['Chg'])})，" +
                    ("資金流入" if dv > 0 else "資金流出") + f" {fmt(abs(dv))}億、{price_dir}" +
                    (f"，漲幅轉強 {fmt_chg(dchg)}" if dchg > 0 else f"，漲幅轉弱 {fmt_chg(dchg)}")
        })

    out.sort(key=lambda x: abs(x["dv"]), reverse=True)
    return out[:20]


def stamp_display(stamp):
    """yyyyMMdd_HHmmss → 2026-09-04 09:27:10"""
    try:
        return datetime.strptime(stamp, "%Y%m%d_%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return stamp


def guess_stamp(path):
    m = re.search(r"(\d{8}_\d{6})\.csv$", path)
    return m.group(1) if m else "unknown"


# ============================================================
#  一句話結論（供 rank 用）
# ============================================================
def kw(tag, text):
    """把關鍵字包上顏色 class。"""
    return f'<span class="{tag}">{text}</span>'


def one_line_rank(d):
    g = d["groups"]
    if not g:
        return "資料不足，尚無法下結論。"
    biggest = g[0]
    parts = []
    bigcls = "key-green" if biggest["Avg"] < 0 else "key-red"
    if biggest["Avg"] < 0:
        parts.append(f"最大資金族群「{kw(bigcls, biggest['G'])}」({biggest['Val']:.0f}億)卻在{kw('key-green', '收黑')}")
    else:
        parts.append(f"最大資金族群「{kw(bigcls, biggest['G'])}」({biggest['Val']:.0f}億){kw('key-red', '紅盤')}")
    # 找「量小但全紅」的組裝/下游族群
    small_red = [x for x in g if x["N"] >= 2 and x["Up"] == x["N"] and 0 < x["Val"] <= biggest["Val"] * 0.6]
    small_red.sort(key=lambda x: x["Val"], reverse=True)
    if small_red:
        parts.append(f"小股數的「{kw('key-red', small_red[0]['G'])}」{kw('key-red', '全紅')}在走")
    contrad = d["contradictions"]
    if contrad:
        top0 = contrad[0]
        parts.append(f"頭號矛盾「{kw('key-green', top0['Name'])}」量排前卻{kw('key-green', '收黑')}")
    return "今天：" + "；".join(parts) + "。"


# ============================================================
#  HTML 產生
# ============================================================
CSS = """
:root{--up:#d64541;--down:#2e9e5b;--flat:#9a9a9a;--bg:#0f1420;--card:#181f30;--line:#2a3350;--txt:#e8ecf5;--sub:#9aa7c4;--warn:#ffd166;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font-family:'Segoe UI',system-ui,-apple-system,sans-serif;font-size:14px;line-height:1.5}
.wrap{max-width:1060px;margin:0 auto;padding:18px}
header{padding:16px 0 10px;border-bottom:1px solid var(--line)}
h1{font-size:20px;margin:0 0 4px}
.meta{color:var(--sub);font-size:12.5px}
.verdict{background:linear-gradient(135deg,#1d2a4a,#232f4e);border:1px solid #31406a;border-left:5px solid var(--warn);border-radius:10px;padding:14px 16px;margin:16px 0;font-size:16px;font-weight:600}
.verdict small{display:block;color:var(--sub);font-weight:400;font-size:12px;margin-top:4px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:16px 0}
.card h2{font-size:14px;margin:0 0 10px;color:var(--sub);text-transform:uppercase;letter-spacing:.5px}
table{width:100%;border-collapse:collapse}
th,td{padding:7px 8px;text-align:left;border-bottom:1px solid #222b40;font-variant-numeric:tabular-nums}
th{color:var(--sub);font-size:12px;font-weight:600;cursor:pointer;user-select:none;white-space:nowrap}
th:hover{color:var(--txt)}
tr:hover td{background:#1c2438}
.num{text-align:right}
.up{color:var(--up);font-weight:600}.down{color:var(--down);font-weight:600}.flat{color:var(--flat)}
.barwrap{background:#202a44;border-radius:4px;height:14px;width:100%;overflow:hidden}
.bar{height:100%;border-radius:4px}
.pill{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11.5px;font-weight:600;margin-left:6px}
.pill.up{color:var(--up);background:rgba(214,69,65,.12)}
.pill.down{color:var(--down);background:rgba(46,158,91,.12)}
.pill.flat{color:var(--flat);background:rgba(154,154,154,.12)}
.contra-card{background:#2a1a1d;border:1px solid #5a2530;border-left:5px solid var(--up);border-radius:10px;padding:12px 14px;margin:10px 0}
.contra-card .t{font-weight:700;font-size:15px}
.contra-card .w{color:#ff9f9a;font-size:12.5px;margin-top:3px}
.contra-card .why{color:var(--warn);font-size:12.5px;margin-top:5px}
.diag{display:flex;flex-wrap:wrap;gap:10px}
.diag-item{flex:1;min-width:220px;background:#1d2840;border:1px solid #2f3d63;border-radius:10px;padding:10px 12px}
.diag-item .k{display:block;font-size:11px;color:var(--sub);text-transform:uppercase;letter-spacing:.5px;margin-bottom:4px}
.diag-item .v{font-size:13px}
.diag-item.alert{background:#2a1a1d;border-color:#5a2530}
.flow{background:#202a44;border-radius:4px;height:12px;width:100%;overflow:hidden}
.flow .fbar{height:100%;border-radius:4px}
.key-red{color:var(--up);font-weight:700}
.key-green{color:var(--down);font-weight:700}
.key-yellow{color:var(--warn);font-weight:700}
.trend-item{background:#1b2438;border:1px solid #2c3858;border-radius:8px;padding:8px 12px;margin:6px 0;font-size:13px}
.trend-item .arrow{font-weight:700;margin-right:6px}
.trend-empty{color:var(--sub);font-style:italic;font-size:13px}
.stock-why{color:#b9c3dd;font-size:12px;font-weight:400}
.watch li{margin:4px 0}
.tip{border-bottom:1px dashed #3a4568;cursor:help}
.rest-row{display:none}
.rest-inline{display:none}
.expand-btn{background:#243156;border:1px solid #3a4a7a;color:#cfe0ff;border-radius:20px;padding:4px 16px;font-size:12.5px;font-weight:600;cursor:pointer;margin-top:8px}
.expand-btn:hover{background:#31406a}
.copybtn{background:#1d2840;border:1px solid #2f3d63;color:#bcd2ff;border-radius:14px;padding:3px 12px;font-size:11.5px;font-weight:600;cursor:pointer;margin-left:10px;vertical-align:middle}
.copybtn:hover{background:#31406a}
.copybtn.copied{background:#2e9e5b;color:#fff;border-color:#3cbf77}
.rest-open .rest-row{display:table-row}
.rest-open .rest-inline{display:block}
.unclassified{color:var(--warn)}
.tag{display:inline-block;padding:1px 8px;border-radius:8px;font-size:11px;font-weight:700;margin:1px}
.tag.RALLY{background:#5a2030;color:#ffb3ad}.tag.SELLOFF{background:#1e4a34;color:#a5e8c3}.tag.SPLIT{background:#4a3a1e;color:#ffe0a0}.tag.SOLO{background:#28406a;color:#bcd2ff}.tag.THIN{background:#333;color:#bbb}
.footer{color:var(--sub);font-size:11.5px;border-top:1px solid var(--line);padding-top:10px;margin-top:18px}
.tabbar{display:flex;gap:8px;margin:14px 0 4px;border-bottom:1px solid var(--line);padding-bottom:8px;flex-wrap:wrap}
.tabbtn{background:none;border:none;color:var(--sub);font-size:14px;font-weight:600;padding:6px 14px;cursor:pointer;border-radius:8px}
.tabbtn.active{background:#31406a;color:#fff}
.histbar{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin:10px 0}
.dot{background:#1d2840;border:1px solid #2f3d63;color:#bcd2ff;border-radius:14px;padding:4px 10px;font-size:11.5px;cursor:pointer;min-width:52px;text-align:center}
.dot.active{background:#4a3a1e;border-color:var(--warn);color:#ffe0a0;font-weight:700}
.dot.today{outline:2px solid #ff6b6b}
.dot.yest{outline:2px solid #9ad0e0}
.histnote{color:var(--sub);font-size:12px;margin:8px 0 4px}
.postmarket blockquote{border-left:3px solid var(--line);margin:8px 0;padding:2px 12px;color:var(--sub)}
.postmarket code{background:#1b2438;border:1px solid #2c3858;border-radius:4px;padding:1px 5px;font-size:12px}
.postmarket table{margin:8px 0}
.pm-stock{padding:2px 0 10px;margin:10px 0 12px;border-bottom:1px solid var(--line)}
.pm-stock:last-of-type{border-bottom:none}
.pm-stock .pm-name{font-size:14.5px;font-weight:700;margin-bottom:4px;color:var(--txt);display:flex;align-items:center;flex-wrap:wrap}
.pm-stock .pm-name b{color:var(--txt)}
.pm-stock .pm-name b.key-red{color:var(--up)}
.pm-stock .pm-name b.key-green{color:var(--down)}
.pm-stock .pm-detail{margin:2px 0;font-size:12.5px;color:var(--txt)}
.pm-stock .pm-detail .pm-k{border-radius:4px;padding:0 5px;font-size:11.5px;font-weight:700;background:#243156;color:#bcd2ff;margin-right:6px}
.pm-copyhint{color:var(--sub);font-size:11.5px;margin:2px 0 8px}
.pm-str{color:var(--sub);font-weight:400;font-size:12.5px;margin-left:8px}
.pm-stk{color:#7fa8dd;font-weight:600}
.postmarket .pm-stk.up{color:var(--up)}
.postmarket .pm-stk.down{color:var(--down)}
.pm-num{color:#ffab40;font-weight:500}
.postmarket .pm-sub{display:inline-block;border-radius:4px;padding:0 6px;font-size:12px;font-weight:700;background:#243156;color:#bcd2ff;margin-right:6px}
.pm-mg{display:inline-block;border-radius:4px;padding:0 6px;font-size:13px;font-weight:700;background:#4d1c2b;color:#e7748a;margin-right:6px}
.postmarket .pm-sub.pm-mg{background:#4d1c2b;color:#e7748a}
.postmarket .pm-sub.pm-judge{background:#4a3a10;color:#e0b34d}
.pm-idx{display:inline-flex;align-items:center;justify-content:center;min-width:20px;height:20px;border-radius:4px;background:#4a3a10;color:#e0b34d;font-size:12.5px;font-weight:800;margin-right:8px}
.pm-pxwarn{display:block;margin:4px 0 2px;font-size:11.5px;font-weight:700;color:#ff9d4d;background:rgba(255,157,77,.1);border:1px solid rgba(255,157,77,.35);border-radius:4px;padding:2px 6px}
.pm-note{display:inline-block;margin-left:8px;font-size:11.5px;font-weight:500;color:#ffab40;vertical-align:middle}
.postmarket .card li{margin:4px 0}
@media(max-width:640px){.wrap{padding:10px;font-size:13px}.hide-sm{display:none}}
"""

JS = """
function sortTable(th){
  var t=th.closest('table');
  var i=+th.getAttribute('data-idx');
  var body=t.tBodies[0], rows=[].slice.call(body.rows);
  var asc=t.getAttribute('data-asc')!=='1';
  rows.sort(function(a,b){
    var av=a.cells[i].getAttribute('data-n'), bv=b.cells[i].getAttribute('data-n');
    if(av!=null&&bv!=null){return asc?(+av)-(+bv):(+bv)-(+av);}
    var x=a.cells[i].textContent,y=b.cells[i].textContent;
    return asc?x.localeCompare(y,'zh-TW',{numeric:true}):y.localeCompare(x,'zh-TW',{numeric:true});
  });
  for(var j=0;j<rows.length;j++)body.appendChild(rows[j]);
  // 重新套用縮表規則：前 5 顯示、其餘收合（排序後仍成立）
  for(var j=0;j<rows.length;j++)rows[j].classList.toggle('rest-row', j>=5);
  var cardId=t.getAttribute('data-card');
  if(cardId){var cb=document.querySelector('.expand-btn[data-wrap="'+cardId+'"]');if(cb){cb.textContent=cb.getAttribute('data-expand');}}
  t.setAttribute('data-asc',asc?'0':'1');
}
function copyStocks(btn){
  var card=btn.closest('.card');
  var seen={}, out=[];
  var els=card.querySelectorAll('[data-code]');
  for(var i=0;i<els.length;i++){
    var c=(els[i].getAttribute('data-code')||'').trim();
    if(c&&!seen[c]){seen[c]=1;out.push(c+'\\t'+els[i].getAttribute('data-name'));}
  }
  var rows=[];
  if(out.length){
    rows=[out.join('\\n')];
  }else{
    var tbl=card.querySelector('table');
    if(tbl){
      for(var r=0;r<tbl.rows.length;r++){
        var cellTxt=[];
        for(var cc=0;cc<tbl.rows[r].cells.length;cc++){
          cellTxt.push(tbl.rows[r].cells[cc].innerText.replace(/\\s+/g,' ').trim());
        }
        rows.push(cellTxt.join('\\t'));
      }
    }
  }
  if(!rows.length){return;}
  var text=rows.join('\\n');
  function done(){btn.classList.add('copied');btn.textContent='已複製 '+rows.length+' 項';setTimeout(function(){btn.classList.remove('copied');btn.textContent='📋';},1600);}
  function fb(){var ta=document.createElement('textarea');ta.value=text;document.body.appendChild(ta);ta.select();document.execCommand('copy');document.body.removeChild(ta);done();}
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(text).then(done,fb);}else{fb();}
}
function toggleRest(btn){
  var wrap=document.getElementById(btn.getAttribute('data-wrap'));
  var open=wrap.classList.toggle('rest-open');
  btn.textContent=open?btn.getAttribute('data-collapse'):btn.getAttribute('data-expand');
}
"""


def render_head(title, stamp, extra_meta=""):
    return f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{CSS}</style></head><body><div class="wrap">
<header><h1>{title}</h1><div class="meta">快照 {stamp_display(stamp)} {extra_meta}</div></header>"""


def render_foot():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""<div class="footer">本看板由快照自動產生（{now}）。盤中資料到收盤前仍會變動；僅描述資金結構與盤面事實，不含買賣建議或目標價推測。</div>
<script>{JS}</script></div></body></html>"""


def _render_watch(d):
    """該盯的變數：列出 2-3 個接下來值得追蹤的客觀盤面訊號（不帶方向）。"""
    items = []
    kind = d["kind"]
    if kind == "rank":
        if d["groups"]:
            g0 = d["groups"][0]
            items.append(f"資金主軸「{g0['G']}」的成交值比重（目前 {g0['Pct']:.0f}%）能否維持，還是轉向次大族群")
        if d["contradictions"]:
            c0 = d["contradictions"][0]
            items.append(f"「{c0['Name']}」量排前卻收黑——下一輪看它是否翻紅（資金回流）或續跌（確認出貨）")
        else:
            items.append("前幾名資金是否出現「量增價滯」（成交值放大但漲幅收斂）的訊號")
    elif kind == "breadth":
        rally = [g for g in d["rows"] if "RALLY" in g["Tags"]]
        sell = [g for g in d["rows"] if "SELLOFF" in g["Tags"]]
        if rally:
            items.append(f"「{rally[0]['G']}」齊漲的續航力——下一輪看齊漲檔數是否維持或退化成分歧")
        if sell:
            items.append(f"「{sell[0]['G']}」齊跌是否擴散到其他族群，還是止跌翻紅")
        if not items:
            items.append("目前沒有族群齊漲/齊跌——看哪些族群浮出「整齊方向」")
        if d["signals"] and d["signals"][0]["items"]:
            s0 = d["signals"][0]["items"][0]
            items.append(f"漲停鎖死「{s0['Name']}」的委賣掛單是否一直掛 0（鎖死強度）")
    elif kind == "notes":
        if d["groups"]:
            g0 = d["groups"][0]
            items.append(f"資金主軸「{g0['G']}」的成交值增量方向（目前較前份 {g0['DV']:+.1f}億）")
        if d["flipped_red"]:
            items.append(f"翻黑股「{d['flipped_red'][0]['Name']}」下一輪是否續弱（確認轉弱）或翻回（假摔）")
        else:
            items.append("今日是否有權值股與中小型脫節（台積電不動但中小型激烈）")
    h = '<div class="card"><h2>該盯的變數（下一輪快照出來後的追蹤重點）</h2><ul class="watch">'
    for it in items[:3]:
        h += f"<li>{it}</li>"
    h += "</ul><div class='meta'>只列客觀可追蹤的訊號，不含看多看空方向。</div></div>"
    return h


def render_rank(d):
    h = render_head(f"族群資金排行 — {stamp_display(d['stamp'])} 盤中", d["stamp"],
                    f"· 全表 {d['total']} 檔 · 前 {d['top_n']} 名成交值合計 <b>{d['top_total']} 億</b>")
    h += f"""
<div class="verdict">{one_line_rank(d)}<small>一句話結論：把這張盤面最重要的一件事先講給你看。（關鍵字上色：<span class="key-red">紅色＝看多</span>、<span class="key-green">綠色＝看空</span>）</small></div>"""

    # ② 整體結構診斷
    h += '<div class="card"><h2>📊 這盤的資金結構診斷（整體涵義）</h2><div class="diag">'
    for k, v in d["structure"]:
        alert = " alert" if k in ("主軸訊號", "資金集中度") else ""
        h += f'<div class="diag-item{alert}"><span class="k">{k}</span><div class="v">{v}</div></div>'
    h += "</div></div>"

    # 巨額矛盾警示卡
    if d["contradictions"]:
        h += '<div class="card"><h2>⚠ 頭號矛盾：量很大、股價卻收黑</h2>'
        h += '<div class="meta" style="margin-bottom:8px">資金還停在這裡，但股價不認帳——通常是出貨重的量，不是承接重的量。</div>'
        for r in d["contradictions"]:
            h += f"""<div class="contra-card">
  <div class="t"><span class="key-green">{r['Rk']}. {r['Name']}</span> <span class="pill down">{r['Grp']}</span></div>
  <div class="w">{fmt_chg(r['Chg'])} · 成交值 {fmt(r['Val'])}億（全場第 {r['Rk']} 大）· 內外盤比 {fmt(r['IO'],0)} · 乖離 {fmt(r['Dev'],1)}</div>
  <div class="why">這代表什麼：{r['Why']}</div></div>"""
        h += "</div>"

    # 族群資金表（橫條）—— 預設依平均漲幅由高到低，點欄位名可排序
    grp_disp = sorted(d["groups"], key=lambda x: x["Avg"], reverse=True)
    h += '<div class="card" id="grp-card"><h2>族群資金表 · 點欄位名可排序 <button class="copybtn" onclick="copyStocks(this)" title="複製本表全部股號與股名">📋</button></h2>'
    h += '<div class="meta" style="margin-bottom:8px"><span class="tip" data-id="0">佔前50%</span>＝族群成交值 ÷ 前50名總值；<span class="tip" data-id="1">漲跌家數</span>＝紅綠各幾檔。預設依平均漲幅由高到低。</div>'
    h += '<table id="grp" data-card="grp-card"><thead><tr>'
    headers = [("族群", "text"), ("成交值(億)", "num"), ("佔前50%", "num"), ("平均漲幅", "num"), ("漲跌", "text"), ("代表股", "text")]
    for i, (name, cls) in enumerate(headers):
        h += f'<th data-idx="{i}" class="{cls}" onclick="sortTable(this)">{name}</th>'
    h += "</tr></thead><tbody>"
    maxval = d["groups"][0]["Val"] if d["groups"] else 1
    for gi, gr in enumerate(grp_disp):
        rest = ' class="rest-row"' if gi >= 5 else ""
        barc = "up" if gr["Avg"] >= 0 else "down"
        members = " ".join(f'<b class="{chg_class(m["Chg"])}" data-code="{m["Code"]}" data-name="{m["Name"]}">{m["Name"]}</b>({fmt(m["Val"])}億,{fmt_chg(m["Chg"])})' for m in gr["Mem"][:4])
        h += f"""<tr{rest}>
  <td data-n="0"><b>{gr['G']}</b> <span class="pill {chg_class(gr['Avg'])}">{gr['N']}檔</span></td>
  <td data-n="{gr['Val']}" class="num">{fmt(gr['Val'])}</td>
  <td data-n="{gr['Pct']}" class="num">{fmt(gr['Pct'])}%</td>
  <td data-n="{gr['Avg']}" class="num {chg_class(gr['Avg'])}">{fmt_chg(gr['Avg'])}</td>
  <td data-n="{gr['Up']-gr['Dn']}" class="num">{gr['Up']}<span class="up">↑</span> {gr['Dn']}<span class="down">↓</span></td>
  <td>{members}</td></tr>"""
    h += "</tbody></table>"
    if len(d["groups"]) > 5:
        h += f'<button class="expand-btn" data-wrap="grp-card" data-expand="展開全部（共 {len(d["groups"])} 群）" data-collapse="收回 5 群" onclick="toggleRest(this)">展開全部（共 {len(d["groups"])} 群）</button>'
    h += "</div>"  # end groups card

    # ① 個股詮釋：依「各股漲跌幅」前 30 檔逐檔解讀（縮表顯示 5 檔）
    stk_sel = sorted(d["top"], key=lambda r: abs(r["Chg"]), reverse=True)[:30]
    h += '<div class="card" id="stk-card"><h2>🎯 逐檔解讀（漲跌幅前 30 · 各檔量價合起來代表什麼） <button class="copybtn" onclick="copyStocks(this)" title="複製本表全部股號與股名">📋</button></h2>'
    for si, r in enumerate(stk_sel):
        tagclass = chg_class(r["Chg"])
        rest = " rest-inline" if si >= 5 else ""
        h += f"""<div class="trend-item{rest}">
  <b>{r['Rk']}.</b> <b class="key-{'red' if r['Chg']>0 else 'green' if r['Chg']<0 else 'yellow'}" data-code="{r['Code']}" data-name="{r['Name']}">{r['Name']}</b>
  <span class="pill {tagclass}">{r['Grp']}</span>
  <span class="num" style="float:right">{fmt_chg(r['Chg'])} · {fmt(r['Val'])}億</span>
  <div class="stock-why">{r['Why']}</div>
</div>"""
    h += f'<button class="expand-btn" data-wrap="stk-card" data-expand="展開全部 30 檔" data-collapse="收回 5 檔" onclick="toggleRest(this)">展開全部 30 檔</button>'
    h += "</div>"

    # ③ 趨勢：與前一份快照比較（依成交值增減幅度前 20，縮表顯示 5 檔）
    n_trend = len(d["trend"]) if d["trend"] else 0
    h += f'<div class="card" id="trend-card"><h2>📈 資金位移（與前一份快照比 · 成交值增減，達標 {n_trend} 檔）：資金增減 ＋ 股價方向合看，判讀進貨／出貨 <button class="copybtn" onclick="copyStocks(this)" title="複製本表全部股號與股名">📋</button></h2>'
    if d["trend"]:
        for ti, it in enumerate(d["trend"]):
            arrow = "<span class='arrow key-red'>▲</span>" if it["dv"] > 0 else "<span class='arrow key-green'>▼</span>"
            vtag = f'<span class="pill {it["vcls"]}">{it["verdict"]}</span>'
            rest = " rest-inline" if ti >= 5 else ""
            h += f'<div class="trend-item{rest}">{arrow}<b data-code="{it["Code"]}" data-name="{it["label"]}">{it["label"]}</b> {vtag} {it["text"]}</div>'
        h += f'<button class="expand-btn" data-wrap="trend-card" data-expand="展開全部 {n_trend} 檔" data-collapse="收回 5 檔" onclick="toggleRest(this)">展開全部 {n_trend} 檔</button>'
    else:
        h += f'<div class="trend-empty">尚無前一份快照可比較（目前僅掃描到 {d["history_count"]} 份歷史快照）。下一次盤中捕捉到新的同類快照後，此區會自動顯示這輪與前輪的資金位移。</div>'
    h += "</div>"

    # 未分類
    h += '<div class="card"><h2>待補族群對照</h2>'
    if d["unclassified"]:
        h += '<div class="meta" style="margin-bottom:6px">以下個股未命中分類表，請補進 groups.ps1 後重跑。</div>'
        h += ", ".join(f'<span class="unclassified">{r["Code"]} {r["Name"]}（{fmt(r["Val"])}億,{fmt_chg(r["Chg"])}）</span>' for r in d["unclassified"])
    else:
        h += "無——前 50 名全數命中分類表。"
    h += "</div>"

    # 該盯的變數
    h += _render_watch(d)

    h += render_foot()
    return h


# ============================================================
#  作法二：齊漲分歧診斷 ─ 一句話結論 + HTML
# ============================================================
TAG_LABEL = {
    "RALLY": "齊漲", "SELLOFF": "齊跌", "SPLIT": "分歧",
    "SOLO": "獨走", "THIN": "樣本不足",
}


def one_line_breadth(d):
    rows = d["rows"]
    if not rows:
        return "資料不足，尚無法下結論。"
    parts = []
    rally = [g for g in rows if "RALLY" in g["Tags"]]
    sell = [g for g in rows if "SELLOFF" in g["Tags"]]
    if sell and (not rally or sell[0]["Val"] >= rows[0]["Val"] * 0.8):
        big = sell[0]
        parts.append(f"最大資金族群「{kw('key-green', big['G'])}」({big['Val']:.0f}億)正在{kw('key-green', '退潮齊跌')}({big['Dn']}/{big['N']})")
    elif rally and sell:
        if rally[0]["Val"] > sell[0]["Val"]:
            parts.append(f"資金主軸「{kw('key-red', rally[0]['G'])}」{kw('key-red', '齊漲')}，但「{kw('key-green', sell[0]['G'])}」在{kw('key-green', '退潮')}")
        else:
            parts.append(f"資金主軸「{kw('key-green', sell[0]['G'])}」{kw('key-green', '退潮')}，只有「{kw('key-red', rally[0]['G'])}」在{kw('key-red', '齊漲')}")
    elif rally:
        big = rally[0]
        parts.append(f"資金主軸「{kw('key-red', big['G'])}」({big['Val']:.0f}億){kw('key-red', '齊漲')}({big['Up']}/{big['N']})")
    else:
        biggest = rows[0]
        parts.append(f"資金主軸「{kw('key-yellow', biggest['G'])}」({biggest['Val']:.0f}億){kw('key-yellow', '沒有一致方向')}，資金在族內挑選")
    return "今天：" + "；".join(parts) + "。"


def render_breadth(d):
    h = render_head(f"齊漲分歧診斷 — {stamp_display(d['stamp'])} 盤中", d["stamp"],
                    f"· 分析範圍 成交值前 <b>{d['top_n']}</b> 名（第 {d['top_n']} 名 {fmt(d['cut']['Val']) if d['cut'] else '-'}億）· 全表 {d['total']} 檔")
    h += f"""
<div class="verdict">{one_line_breadth(d)}<small>一句話結論：先判斷「這張盤是大家一起向同一個方向，還是資金只在一檔身上」。（上色：紅=偏多、綠=偏空）</small></div>"""

    # 漲跌家數
    h += '<div class="card"><h2>📊 盤面廣度（前 {top_n} 名 vs 全表）</h2>'.replace("{top_n}", str(d["top_n"]))
    h += f"""<div class="diag">
  <div class="diag-item"><span class="k">前 {d['top_n']} 名</span><div class="v"><span class="up">{d['up_top']}</span>↑ / <span class="down">{d['dn_top']}</span>↓ / <span class="flat">{d['flat_top']}</span>–</div></div>
  <div class="diag-item"><span class="k">全表</span><div class="v"><span class="up">{d['up_all']}</span>↑ / <span class="down">{d['dn_all']}</span>↓</div></div>
  <div class="diag-item"><span class="k">未分類</span><div class="v">{len(d['unclassified'])} 檔在前 {d['top_n']} 名內</div></div>
</div></div>"""

    # 最反直覺
    if d["counter"]:
        h += '<div class="card" style="border-left:5px solid var(--up)"><h2>⚡ 最反直覺的一件事</h2>'
        for c in d["counter"]:
            h += f'<div class="contra-card"><div class="t">反直覺</div><div class="why">{c}</div></div>'
        h += "</div>"

    # 齊漲族群表（平均漲幅由高到低）
    rally = [g for g in d["rows"] if "RALLY" in g["Tags"]]
    rally.sort(key=lambda g: g["Avg"], reverse=True)
    h += '<div class="card" id="rally-card"><h2>🔴 齊漲族群（上漲比 ≥ 0.75 且 ≥ 3 檔）<button class="copybtn" onclick="copyStocks(this)" title="複製本表全部股號與股名">📋</button></h2>'
    if rally:
        h += _grp_align_table(rally, up=True, card_id="rally-card")
    else:
        h += '<div class="trend-empty">無——沒有任何族群達到齊漲門檻。</div>'
    h += "</div>"

    # 齊跌族群表（平均漲幅由高到低）
    sell = [g for g in d["rows"] if "SELLOFF" in g["Tags"]]
    sell.sort(key=lambda g: g["Avg"], reverse=True)
    h += '<div class="card" id="sell-card"><h2>🟢 齊跌族群（下跌比 ≥ 0.75 且 ≥ 3 檔）<button class="copybtn" onclick="copyStocks(this)" title="複製本表全部股號與股名">📋</button></h2>'
    if sell:
        h += _grp_align_table(sell, up=False, card_id="sell-card")
    else:
        h += '<div class="trend-empty">無——沒有任何族群達到齊跌門檻。</div>'
    h += "</div>"

    # 內部分歧（平均漲幅由高到低）
    split = [g for g in d["rows"] if "SPLIT" in g["Tags"]]
    split.sort(key=lambda g: g["Avg"], reverse=True)
    h += '<div class="card"><h2>⚖️ 內部分歧（同族群同時有 ≥+3% 與 ≤-3% 成員）<button class="copybtn" onclick="copyStocks(this)" title="複製本表全部股號與股名">📋</button></h2>'
    if split:
        h += '<div class="meta" style="margin-bottom:8px">資金在族內挑選、不是整組行情。成交值最大的分歧族群特別重要。</div>'
        for g in split:
            alert = " contra-card" if g is split[0] and g["Val"] >= (split[1]["Val"] if len(split) > 1 else 0) * 1.05 else ""
            h += f"""<div class="trend-item{'_contra' if alert else ''}">
  <b>{g['G']}</b> <span class="pill">{g['N']}檔</span> · 成交值 {g['Val']}億 · 高 <b class="up">{g['Hi']:+.1f}%</b> / 低 <b class="down">{g['Lo']:+.1f}%</b>
  <div class="stock-why">{_grp_member_str(g)}</div></div>"""
    else:
        h += '<div class="trend-empty">無——資金主軸族群方向一致，內部無明顯分歧。</div>'
    h += "</div>"

    # 個別表現 SOLO
    solo = [g for g in d["rows"] if "SOLO" in g["Tags"]]
    solo.sort(key=lambda g: g["Avg"], reverse=True)
    h += '<div class="card"><h2>🎯 個別表現獨走（僅 1 檔 ≥+5%，其餘在 ±2%內）<button class="copybtn" onclick="copyStocks(this)" title="複製本表全部股號與股名">📋</button></h2>'
    if solo:
        for g in solo:
            h += f"""<div class="trend-item"><b>{g['G']}</b> · {g['N']}檔 · 成交值 {g['Val']}億
  <div class="stock-why">{_grp_member_str(g)}</div></div>"""
    else:
        h += '<div class="trend-empty">無——成交值前 200 名內沒有任何族群呈獨走型態。</div>'
    h += "</div>"

    # 個股訊號清單
    h += '<div class="card"><h2>🚨 個股訊號 <button class="copybtn" onclick="copyStocks(this)" title="複製本表全部股號與股名">📋</button></h2>'
    for sg in d["signals"]:
        h += f'<div class="trend-item" style="margin-top:10px"><b>{sg["title"]}</b> <span class="meta">（{sg["detail"]}）</span>'
        if sg["items"]:
            h += '<div style="margin-top:5px">' + " ".join(
                f'<span class="pill {chg_class(x["Chg"])}" data-code="{x["Code"]}" data-name="{x["Name"]}">{x["Name"]}</span> {fmt_chg(x["Chg"])} · {fmt(x["Val"])}億'
                for x in sg["items"][:6]) + "</div>"
        else:
            h += ' <span class="trend-empty">無</span>'
        h += "</div>"
    h += "</div>"

    # 樣本不足
    thin = [g for g in d["rows"] if "THIN" in g["Tags"]]
    h += '<div class="card"><h2>樣本不足（&lt;3 檔，不判定整齊度）</h2>'
    if thin:
        h += ", ".join(f'<span class="key-yellow">{g["G"]}</span>(n={g["N"]})' for g in thin)
    else:
        h += "無。"
    h += "</div>"

    # 未分類
    h += '<div class="card"><h2>待補族群對照</h2>'
    if d["unclassified"]:
        h += ', '.join(f'<span class="unclassified">{x["Code"]} {x["Name"]}（{fmt(x["Val"])}億,{fmt_chg(x["Chg"])}）</span>' for x in d["unclassified"])
    else:
        h += "無——前 200 名全數命中分類表。"
    h += "</div>"

    # 該盯的變數
    h += _render_watch(d)

    h += render_foot()
    return h


def _grp_align_table(groups, up=True, card_id="grp-card"):
    """齊漲/齊跌共用的族群表格。"""
    h = f'<table id="align" data-card="{card_id}"><thead><tr><th data-idx="0" onclick="sortTable(this)">族群</th><th data-idx="1" class="num" onclick="sortTable(this)">整齊度</th><th data-idx="2" class="num" onclick="sortTable(this)">成交值(億)</th><th data-idx="3" class="num" onclick="sortTable(this)">平均漲幅</th><th data-idx="4" onclick="sortTable(this)">成員（漲幅）</th></tr></thead><tbody>'
    for gi, g in enumerate(groups):
        cls = "up" if up else "down"
        rest = ' class="rest-row"' if gi >= 5 else ""
        h += f"""<tr{rest}>
  <td><b>{g['G']}</b> <span class="pill {cls}">{g['N']}檔</span></td>
  <td data-n="{g['Ratio']}" class="num">{g['Up' if up else 'Dn']}/{g['N']}</td>
  <td data-n="{g['Val']}" class="num">{g['Val']}</td>
  <td data-n="{g['Avg']}" class="num {chg_class(g['Avg'])}">{fmt_chg(g['Avg'])}</td>
  <td>{_grp_member_str(g)}</td></tr>"""
    h += "</tbody></table>"
    if len(groups) > 5:
        h += f'<button class="expand-btn" data-wrap="{card_id}" data-expand="展開全部（共 {len(groups)} 群）" data-collapse="收回 5 群" onclick="toggleRest(this)">展開全部（共 {len(groups)} 群）</button>'
    return h


def _grp_member_str(g):
    return " ".join(
        f'<b class="{chg_class(x["Chg"])}" data-code="{x["Code"]}" data-name="{x["Name"]}">{x["Name"]}</b>({fmt_chg(x["Chg"])})' for x in g["Mem"][:8])


# ============================================================
#  作法三：盤中觀察三段 ─ 一句話結論 + HTML
# ============================================================
def one_line_notes(d):
    parts = []
    if d["prev_stat"]:
        dv = d["prev_stat"]["d_val"]
        if dv >= 20:
            parts.append(f"總成交值較上份{kw('key-red', '放大')} {dv:+.0f}億");
        elif dv <= -20:
            parts.append(f"總成交值較上份{kw('key-green', '收縮')} {dv:+.0f}億")
    gmax = d["groups"][0] if d["groups"] else None
    if gmax:
        if gmax["DV"] > 5:
            parts.append(f"資金主軸「{kw('key-red', gmax['G'])}」持續流入 {gmax['DV']:+.1f}億")
        elif gmax["DV"] < -5:
            parts.append(f"資金主軸「{kw('key-green', gmax['G'])}」流出 {gmax['DV']:+.1f}億")
        if gmax["D"] >= gmax["U"] and (gmax["U"] + gmax["D"]) >= 3:
            parts.append(f"但「{kw('key-green', gmax['G'])}」內部{kw('key-green', '走弱')}({gmax['U']}↑/{gmax['D']}↓)")
        elif gmax["U"] > gmax["D"] * 2 and gmax["U"] >= 3:
            parts.append(f"且「{kw('key-red', gmax['G'])}」內部同調走強({gmax['U']}↑)")
    if not parts:
        parts.append("盤面變動不大，資金主軸維持不變")
    return "這一輪：" + "；".join(parts) + "。"


def render_notes(d):
    h = render_head(f"盤中觀察三段 — {stamp_display(d['stamp'])} 盤中", d["stamp"],
                    f"· 全樣本 {d['total']} 檔" +
                    (f" · 比較基準 {stamp_display(d.get('prev_stamp', ''))}" if d.get("prev_stamp") else " · 尚無前一份可比"))
    h += f"""
<div class="verdict">{one_line_notes(d)}<small>一句話結論：這一段時間（跟上一份快照比）盤面最重要的變化。</small></div>"""

    # 指數 + 廣度
    h += '<div class="card"><h2>📊 大盤與廣度</h2>'
    h += '<div class="diag">'
    for i in d["idx"]:
        h += f'<div class="diag-item"><span class="k">{i["Name"]}</span><div class="v"><span class="{chg_class(i["Chg"])}">{fmt_chg(i["Chg"])}</span> · {i["Close"]} · 成交值 {fmt(i["Val"])}億</div></div>'
    h += f'<div class="diag-item"><span class="k">漲跌家數</span><div class="v"><span class="up">{d["up_all"]}</span>↑ / <span class="down">{d["dn_all"]}</span>↓ / <span class="flat">{d["flat_all"]}</span>– · 總成交值 <b>{d["tot_val"]}億</b></div></div>'
    if d["prev_stat"]:
        p = d["prev_stat"]
        h += f'<div class="diag-item"><span class="k">vs 前一輪</span><div class="v">總值 {p["d_val"]:+.1f}億 · 上漲家數 {p["d_up"]:+d}</div></div>'
    h += "</div></div>"

    grpnotes_all = sorted(d["groups"], key=lambda x: x["A"], reverse=True)
    h += '<div class="card" id="grpnotes-card"><h2>族群成交值（全樣本 · 依平均漲幅排序）<button class="copybtn" onclick="copyStocks(this)" title="複製本表全部股號與股名">📋</button></h2>'
    h += '<table id="grpnotes" data-card="grpnotes-card"><thead><tr><th data-idx="0" onclick="sortTable(this)">族群</th><th data-idx="1" class="num" onclick="sortTable(this)">成交值(億)</th><th data-idx="2" class="num" onclick="sortTable(this)">佔比</th><th data-idx="3" class="num" onclick="sortTable(this)">漲跌</th><th data-idx="4" class="num" onclick="sortTable(this)">平均漲幅</th><th data-idx="5" class="num" onclick="sortTable(this)">vs前份</th></tr></thead><tbody>'
    for gi, g in enumerate(grpnotes_all):
        dvcls = chg_class(g["DV"]) if g["DV"] else "flat"
        rest = ' class="rest-row"' if gi >= 5 else ""
        h += f"""<tr{rest}>
  <td><b>{g['G']}</b> <span class="pill">{g['N']}檔</span></td>
  <td data-n="{g['V']}" class="num">{g['V']}</td>
  <td data-n="{g['Pct']}" class="num">{g['Pct']}%</td>
  <td data-n="{g['U']-g['D']}" class="num">{g['U']}<span class="up">↑</span> {g['D']}<span class="down">↓</span></td>
  <td data-n="{g['A']}" class="num {chg_class(g['A'])}">{fmt_chg(g['A'])}</td>
  <td data-n="{g['DV']}" class="num {dvcls}">{g['DV']:+.1f}億</td></tr>"""
    h += "</tbody></table>"
    if len(grpnotes_all) > 5:
        h += ' <button class="expand-btn" data-wrap="grpnotes-card" data-expand="展開全部（共 {} 群）" data-collapse="收回 5 群" onclick="toggleRest(this)">展開全部（共 {} 群）</button>'.format(len(grpnotes_all), len(grpnotes_all))
    h += "</div>"

    # ①②③ 三段：把「locks + flipped + big_movers」轉成三段文字
    segs = _notes_segments(d)
    h += '<div class="card"><h2>盤中觀察（三段）</h2>'
    for i, (t, body) in enumerate(segs, 1):
        h += f'<div class="trend-item" style="margin:10px 0"><b>[{i}] {t}</b><div style="margin-top:4px">{body}</div></div>'
    h += '<div class="meta" style="margin-top:8px">三段依「最有訊息量的變化」自動挑選，數字都是與上一份快照比較的結果。</div>'
    h += "</div>"

    # 鎖死/換手/異常 清單
    h += '<div class="card" id="lock-card"><h2>🚨 關鍵清單 <button class="copybtn" onclick="copyStocks(this)" title="複製本表全部股號與股名">📋</button></h2>'
    for lk in d["locks"]:
        h += f'<div class="trend-item" style="margin:8px 0"><b>{lk["title"]}</b>'
        if lk["items"]:
            shown = [];
            for it in lk["items"][:8]:
                r = it["r"]
                s = f'<span class="pill {chg_class(r["Chg"])}" data-code="{r["Code"]}" data-name="{r["Name"]}">{r["Name"]}</span> {fmt_chg(r["Chg"])} · {fmt(r["Val"])}億' + (f' · 前份 {fmt_chg(it["prev_chg"])}' if "prev_chg" in it else "")
                if "is_new" in it:
                    s += ' <span class="key-yellow">（本輪新進）</span>'
                shown.append(s)
            h += '<div style="margin-top:5px">' + " ".join(shown) + "</div>"
        else:
            h += ' <span class="trend-empty">無</span>'
        h += "</div>"
    h += "</div>"

    # 翻紅翻黑
    h += '<div class="card" id="flip-card"><h2>🔄 轉折（與前一輪比） <button class="copybtn" onclick="copyStocks(this)" title="複製本表全部股號與股名">📋</button></h2>'
    h += '<div class="trend-item"><b>翻黑（前紅今綠）</b>'
    h += (" ".join(f'<span class="pill down" data-code="{x["Code"]}" data-name="{x["Name"]}">{x["Name"]}</span>({fmt_chg(x["Chg"])})' for x in d["flipped_red"][:6])) if d["flipped_red"] else ' <span class="trend-empty">無</span>'
    h += "</div><div class='trend-item'><b>翻紅（前綠今紅）</b>"
    h += (" ".join(f'<span class="pill up" data-code="{x["Code"]}" data-name="{x["Name"]}">{x["Name"]}</span>({fmt_chg(x["Chg"])})' for x in d["flipped_green"][:6])) if d["flipped_green"] else ' <span class="trend-empty">無</span>'
    h += "</div></div>"

    # 大幅位移
    h += '<div class="card" id="mover-card"><h2>📈 大幅位移（|Δ漲幅| ≥ 2.5%） <button class="copybtn" onclick="copyStocks(this)" title="複製本表全部股號與股名">📋</button></h2>'
    if d["big_movers"]:
        h += "<div style='display:flex;flex-wrap:wrap;gap:8px'>"
        for it in d["big_movers"][:10]:
            cls = "up" if it["d"] > 0 else "down"
            h += f'<span class="pill {cls}" data-code="{it["r"]["Code"]}" data-name="{it["r"]["Name"]}">{it["r"]["Name"]}</span> {fmt_chg(it["prev_chg"])}→{fmt_chg(it["r"]["Chg"])} ({it["d"]:+.2f}%)'
        h += "</div>"
    else:
        h += '<span class="trend-empty">無</span>'
    h += "</div>"

    # 固定盯的個股
    h += '<div class="card" id="key-card"><h2>每次固定盯的個股 <button class="copybtn" onclick="copyStocks(this)" title="複製本表全部股號與股名">📋</button></h2>'
    if d["key_codes"]:
        h += "<div style='display:flex;flex-wrap:wrap;gap:8px'>"
        for it in d["key_codes"]:
            r = it["r"]
            h += f'<span class="pill {chg_class(r["Chg"])}" data-code="{r["Code"]}" data-name="{r["Name"]}">{r["Name"]}</span> {fmt_chg(r["Chg"])} · {fmt(r["Val"])}億' + (f' · 前份 {fmt_chg(it["prev_chg"])}' if it["prev_chg"] is not None else "")
        h += "</div>"
    h += "</div>"

    # 未分類
    h += '<div class="card"><h2>待補族群對照</h2>'
    if d["unclassified"]:
        h += ', '.join(f'<span class="unclassified">{x["Code"]} {x["Name"]}</span>' for x in d["unclassified"])
    else:
        h += "無。"
    h += "</div>"

    h += render_foot()
    return h


def _notes_segments(d):
    """把關鍵資料拼成三段自動文字（有訊息量的優先）。"""
    segs = []
    p = d["prev_stat"]
    # 段1：資金主軸與廣度變化
    gmax = d["groups"][0] if d["groups"] else None
    s1 = []
    if gmax:
        s1.append(f"資金主軸落在「{gmax['G']}」（成交值 {gmax['V']}億，佔全體 {gmax['Pct']}%）")
        if gmax["DV"] >= 5:
            s1.append(f"本輪再流入 {gmax['DV']:+.1f}億")
        elif gmax["DV"] <= -5:
            s1.append(f"本輪流出 {gmax['DV']:+.1f}億")
        if gmax["D"] >= gmax["U"] and (gmax["U"] + gmax["D"]) >= 3:
            s1.append(f"但族內 {gmax['U']}↑/{gmax['D']}↓，主軸成員反而走弱")
        elif gmax["U"] > gmax["D"] * 2 and gmax["U"] >= 3:
            s1.append(f"族內 {gmax['U']}↑/{gmax['D']}↓ 同調走強")
    if p:
        s1.append(f"整體漲跌家數 {'增加' if p['d_up'] >= 0 else '減少'} {p['d_up']:+d} 家（現 {d['up_all']}↑/{d['dn_all']}↓）")
    segs.append(("資金主軸", "；".join(s1) if s1 else "資金主軸與上輪相比變動不大。"))

    # 段2：本輪的「新變化」
    s2 = []
    locked = [it for it in d["locks"][0]["items"] if it.get("is_new")][:4]
    for lk in d["locks"]:
        newones = [it for it in lk["items"] if it.get("is_new")]
        if newones:
            s2.append(lk["title"].replace("接近", "") + "新增：" + "、".join(x["r"]["Name"] for x in newones[:4]))
    if not s2:
        big = d["big_movers"][:3]
        if big:
            s2.append("大幅位移：" + "、".join(f'{x["r"]["Name"]}({x["d"]:+.1f}%)' for x in big))
    if not s2:
        fl = d["flipped_red"][:3]
        if fl:
            s2.append("明顯翻黑：" + "、".join(x["Name"] for x in fl))
    if not s2:
        s2.append("本輪沒有新的鎖死/翻轉，盤面變化有限")
    segs.append(("本輪新變化", "；".join(s2)))

    # 段3：異常訊號（換手/假強勢/重挫）
    s3 = []
    hot = d["locks"][4]["items"][:3]
    if hot:
        s3.append("高換手：" + "、".join(f'{x["r"]["Name"]}({fmt(x["r"]["Turn"],1)}%)' for x in hot))
    fake = d["locks"][5]["items"][:3]
    if fake:
        s3.append("假強勢(開高走低)：" + "、".join(f'{x["r"]["Name"]}({fmt_chg(x["r"]["Chg"])})' for x in fake))
    weak = d["locks"][6]["items"][:3]
    if weak:
        s3.append("重挫：" + "、".join(f'{x["r"]["Name"]}({fmt_chg(x["r"]["Chg"])})' for x in weak))
    if not s3:
        s3.append("換手、假強勢、重挫等異常訊號皆未達門檻，盤面相對平靜")
    segs.append(("異常診斷", "；".join(s3)))
    return segs


# ============================================================
#  XQ 盤中儀表板：把三種 kind 濃縮在「一個 HTML」＋歷史時間軸
# ============================================================
KIND_LABEL = {"rank": "資金排行", "breadth": "齊漲分歧", "notes": "盤中三段"}
HIST_DAYS = 5  # 歷史內嵌保留最近 N 個交易日


# ---------- 精簡 fragment（歷史輪次用，避免檔案爆炸） ----------
def frag_rank(d):
    h = [f'<div class="verdict">{one_line_rank(d)}</div>']
    # 族群資金前 10（橫條）
    if d["groups"]:
        h.append('<div class="card"><h2>族群資金（前10）</h2><div style="margin-top:6px">')
        mx = d["groups"][0]["Val"] or 1
        for g in d["groups"][:10]:
            w = min(100, g["Val"] / mx * 100)
            barc = "up" if g["Avg"] >= 0 else "down"
            h.append(f'''<div style="margin-bottom:6px">
  <div style="display:flex;justify-content:space-between"><b>{g['G']}</b>
  <span>{g['Val']}億 · <span class="{chg_class(g['Avg'])}">{fmt_chg(g['Avg'])}</span></span></div>
  <div class="barwrap"><div class="bar {barc}" style="width:{w:.0f}%"></div></div></div>''')
        h.append("</div></div>")
    if d["trend"]:
        h.append('<div class="card"><h2>📈 資金位移（前10）</h2>')
        for it in d["trend"][:10]:
            if it["dv"] > 0:
                h.append(f'<div class="trend-item"><span class="arrow key-red">▲</span><b>{it["label"]}</b> <span class="pill {it["vcls"]}">{it["verdict"]}</span> {it["text"]}</div>')
            else:
                h.append(f'<div class="trend-item"><span class="arrow key-green">▼</span><b>{it["label"]}</b> <span class="pill {it["vcls"]}">{it["verdict"]}</span> {it["text"]}</div>')
        h.append("</div>")
    return "".join(h)


def frag_breadth(d):
    h = [f'<div class="verdict">{one_line_breadth(d)}</div>']
    h.append(f'''<div class="card"><h2>廣度</h2>
  <div class="diag-item"><span class="k">前 {d['top_n']} 名</span><div class="v"><span class="up">{d['up_top']}</span>↑ / <span class="down">{d['dn_top']}</span>↓</div></div>
  <div class="diag-item"><span class="k">全表</span><div class="v"><span class="up">{d['up_all']}</span>↑ / <span class="down">{d['dn_all']}</span>↓</div></div></div>''')
    for title, tag, up in (("🔴 齊漲", "RALLY", True), ("🟢 齊跌", "SELLOFF", False)):
        grps = [g for g in d["rows"] if tag in g["Tags"]]
        grps.sort(key=lambda g: (g["Ratio"], g["Val"]), reverse=True)
        h.append(f'<div class="card"><h2>{title}</h2>')
        if grps:
            for g in grps[:4]:
                cls = "up" if up else "down"
                h.append(f'<div class="trend-item"><b>{g["G"]}</b> <span class="pill {cls}">{g["Up" if up else "Dn"]}/{g["N"]}</span> · {g["Val"]}億 · {fmt_chg(g["Avg"])}</div>')
        else:
            h.append('<div class="trend-empty">無</div>')
        h.append("</div>")
    return "".join(h)


def frag_notes(d):
    h = [f'<div class="verdict">{one_line_notes(d)}</div>']
    h.append('<div class="card"><h2>族群成交值（前8）</h2><table><thead><tr><th>族群</th><th class="num">成交值</th><th class="num">佔比</th><th class="num">漲跌</th><th class="num">avg</th><th class="num">vs前</th></tr></thead><tbody>')
    for g in d["groups"][:8]:
        h.append(f'''<tr><td><b>{g['G']}</b></td><td class="num">{g['V']}</td><td class="num">{g['Pct']}%</td>
<td class="num">{g['U']}<span class="up">↑</span> {g['D']}<span class="down">↓</span></td>
<td class="num {chg_class(g['A'])}">{fmt_chg(g['A'])}</td>
<td class="num {chg_class(g['DV'])}">{g['DV']:+.1f}億</td></tr>''')
    h.append("</tbody></table></div>")
    if d["big_movers"]:
        h.append('<div class="card"><h2>大幅位移</h2>')
        for it in d["big_movers"][:5]:
            cls = "up" if it["d"] > 0 else "down"
            h.append(f'<div class="trend-item"><span class="{cls}">{fmt_chg(it["d"])}</span> {it["r"]["Name"]} · {fmt_chg(it["prev_chg"])} → {fmt_chg(it["r"]["Chg"])} · {it["r"]["Val"]}億</div>')
        h.append("</div>")
    return "".join(h)


def build_fragment(kind, groups, path):
    if kind == "rank":
        return frag_rank(build_rank(groups, path))
    if kind == "breadth":
        return frag_breadth(build_breadth(groups, path))
    if kind == "notes":
        return frag_notes(build_notes(groups, path))
    return ""


def _body_only(full_html):
    """完整 render 文件 → 只留 <body> 內容（dashboard 嵌歷史用，統一用 dashboard 的 CSS）。

    會剝掉最外層 <div class="wrap">…</div>，避免 dashboard 的內容區內再套一層。
    """
    m = re.search(r"<body>(.*)</body>", full_html, re.S)
    if not m:
        return full_html
    inner = m.group(1)
    inner = re.sub(r"\s*<style>.*?</style>\s*", "", inner, flags=re.S)  # 丟掉文件自己的 <style>（CSS 在 dashboard 層有）
    inner = re.sub(r"\s*<script>.*?</script>\s*", "", inner, flags=re.S)  # 丟掉排序等 JS（避免與 dashboard JS 衝突）
    inner = inner.strip()
    if inner.startswith("<div class=\"wrap\">"):
        # 移除最外層 wrap 的開頭與結尾 div
        inner = inner[len('<div class="wrap">'):].strip()
        if inner.endswith("</div>"):
            inner = inner[: -len("</div>")]
    return inner.strip()


def build_dashboard(groups):
    """彙整最近 HIST_DAYS 個交易日的所有快照 → 當日+昨日完整報告，更早日精簡 fragment。

    同一輪的快照（rank/breadth/notes 相差數秒）以「分鐘」為 round key 合併，
    時間軸每 30 分鐘只出現一個點。
    """
    all_snaps = {k: list_snapshots(k) for k in ("rank", "breadth", "notes")}
    all_minutes = sorted(set(s[:13] for m in all_snaps.values() for s in m))
    if not all_minutes:
        return None

    # 每 15 分鐘只保留一個時間點：從最新往回掃，下一個點比上一個保留點早 ≥15 分才保留。
    # 防止多支快照任務同跑造成 5/10 分交錯（例如 09:15 任務與 09:10 任務同存 → 資料 15,10,15,10）。
    def _gap_min(a, b):
        a = datetime.strptime(a, "%Y%m%d_%H%M")
        b = datetime.strptime(b, "%Y%m%d_%H%M")
        return int((a - b).total_seconds() // 60)
    kept = []
    for k in reversed(all_minutes):          # 最新的先
        if not kept or _gap_min(kept[-1], k) >= 15:
            kept.append(k)
    all_minutes = list(reversed(kept))

    # 保留最近 HIST_DAYS 個交易日（round key 前 8 位 = yyyymmdd）
    days = sorted(set(k[:8] for k in all_minutes))
    keep_days = set(days[-HIST_DAYS:])
    full_days = set(days[-2:])   # 當日＋昨日：完整報告
    minutes = [k for k in all_minutes if k[:8] in keep_days]

    def pick(kind, minute):
        """找『該分鐘』內最近的一份 kind 快照 path。"""
        cand = [s for s in all_snaps[kind] if s.startswith(minute)]
        if not cand:
            return None
        return all_snaps[kind][max(cand)]

    # 最新一輪：三種 kind 的「完整」內容
    latest_minute = minutes[-1]
    latest = {}
    for k in ("rank", "breadth", "notes"):
        p = pick(k, latest_minute)
        if not p:
            continue
        if k == "rank":
            latest[k] = render_rank(build_rank(groups, p))
        elif k == "breadth":
            latest[k] = render_breadth(build_breadth(groups, p))
        else:
            latest[k] = render_notes(build_notes(groups, p))

    # 歷史：當日+昨日每一輪（分鐘）三種 kind 都放「完整」，更早日放精簡 fragment
    hist = []
    for minute in minutes:
        entry = {"stamp": minute}
        is_full = minute[:8] in full_days
        for k in ("rank", "breadth", "notes"):
            p = pick(k, minute)
            if not p:
                continue
            if is_full:
                if k == "rank":
                    full_html = render_rank(build_rank(groups, p))
                elif k == "breadth":
                    full_html = render_breadth(build_breadth(groups, p))
                else:
                    full_html = render_notes(build_notes(groups, p))
                entry[k] = _body_only(full_html)
            else:
                entry[k] = build_fragment(k, groups, p)
        hist.append(entry)
    hist.sort(key=lambda x: x["stamp"], reverse=True)  # 新的在前

    return {"latest": latest, "hist": hist,
            "total_rounds": len(hist) if hist else 0}


DASH_HEAD = """<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>XQ 盤中儀表板 — {latest_stamp}</title><style>{css}
.tabpage{{display:none}}
.tabpage.active{{display:block}}
</style></head><body><div class="wrap">
<header><h1>📋 XQ 盤中儀表板</h1><div class="meta">每 15 分自動快照 · 目前顯示 <span id="cur-label">—</span> · 當日+昨日每一輪完整報告，更早輪次精簡版（保留最近 {days} 個交易日）</div></header>
<div class="histbar" id="histbar"></div>
<div class="histnote">時間軸：點一個時間點，那一輪的三份資料（資金排行／齊漲分歧／盤中三段）會一起帶出，用下面的頁籤切換看哪一份；「最新」回到最新一輪。當日與昨日為完整報告，更早交易日只有精簡版（一句話結論＋族群資金前10＋資金位移前10）。「盤後綜合分析」也會一起帶出：顯示該日期產出的報告（當天有兩份會上下排列），該日無報告則顯示前一份；可再用下拉選單瀏覽全部歷史。超過 {days} 個交易日的歷史仍在 snapshots\\ 的 CSV，可重產完整 HTML。</div>
<div class="tabbar" id="tabbar">
  <button class="tabbtn" data-kind="rank" onclick="setKind('rank')">資金排行</button>
  <button class="tabbtn" data-kind="breadth" onclick="setKind('breadth')">齊漲分歧</button>
  <button class="tabbtn" data-kind="notes" onclick="setKind('notes')">盤中三段</button>
  <button class="tabbtn" data-kind="postmarket" onclick="setKind('postmarket')">盤後綜合分析</button>
</div>
<div id="content">
  <div class="tabpage" id="page-rank"></div>
  <div class="tabpage" id="page-breadth"></div>
  <div class="tabpage" id="page-notes"></div>
  <div class="tabpage" id="page-postmarket"></div>
</div>
<div class="footer">本看板每 30 分由快照自動更新。盤中資料到收盤前仍會變動；僅描述資金結構與盤面事實，不含買賣建議或目標價推測。</div>
<script type="application/json" id="histdata">{hist_json}</script>
<script type="application/json" id="pmdata">{pmdata}</script>
<script>{js}</script>
</div></body></html>"""

DASH_JS = """
var HIST = JSON.parse(document.getElementById('histdata').textContent);
var curKind = 'rank';
var KIND_LABEL = {rank:'資金排行', breadth:'齊漲分歧', notes:'盤中三段'};
function label(stamp){ /* yyyymmdd_HHMM -> 09/08 10:55 */ return stamp.slice(4,6)+'/'+stamp.slice(6,8)+' '+stamp.slice(9,11)+':'+stamp.slice(11,13); }
function emptyMsg(k){ return '<div class="card"><div class="trend-empty">這一輪沒有 '+KIND_LABEL[k]+' 快照。</div></div>'; }
var PMDATA = []; try { PMDATA = JSON.parse(document.getElementById('pmdata').textContent || '[]'); } catch(e){}
var PM_CUR_OVERRIDE = ''; // 非空＝用下拉選單手動指定某一份（date|slot），有時間軸互動才清除
function pmShort(d,s){ var dd=d.slice(4,6)+'/'+d.slice(6,8); return (s==='morning'?'盤後分析 開盤前更新版':'盤後分析 前一晚初版')+'（'+dd+'）'; }
function pmPickDate(){ return PMDATA.filter(function(r){return (r.date+'|'+r.slot)===PM_CUR_OVERRIDE;}); }
function renderPostmarket(stamp){
  var el = document.getElementById('page-postmarket');
  var body='';
  if(!PMDATA.length){
    el.innerHTML = '<div class="card"><div class="trend-empty">尚無盤後綜合分析報告。排程會在前一晚 22:00（初版）與開盤前 06:30（更新版）自動產生。</div></div>';
    return;
  }
  var list=[];
  if(PM_CUR_OVERRIDE){
    list = pmPickDate();
  } else {
    var d = stamp ? stamp.slice(0,8) : PMDATA[PMDATA.length-1].date;
    list = PMDATA.filter(function(r){return r.date===d;});
    if(!list.length){ // 該日期沒報告：向前找最近一份（含當天與更早），標示為「最接近」
      var prev = PMDATA.filter(function(r){return r.date < d;}).pop();
      if(prev){ list=[prev]; body += '<div class="card"><div class="trend-empty">該日期沒有盤後分析產出，顯示前一份：'+pmShort(prev.date,prev.slot)+'</div></div>'; }
      else { list=[PMDATA[PMDATA.length-1]]; }
    }
  }
  // 下拉選單：預設「依時間軸」；手動選完顯示該份（直到再點時間軸或點回首項）
  var opts = '<option value=""'+(PM_CUR_OVERRIDE?'':' selected')+'>依時間軸（這一天產出的報告）</option>';
  for (var i=PMDATA.length-1;i>=0;i--){
    var r=PMDATA[i]; var sel=(PM_CUR_OVERRIDE===(r.date+'|'+r.slot))?' selected':'';
    opts += '<option value="'+r.date+'|'+r.slot+'"'+sel+'>'+pmShort(r.date,r.slot)+'</option>';
  }
  body += '<div class="card pc" style="margin-bottom:8px"><select id="pm-sel" style="width:100%;padding:6px;border:1px solid var(--line);border-radius:6px;background:#0f1626;color:var(--txt)" onchange="pmOverride(this.value)">'+opts+'</select></div>';
  body += '<div class="postmarket">' + list.map(function(r){
    var tag = (r.slot==='morning'?'開盤前更新版':'前一晚初版');
    return '<div class="card"><div style="margin-bottom:8px;color:var(--sub);font-size:12px">盤後綜合分析 · '+r.date.slice(4,6)+'/'+r.date.slice(6,8)+' '+tag+' · <code>postmarket_'+r.date+'_'+r.slot+'.md</code></div>' + r.html + '</div>';
  }).join('') + '</div>';
  body += '<div class="card"><div class="trend-empty">數字/漲幅/價位＝淡黃色標示；股名＝藍色；方向<strong>偏多/偏空</strong>用紅/綠標籤。內容由 Gemini 依當日 XQ 快照＋融資券＋三大法人＋千張大戶＋美股＋行事曆＋金融報告生成，僅供解讀盤面與機構可能路徑，不構成買賣建議。</div></div>';
  el.innerHTML = body;
}
function pmOverride(v){ PM_CUR_OVERRIDE = v; render(); if(document.getElementById('pm-sel')){document.getElementById('pm-sel').value=v;} }
function render(){
  var idx = parseInt(document.getElementById('histbar').getAttribute('data-cur') || '0', 10);
  var f = HIST[idx] || {};
  // 把這一輪的三份資料全部一次寫進各自的頁面（之後切頁籤只做顯示/隱藏）
  ['rank','breadth','notes'].forEach(function(k){
    document.getElementById('page-'+k).innerHTML = f[k] ? f[k] : emptyMsg(k);
  });
  renderPostmarket(f.stamp);
  showKind(curKind);
  document.getElementById('cur-label').textContent = idx===0 ? ('最新：' + label(HIST[0].stamp)) : label(HIST[idx].stamp);
  document.querySelectorAll('.dot').forEach(function(b){b.classList.toggle('active', parseInt(b.getAttribute('data-i'),10)===idx);});
}
function showKind(k){
  curKind = k;
  ['rank','breadth','notes','postmarket'].forEach(function(x){
    var p = document.getElementById('page-'+x);
    p.classList.toggle('active', x===k);
  });
  document.querySelectorAll('.tabbtn').forEach(function(b){b.classList.toggle('active', b.getAttribute('data-kind')===k);});
}
function setKind(k){ showKind(k); }
function setRound(i){ document.getElementById('histbar').setAttribute('data-cur', i); render(); }
function toggleRest(btn){
  var wrap=document.getElementById(btn.getAttribute('data-wrap'));
  var open=wrap.classList.toggle('rest-open');
  btn.textContent=open?btn.getAttribute('data-collapse'):btn.getAttribute('data-expand');
}
function sortTable(th){
  var t=th.closest('table');
  var i=+th.getAttribute('data-idx');
  var body=t.tBodies[0], rows=[].slice.call(body.rows);
  var asc=t.getAttribute('data-asc')!=='1';
  rows.sort(function(a,b){
    var av=a.cells[i].getAttribute('data-n'), bv=b.cells[i].getAttribute('data-n');
    if(av!=null&&bv!=null){return asc?(+av)-(+bv):(+bv)-(+av);}
    var x=a.cells[i].textContent,y=b.cells[i].textContent;
    return asc?x.localeCompare(y,'zh-TW',{numeric:true}):y.localeCompare(x,'zh-TW',{numeric:true});
  });
  for(var j=0;j<rows.length;j++)body.appendChild(rows[j]);
  for(var j=0;j<rows.length;j++)rows[j].classList.toggle('rest-row', j>=5);
  var cardId=t.getAttribute('data-card');
  if(cardId){var cb=document.querySelector('.expand-btn[data-wrap="'+cardId+'"]');if(cb){cb.textContent=cb.getAttribute('data-expand');}}
  t.setAttribute('data-asc',asc?'0':'1');
}
function copyStocks(btn){
  var card=btn.closest('.card');
  var seen={}, out=[];
  var els=card.querySelectorAll('[data-code]');
  for(var i=0;i<els.length;i++){
    var c=(els[i].getAttribute('data-code')||'').trim();
    if(c&&!seen[c]){seen[c]=1;out.push(c+'\\t'+els[i].getAttribute('data-name'));}
  }
  var rows=[];
  if(out.length){
    rows=[out.join('\\n')];
  }else{
    var tbl=card.querySelector('table');
    if(tbl){
      for(var r=0;r<tbl.rows.length;r++){
        var cellTxt=[];
        for(var cc=0;cc<tbl.rows[r].cells.length;cc++){
          cellTxt.push(tbl.rows[r].cells[cc].innerText.replace(/\\s+/g,' ').trim());
        }
        rows.push(cellTxt.join('\\t'));
      }
    }
  }
  if(!rows.length){return;}
  var text=rows.join('\\n');
  function done(){btn.classList.add('copied');btn.textContent='已複製 '+rows.length+' 項';setTimeout(function(){btn.classList.remove('copied');btn.textContent='📋';},1600);}
  function fb(){var ta=document.createElement('textarea');ta.value=text;document.body.appendChild(ta);ta.select();document.execCommand('copy');document.body.removeChild(ta);done();}
  if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(text).then(done,fb);}else{fb();}
}
window.onload = function(){
  var hb = document.getElementById('histbar');
  // 依 stamp (yyyyMMdd_HHMM) 判斷當日/次日：最新日期=當日(紅框)，下一個不同日期=次日(淡青)
  var todayD = HIST.length ? HIST[0].stamp.slice(0,8) : '';
  var yestD = '';
  for (var t=1; t<HIST.length; t++){
    if (HIST[t].stamp.slice(0,8) !== todayD){ yestD = HIST[t].stamp.slice(0,8); break; }
  }
  function dayCls(stamp){
    var d = stamp.slice(0,8);
    if (d === todayD) return ' today';
    if (d === yestD) return ' yest';
    return '';
  }
  hb.innerHTML = '<button class="dot active' + (HIST.length ? dayCls(HIST[0].stamp) : '') + '" data-i="0" onclick="setRound(0)">最新</button>';
  for (var i=1; i<HIST.length; i++){
    var b=document.createElement('button');
    b.className='dot' + dayCls(HIST[i].stamp); b.setAttribute('data-i',i); b.textContent=label(HIST[i].stamp);
    b.onclick=(function(ii){return function(){setRound(ii);};})(i);
    hb.appendChild(b);
  }
  render();
};
"""


def render_dashboard(d):
    if not d:
        return ""
    latest_stamp = ""
    if d["hist"]:
        k = d["hist"][0]["stamp"]  # yyyyMMdd_HHMM（13 位）
        latest_stamp = datetime.strptime(k, "%Y%m%d_%H%M").strftime("%Y-%m-%d %H:%M")
    return DASH_HEAD.format(
        latest_stamp=latest_stamp, days=HIST_DAYS,
        # 轉義 </script>：完整 HTML fragment 內含自己的 <script>，若不轉義，內嵌 JSON 會被瀏覽器截斷（JSON 內 "</" 轉 "<\\/" 是合法且安全）
        hist_json=json.dumps(d["hist"], ensure_ascii=False).replace("</", "<\\/"),
        css=CSS, js=DASH_JS,
        pmdata=json.dumps(pm_records(), ensure_ascii=False).replace("</", "<\\/"),
    )


# ============================================================
#  盤後綜合分析（第四頁籤）：routines\outputs\postmarket\*.md
# ============================================================

# 多方/空方關鍵字（跟前面三頁籤一致的紅多綠空配色）
_PM_BULLISH = ["偏多", "買超", "流入", "增持", "作帳", "強勢", "漲停", "齊漲",
               "轉強", "走強", "點火", "拉抬", "回補", "低接", "看好", "利多",
               "淨買", "連買", "加碼", "守穩", "強彈", "防禦"]
_PM_BEARISH = ["偏空", "賣超", "流出", "調節", "出貨", "轉弱", "走弱", "重挫",
               "大跌", "跌破", "齊跌", "退潮", "下修", "保守", "利空", "淨賣",
               "連賣", "減碼", "賣壓", "承壓", "觀望", "恐慌"]

_PM_STOCK_RE = re.compile(r"^\s*(?:[-*]|\d+[.、])?\s*(\d{4,5})\s+([^\s｜|，,。]+)")
_PM_DIR_RE = re.compile(r"方向[：:]\s*([^｜|，,。]*)")
_PM_STR_RE = re.compile(r"強度[：:]\s*([強中弱])")

_PM_KW_COLOR = {}
_PM_CUR_STOCKS = {}          # name -> code（本次報告預測榜的股票；內文股名標示用）
_PM_CUR_DIR = {}             # name -> key-red/key-green/""（內文股名依方向紅綠）
_PM_SUB_JUDGE = {"我的判斷", "我的判斷與理由"}
_PM_PRICE = {}               # code -> close（最新 breadth 快照現價，供價位驗證）


def _pm_price_map():
    """最新 breadth 快照的現價 {code: close}；沒有快照時回空 dict。"""
    if _PM_PRICE:
        return _PM_PRICE
    try:
        snaps = list_snapshots("breadth")
        if not snaps:
            return {}
        _, path = snaps.popitem()
        for r in load_csv(path):
            c = r.get("Code")
            if c:
                _PM_PRICE[c] = float(r.get("Close", 0) or 0)
    except Exception:
        pass
    return _PM_PRICE


def _pm_check_price(code, text):
    """驗證關鍵價位合理性：用現價檢查「支撐 X / 壓力 Y」。

    現價有、且支撐或壓力與現價相差 ≥50%（或方向反了）→ 回傳警示 HTML，
    否則回空字串。
    """
    if not code or not text:
        return ""
    px = _pm_price_map().get(code)
    if not px:
        return ""
    m = re.findall(r"支撐\s*([\d,]+\.?\d*)\s*元?\s*/\s*壓力\s*([\d,]+\.?\d*)", text)
    if not m:
        return ""
    try:
        sup, res = float(m[0][0].replace(",", "")), float(m[0][1].replace(",", ""))
    except ValueError:
        return ""
    bad = []
    if sup >= px * 1.5:
        bad.append(f"支撐{sup:g} 高於現價{px:g}太多")
    if res <= px * 0.5:
        bad.append(f"壓力{res:g} 低於現價{px:g}太多")
    if sup >= px or res <= px:
        bad.append("支撐/壓力方向反了" if sup >= px and res <= px else "")
    bad = [b for b in bad if b]
    if not bad:
        return ""
    return (f'<span class="pm-pxwarn">⚠ 價位可疑（現價 {px:g}）：' + "；".join(bad) + "</span>")


def _pm_dir_label(d):
    """把「方向」欄的字串（可能像「中含偏多」）簡化成 偏多/偏空/中性 + 配色。

    Gemini 偶爾漏寫「方向：」欄（只寫強度）→ 空字串也補顯示「中性」，避免卡片缺 pill。
    """
    if not d or not d.strip():
        return "中性", "flat", ""
    if "偏多" in d:
        return "偏多", "up", "key-red"
    if "偏空" in d:
        return "偏空", "down", "key-green"
    if "中性" in d:
        return "中性", "flat", ""
    return d.strip(), "flat", ""


def _pm_build_kw():
    if _PM_KW_COLOR:
        return
    for w in _PM_BULLISH:
        _PM_KW_COLOR[w] = "key-red"
    for w in _PM_BEARISH:
        _PM_KW_COLOR[w] = "key-green"


def _pm_esc(t):
    return html.escape(t, quote=False)


def _pm_highlight(text):
    """把多方/空方關鍵字染成 key-red/key-green（白字改彩色），一次取代避免巢狀。"""
    if not text:
        return text
    _pm_build_kw()
    pat = "|".join(sorted(_PM_KW_COLOR.keys(), key=len, reverse=True))
    return re.sub(pat, lambda m: f'<span class="{_PM_KW_COLOR[m.group(0)]}">{m.group(0)}</span>', text)


_PM_NUM_RE = re.compile(r"[+\-]?\d[\d,]*(?:\.\d+)?\s*(?:%|％|億|萬|TWD|元)")

def _pm_hl_numbers(text):
    """把「量化重點」標色：純數據（金額/漲幅%/價位 TWD）→ 橘黃；帶 +/- 的漲跌幅 → 紅/綠。"""
    if not text:
        return text
    pat = re.compile(
        r"(?P<delta>[+\-]\d[\d,]*(?:\.\d+)?\s*(?:%|％|點))"
        r"|(?P<num>[+\-]?\d[\d,]*(?:\.\d+)?\s*(?:%|％|億|萬|TWD|元))")
    def repl(m):
        d = m.group("delta")
        if d is not None:
            cls = "up" if d.strip().startswith("+") else "down"
            return f'<span class="{cls}">{d}</span>'
        return f'<span class="pm-num">{m.group("num")}</span>'
    return pat.sub(repl, text)


def _pm_hl_line(line):
    """行內容重點上色（先 escape → 粗體/斜體 → 標數字重點 → 內文股名標示）。
    不做大範圍關鍵字紅綠上色（避免畫面一片紅綠），只標量化重點與股名。
    """
    s = _pm_esc(line)
    s = re.sub(r"^\*\*(.+?)\*\*\s*[：:]\s*", lambda m: _pm_sub_span(m.group(1)), s)
    s = re.sub(r"^\*(.+?)\*\s*[：:]\s*", lambda m: _pm_sub_span(m.group(1)), s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)              # **粗體**
    s = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", s)  # *斜體*
    s = _pm_hl_numbers(s)
    return _pm_hl_stocks(s)


def _pm_sub_span(label):
    """次標籤：價值點的「我的判斷」用薑黃（pm-judge）凸顯，其餘維持淡藍（pm-sub）。"""
    cls = "pm-sub pm-judge" if label in _PM_SUB_JUDGE else "pm-sub"
    return f'<span class="{cls}">{label}</span>：'


def _pm_hl_stocks(text):
    """把已轉好 HTML 的文字中出現的股名標成金色（.pm-stk），不影響既有 <b>/<span>。

    只針對「預測榜收集到的股票名」：
      - 一般股名：前後不緊鄰拉丁字母或數字即可（中文前後相鄰正常，例如「台積電與欣興」）。
      - 若某股名是「另一個更長股名的前綴」（如 台塑 vs 台塑化），該股名改用嚴格邊界
        （兩側都不能是中文），避免把「台塑化」切出一個錯誤的「台塑」。
    注意：不能對 <b data-code> 內的股名再加一層（copyStocks 依賴 data-code 唯一性）。
    """
    if not text or not _PM_CUR_STOCKS:
        return text
    names = sorted(_PM_CUR_STOCKS, key=len, reverse=True)
    prefixes = {a for a in names if any(b != a and b.startswith(a) for b in names)}
    for name in names:
        esc = html.escape(name)
        if name in prefixes:
            pat = re.compile(r"(?<![\u4e00-\u9fffA-Za-z0-9])" + re.escape(esc) + r"(?![\u4e00-\u9fffA-Za-z0-9])")
        else:
            pat = re.compile(r"(?<![A-Za-z0-9])" + re.escape(esc) + r"(?![A-Za-z0-9])")
        text2 = pat.sub(lambda m, name=name, esc=esc: f'<span class="{_pm_stk_cls(name)}" data-code="{_PM_CUR_STOCKS[name]}" data-name="{esc}">{esc}</span>', text)
        if text2 != text:
            text = text2
    return text


def _pm_stk_cls(name):
    """內文股名 class：預測榜有方向的股票依方向紅/綠，其餘維持藍底（無方向）。"""
    d = _PM_CUR_DIR.get(name, "")
    if d == "key-red":
        return "pm-stk up"
    if d == "key-green":
        return "pm-stk down"
    return "pm-stk"


def _pm_forecast_section(body, note=""):
    """「明日個股預測榜」：每檔做成卡片＋股名依方向上色，卡上附一鍵複製。

    Gemini 輸出格式不穩（行首常見整行 **粗體**、方向可能是「中含偏多」這類複合詞），
    解析時先剝掉粗體標記再抓 代碼＋股名，方向/強度用獨立的搜尋 regex 容錯。
    note：標題尾註（如「含 5 檔中小型股」），當作小字附註顯示在標題旁。
    """
    note_html = f'<span class="pm-note">{_pm_esc(note)}</span>' if note else ""
    parts = ['<div class="card" id="pm-forecast"><div style="display:flex;align-items:center;justify-content:space-between">'
             '<h2 style="margin:0">明日個股預測榜{note}</h2>'
             '<button class="copybtn" onclick="copyStocks(this)" title="複製全部股號+股名到 Excel（兩欄）">📋 一鍵複製</button></div>'.format(note=note_html)]
    cur = None
    idx = 0
    for ln in body:
        s = ln.strip()
        if not s or s == "---":
            continue
        flat = s.replace("**", "").strip()          # 剝掉粗體，像是 1. **2330 台積電｜方向：…**
        m = _PM_STOCK_RE.match(flat)
        if m and m.group(2):
            if cur is not None:
                parts.append(cur + "</div>")
            idx += 1
            code, name = m.group(1), m.group(2)
            dm = _PM_DIR_RE.search(flat)
            sm = _PM_STR_RE.search(flat)
            dlabel, cls, ncls = _pm_dir_label(dm.group(1).strip() if dm else "")
            strat = sm.group(1) if sm else ""
            pill = f'<span class="pill {cls}">{dlabel}</span>' if cls else ""
            strat_html = f'<span class="pm-str">強度：{_pm_esc(strat)}</span>' if strat else ""
            if ncls:
                name_html = f'<b class="{ncls}" data-code="{code}" data-name="{name}">{code} {name}</b>'
            else:
                name_html = f'<b data-code="{code}" data-name="{name}">{code} {name}</b>'
            cur = (f'<div class="pm-stock {cls}">'
                   f'<div class="pm-name"><span class="pm-idx">{idx}</span>{name_html}{pill}{strat_html}</div>')
        elif (s.startswith("-") or s.startswith("·")) and cur is not None:
            raw = s.lstrip("-· ").strip()
            mm = re.match(r"^([^：]+)：\s*(.*)$", raw, re.S)
            if mm:
                lab = mm.group(1).strip().replace("**", "")
                rest = _pm_hl_line(mm.group(2).strip())
                if cur is not None and "關鍵價位" in lab:
                    rest += _pm_check_price(code, mm.group(2).strip())
                cur += f'<div class="pm-detail"><span class="pm-k">{_pm_esc(lab)}</span>：{rest}</div>'
            else:
                cur += f'<div class="pm-detail">{_pm_hl_line(raw)}</div>'
        else:
            parts.append(f'<p>{_pm_hl_line(s)}</p>')
    if cur is not None:
        parts.append(cur + "</div>")
    parts.append("</div>")
    return "".join(parts)


def _pm_generic_section(title, body):
    """非預測榜章節：簡潔排版，bullets/編號轉 ul，關鍵字照樣上色。"""
    parts = [f'<div class="card"><h2>{_pm_esc(title)}</h2>']
    ul_open = False
    para = []

    def flush_ul():
        nonlocal ul_open
        if ul_open:
            parts.append("</ul>")
            ul_open = False

    def flush_para():
        if para:
            parts.append("<p>" + _pm_hl_line(" ".join(para)) + "</p>")
            del para[:]

    for ln in body:
        s = ln.strip()
        if not s or s == "---":
            flush_ul()
            flush_para()
            continue
        if s.startswith("- "):
            flush_para()
            if not ul_open:
                parts.append("<ul>")
                ul_open = True
            parts.append("<li>" + _pm_hl_line(s[2:]) + "</li>")
        elif re.match(r"^\d+[.、]\s*", s):
            flush_para()
            mm2 = re.match(r"^(\d+[.、])\s*(.*)$", s, re.S)
            num = mm2.group(1) if mm2 else ""
            rest = mm2.group(2) if mm2 else s
            if not ul_open:
                parts.append("<ul>")
                ul_open = True
            m3 = re.match(r"^\*\*(.+?)\*\*\s*$", rest, re.S)
            if m3:
                parts.append("<li><b>" + _pm_esc(num) + "</b> <span class='pm-mg'>" +
                             _pm_esc(m3.group(1)) + "</span></li>")
            else:
                parts.append("<li><b>" + _pm_esc(num) + "</b> " + _pm_hl_line(rest) + "</li>")
        else:
            flush_ul()
            if s.startswith("> "):
                parts.append("<p class='pm-quote'>" + _pm_hl_line(s[2:]) + "</p>")
            else:
                para.append(s)
    flush_ul()
    flush_para()
    parts.append("</div>")
    return "".join(parts)


def _pm_render_md(text):
    """把 postmarket md 轉成跟儀表板配色一致（紅多綠空）的 HTML。"""
    lines = [ln.rstrip() for ln in text.splitlines()]
    sections = []
    cur_title = None
    cur_body = []
    for ln in lines:
        st = ln.strip()
        if st.startswith("## "):
            if cur_title is not None:
                sections.append((cur_title, cur_body))
            cur_title = st[3:].strip()
            cur_body = []
        elif cur_title is not None:
            cur_body.append(ln)
    if cur_title is not None:
        sections.append((cur_title, cur_body))

    # 先掃預測榜收集股名與方向（供內文其他段落把股名標成對應顏色/可複製）
    _PM_CUR_STOCKS.clear()
    _PM_CUR_DIR.clear()
    for title, body in sections:
        if not title.startswith("明日個股預測榜"):
            continue
        for ln in body:
            flat = ln.strip().replace("**", "")
            mm = _PM_STOCK_RE.match(flat)
            if mm and mm.group(2) and not re.match(r"\d", mm.group(2)):
                name = mm.group(2)
                _PM_CUR_STOCKS[name] = mm.group(1)
                dm = _PM_DIR_RE.search(flat)
                dlabel, cls, ncls = _pm_dir_label(dm.group(1).strip() if dm else "")
                _PM_CUR_DIR[name] = ncls

    out = []
    for title, body in sections:
        if title.startswith("明日個股預測榜"):
            note = title[len("明日個股預測榜"):].strip().strip("（）()")
            out.append(_pm_forecast_section(body, note))
        else:
            out.append(_pm_generic_section(title, body))
    return "".join(out)


def pm_records():
    """把 routines/outputs/postmarket/*.md 全部轉成 [{date, slot, html}]，塞進 pmdata JSON。

    date = yyyyMMdd，slot = morning/evening。輸出依日期舊→新排序（JS 端自行挑當天）。
    """
    if not os.path.isdir(POSTMARKET_OUT):
        return []
    files = [f for f in os.listdir(POSTMARKET_OUT) if f.startswith("postmarket_") and f.endswith(".md")]
    if not files:
        return []
    recs = []
    for fn in files:
        m = re.match(r"postmarket_(\d{8})_(morning|evening)\.md", fn)
        if not m:
            continue
        date, slot = m.group(1), m.group(2)
        path = os.path.join(POSTMARKET_OUT, fn)
        try:
            with io.open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except IOError:
            continue
        recs.append({"date": date, "slot": slot, "html": _pm_render_md(text)})
    recs.sort(key=lambda r: (r["date"], 0 if r["slot"] == "morning" else 1))
    return recs


# ============================================================
#  主程式
# ============================================================
def main():
    ap = argparse.ArgumentParser(description="XQ 盤中 HTML 看板產生器")
    ap.add_argument("--kind", choices=["rank", "breadth", "notes"], help="只產生某一種")
    ap.add_argument("--all", action="store_true", help="一次產生三種單檔 + dashboard")
    ap.add_argument("--dashboard", action="store_true", help="只產生 xq_dashboard.html（預設行為）")
    ap.add_argument("--csv", help="指定某份快照檔（預設抓最新）")
    ap.add_argument("--out", help="輸出 HTML 路徑（預設 routines\\outputs\\(kind)_(stamp).html）")
    args = ap.parse_args()

    groups = build_group_map()
    print(f"分類表載入：{len(groups)} 檔", file=sys.stderr)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # dashboard 永遠產出（預設 / --dashboard / --all 都含）
    if args.dashboard or not args.kind or args.all:
        dd = build_dashboard(groups)
        if dd:
            html = render_dashboard(dd)
            dpath = os.path.join(OUTPUT_DIR, "xq_dashboard.html")
            with io.open(dpath, "w", encoding="utf-8") as f:
                f.write(html)
            print(f"[dashboard] 已產生 -> {dpath}（{dd['total_rounds']} 輪歷史）")
        else:
            print("[dashboard] snapshots\\ 沒有任何快照，先跳過", file=sys.stderr)
        if args.dashboard or not args.kind:
            return

    kinds = ["rank", "breadth", "notes"] if args.all else ([args.kind] if args.kind else [])
    for kind in kinds:
        snaps = list_snapshots(kind)
        if not snaps:
            print(f"[{kind}] snapshots\\ 沒有 {kind}_*.csv，跳過", file=sys.stderr)
            continue
        latest_stamp, latest_path = snaps.popitem()
        path = args.csv or latest_path
        stamp = guess_stamp(path)
        if kind == "rank":
            data = build_rank(groups, path)
            html = render_rank(data)
        elif kind == "breadth":
            data = build_breadth(groups, path)
            html = render_breadth(data)
        elif kind == "notes":
            data = build_notes(groups, path)
            html = render_notes(data)
        else:
            print(f"[{kind}] HTML 尚未實作此 kind，先跳過", file=sys.stderr)
            continue
        out = args.out or os.path.join(OUTPUT_DIR, f"{kind}_{stamp}.html")
        with io.open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"[{kind}] 已產生 -> {out}")
        if kind == "rank":
            print(f"       一句話結論：{one_line_rank(data)}")
        elif kind == "breadth":
            print(f"       一句話結論：{one_line_breadth(data)}")
        elif kind == "notes":
            print(f"       一句話結論：{one_line_notes(data)}")


if __name__ == "__main__":
    main()
