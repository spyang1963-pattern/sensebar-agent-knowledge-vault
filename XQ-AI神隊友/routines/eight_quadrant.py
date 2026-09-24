# -*- coding: utf-8 -*-
"""
eight_quadrant.py — 量價結構八象限判讀（v2：L0~L3），餵給 postmarket_report 的 input。

資料源：XQ dashboard 的 <script id="monitordata">（當日預測榜 20 檔 15分K series）。
產出：每檔供需象限＋極限大量確認＋8MA 短線結構＋5MV/13MV 量軸＋Gemini 方向互證。

用法：
  python eight_quadrant.py                # stdout 印 md 判讀表
  python eight_quadrant.py --out out.md   # 存檔
  python eight_quadrant.py --json         # 印原始計算結果（除錯）
被 postmarket_prep.py 呼叫：build_md()
"""
import sys
import io
import re
import json
import urllib.request

FEED_URL = "https://spyang1963-pattern.github.io/xq-dashboard/"

def fetch_feed():
    """抓 dashboard monitordata JSON；失敗回 None（呼叫端要能容錯）。"""
    try:
        html = urllib.request.urlopen(FEED_URL, timeout=40).read().decode("utf-8", "replace")
        m = re.search(r'id="monitordata">(\{.*?\})</script>', html, re.S)
        if not m:
            return None
        return json.loads(m.group(1))
    except Exception:
        return None

def _deltas(ser):
    vals = [p["val"] for p in ser]
    dv = [vals[0]] + [vals[i] - vals[i - 1] for i in range(1, len(vals))]
    return dv

def _segs(ser):
    """把 series 切成漲段/跌段（用 d=up/down），flat/None 併入上一段。"""
    up, dn, cur, curdir = [], [], [], None
    for pt in ser:
        d = pt.get("d")
        if d in ("up", "down"):
            if curdir is None or d == curdir:
                cur.append(pt)
                curdir = d
            else:
                (up if curdir == "up" else dn).append(cur)
                cur, curdir = [pt], d
        elif curdir:
            cur.append(pt)
    if cur and curdir:
        (up if curdir == "up" else dn).append(cur)
    return up, dn

def _seg_avg(seg):
    if len(seg) < 2:
        return None
    return (seg[-1]["close"] - seg[0]["close"]) / (len(seg) - 1)

def quadrant(item):
    """單檔判讀。回傳 dict；series 不足回 None。"""
    ser = item.get("series") or []
    if len(ser) < 3:
        return None
    up, dn = _segs(ser)
    up_avgs = [a for s in up if (a := _seg_avg(s)) is not None]
    dn_avgs = [abs(a) for s in dn if (a := _seg_avg(s)) is not None]
    A = B = None
    if up_avgs and dn_avgs and dn_avgs[-1] > 0:
        A = up_avgs[-1] / dn_avgs[-1]
    if len(up_avgs) >= 2 and up_avgs[-2]:
        B = up_avgs[-1] / up_avgs[-2]

    dv = _deltas(ser)
    last, prev = ser[-1], ser[-2]
    price_up = last["close"] > prev["close"]
    VR = dv[-1] / dv[-2] if dv[-2] else None
    win13 = dv[-13:] if len(dv) >= 13 else dv
    VX = dv[-1] / max(win13) if max(win13) else None
    vol = "增" if VR and VR >= 1.2 else ("縮" if VR and VR <= 0.8 else "平")

    boom_idx = dv.index(max(dv))
    maxc_before = max(p["close"] for p in ser[:boom_idx + 1])
    post_high = max(p["close"] for p in ser[boom_idx + 1:]) if boom_idx + 1 < len(ser) else maxc_before
    new_high = post_high > maxc_before
    review = "大量後未過高→調節" if max(dv) and (max(dv) / (sum(dv) / len(dv))) >= 1.5 and not new_high else ""

    if price_up:
        steep = "陡" if (A is None or A >= 1.2) else "缓"
    else:
        steep = "陡" if (A is not None and A < 0.8) else "缓"
    if vol == "增":
        if price_up:
            Q = "Q1量增价涨·陡" if steep == "陡" else "Q2量增价涨·缓(边際K)"
            bias = "多" if Q.startswith("Q1") else "疑"
        else:
            Q = "Q3量增价跌·陡" if steep == "陡" else "Q4量增价跌·缓"
            bias = "偏空"
    else:
        if price_up:
            Q = "Q5量缩价涨·陡(飘)" if steep == "陡" else "Q6量缩价涨·缓(惜售)"
            bias = "疑" if Q.startswith("Q5") else "多"
        else:
            Q = "Q7量缩价跌·陡" if steep == "陡" else "Q8量缩价跌·缓(多方整理)"
            bias = "疑" if Q.startswith("Q7") else "多"
    mb = ""
    if Q.startswith("Q2"):
        mb = "边際K续强" if (VR and VR > 1) else "边際K转弱警報"
    flag = ""
    if Q.startswith("Q5"):
        flag = "缩量价涨·飘(背離)"
    if Q.startswith("Q7"):
        flag = "无量急跌·待量确认"
    if Q.startswith("Q8"):
        flag = "缩量缓跌·多方整理"

    ma8_cur = sum(p["close"] for p in ser[-8:]) / 8
    ma8_prev = sum(p["close"] for p in ser[-9:-1]) / 8 if len(ser) >= 9 else ma8_cur
    above8 = last["close"] >= ma8_cur
    slope8 = "↑" if ma8_cur > ma8_prev else ("↓" if ma8_cur < ma8_prev else "→")

    mv5_prev = sum(dv[-6:-1]) / 5 if len(dv) >= 6 else None   # 前一根的 5MV
    attack = (mv5_prev is not None) and (dv[-1] > mv5_prev)
    mv5_cur = sum(dv[-5:]) / 5 if len(dv) >= 5 else None
    mv5_s = None if mv5_cur is None or mv5_prev is None else ("↑" if mv5_cur > mv5_prev else ("↓" if mv5_cur < mv5_prev else "→"))
    mv13_s = None
    if len(dv) >= 14:
        a13 = sum(dv[-13:]) / 13
        b13 = sum(dv[-14:-1]) / 13
        mv13_s = "↑" if a13 > b13 else ("↓" if a13 < b13 else "→")
    mv55 = None  # 需跨日 15K（≒3 個交易日），當日 feed 不足 → 標 NA

    # 扣抵（MA8 向前看）：扣抵價 = 8 根前收盤；現價 > 扣抵價 → MA 準備上揚（助漲）
    deduct = "NA"
    if len(ser) >= 8:
        ded_price = ser[-8]["close"]
        if last["close"] > ded_price:
            deduct = "助漲"
        elif last["close"] < ded_price:
            deduct = "助跌"
        else:
            deduct = "平"

    # 力道衰竭：同位對照 B < 1 → 本波力道 < 前波（攻擊動能衰）
    b_decline = (B is not None and B < 1)

    return dict(code=item.get("code", ""), name=item.get("name", ""), close=last["close"],
                dirx=item.get("dir", ""), climax=bool(item.get("climax")), sweep=bool(item.get("sweep")),
                Q=Q, bias=bias, A=A, B=B, VR=VR, VX=VX, vol=vol, mb=mb, flag=flag or review,
                above8=above8, slope8=slope8, attack=attack, mv5_s=mv5_s, mv13_s=mv13_s, mv55=mv55,
                price_up=price_up, deduct=deduct, b_decline=b_decline)


_DEFAULT_WEIGHTS = {"Q": 2, "MA": 2, "deduct": 2, "B": 2, "attack": 1}

# 量價象限 → 下一方向（Q 是「量×價×陡緩」，直接映射即時方向；bias 是結構立場，不適用）
# 依分層稽核實證（15分 樣本）改為「當沖均值回歸」：量增＝竭盡→反轉、量縮價漲陡=背離→跌、量縮價跌陡=賣壓竭盡→漲
_Q_DIR = {"Q1": -0.3, "Q2": -0.5, "Q3": -1.0, "Q4": 0.3, "Q5": -0.5, "Q6": 0.5, "Q7": 0.3, "Q8": 0.0}


def next_direction(q, climax="", sweep=""):
    """下一方向引擎（加權投票＋反轉覆寫）。

    吃 quadrant() 結果（可為 None＝點數不足）＋反轉方向 climax/sweep（'bull'/'bear'，
    由監控層用 sup/res 判斷）。回 (方向, 信心 0~1)。
    方向 ∈ {續漲, 續跌, 觀望, 轉漲, 轉跌}。
    """
    if climax == "bull" or sweep == "bull":
        return "轉漲", 1.0
    if climax == "bear" or sweep == "bear":
        return "轉跌", 1.0
    if not q:
        return "觀望", 0.0

    w = _DEFAULT_WEIGHTS
    bull = bear = 0.0

    # 1) 量價象限（直接方向映射）
    qd = _Q_DIR.get(q.get("Q", ""), 0.0)
    if qd > 0:
        bull += w["Q"] * qd
    elif qd < 0:
        bear += w["Q"] * abs(qd)

    # 2) MA 站破＋斜率
    above = q.get("above8")
    slope = q.get("slope8")
    if slope in ("↑", "↓") and above is not None:
        if above and slope == "↑":
            bull += w["MA"]
        elif not above and slope == "↓":
            bear += w["MA"]
        elif above and slope == "↓":
            bear += w["MA"] * 0.5
        elif not above and slope == "↑":
            bull += w["MA"] * 0.5

    # 3) 扣抵（向前看：助漲/助跌）
    d = q.get("deduct", "")
    if d == "助漲":
        bull += w["deduct"]
    elif d == "助跌":
        bear += w["deduct"]

    # 4) 力道衰竭 B<1（多頭動能衰 → 偏空；僅價漲時有意義）
    if q.get("b_decline") and q.get("price_up"):
        bear += w["B"]

    # 5) 5MV 攻擊
    if q.get("attack"):
        if q.get("price_up"):
            bull += w["attack"]
        else:
            bear += w["attack"]

    if bull + bear == 0:
        return "觀望", 0.0
    ratio = bull / (bull + bear)
    conf = round(abs(ratio - 0.5) * 2, 2)
    if ratio >= 0.6:
        return "續漲", conf
    if ratio <= 0.4:
        return "續跌", conf
    return "觀望", conf


def _dir_bias(q):
    """互證：Gemini 方向 vs 結構象限。回傳 (判, 文字符號)。"""
    d = 1 if "多" in q["dirx"] else (-1 if "空" in q["dirx"] else 0)
    b = 1 if q["bias"] == "多" else (-1 if q["bias"] == "偏空" else 0)
    if not d or not b:
        return "◦", "中性/未定"
    if d == b:
        return "✓", "一致"
    return "✗", "相左"


def _alert(q):
    a = []
    if q["dirx"] and "多" in q["dirx"] and q["bias"] == "偏空" and q["VX"] is not None and q["VX"] >= 0.9:
        a.append("⚠偏多vs空方大量")
    if "多" in q["dirx"] and not q["above8"]:
        a.append("偏多破8MA")
    if "空" in q["dirx"] and q["bias"] == "多":
        a.append("偏空vs多頭增量")
    if q["flag"]:
        a.append(q["flag"])
    if q["sweep"]:
        a.append("Sweep标签")
    if q["climax"]:
        a.append("climax标签")
    if q["mb"].startswith("边際"):
        a.append(q["mb"])
    return "；".join(a)


def build_md(feed=None):
    """組 markdown 判讀表；feed 抓取失敗回 None（呼叫端 fallback）。"""
    if feed is None:
        feed = fetch_feed()
    if not feed or not feed.get("items"):
        return None
    items = feed["items"]
    rows = []
    n_short = 0
    for it in items:
        ser = it.get("series") or []
        q = quadrant(it)
        if q is None:
            n_short += 1
            rows.append((it.get("name", "?"), f"（series 過短（{len(ser)} 點），無法判讀）", None, "", "-", "", ""))
            continue
        m, tag = _dir_bias(q)
        f = lambda v: f"{v:.2f}" if isinstance(v, float) else ("-" if v is None else v)
        a = _alert(q)
        rows.append((q["name"], q["Q"], q, m, f, tag, a))

    L = []
    L.append("### 量價結構判讀（v2 L0~L3）")
    L.append(f"- 資料：dashboard feed stamp `{feed.get('stamp', '?')}`，成交值累計換算當根量；A=異位(涨段/跌段力道)、B=同位(本波/前波涨)、VR、VX=極限大量。")
    pts_all = [len(it.get("series") or []) for it in items]
    if pts_all:
        L.append(f"- 點數統計：{len(items)} 檔，每檔當日 15分K 點數 min={min(pts_all)} / max={max(pts_all)}（八象限需 ≥3 點才有值）。")
    if n_short:
        L.append(f"- ⚠️ 有 {n_short} 檔點數不足（<3）無法判讀象限：出榜時請改以「0b 技術位階」補強，並註記「（1b 資料不足）」。")
    L.append("- **L0 趨勢層**：55MA／34MV 需跨日 15K（≒3 交易日）當日 feed 不足，暫列 NA；環境請對照「0b 技術位階」（MA20 乖離＋前20日高低）。")
    L.append("| 名稱 | 預測 | 象限 | A | B | VR | VX | 8MA(15K) | 5MV | 13MV | 互證 | 警示 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for name, Q, q, m, f, tag, a in rows:
        if q is None:
            L.append(f"| {name} | {''} | {Q} | - | - | - | - | - | - | - | - | - |")
            continue
        L.append(f"| {name} | {q['dirx'] or '中性'} | {q['Q']} | {f(q['A'])} | {f(q['B'])} | {f(q['VR'])} | {f(q['VX'])} | "
                 f"{'站' if q['above8'] else '破'}MA8{q['slope8']} | {'攻' if q['attack'] else '-'}{q['mv5_s'] or ''} | {q['mv13_s'] or 'NA'} | "
                 f"{m}({tag}) | {a or '-'} |")
    return "\n".join(L)


def main():
    ap = None
    try:
        from argparse import ArgumentParser
        ap = ArgumentParser()
        ap.add_argument("--out", default=None)
        ap.add_argument("--json", action="store_true")
        args = ap.parse_args()
    except Exception:
        args = type("A", (), {"out": None, "json": False})()

    feed = fetch_feed()
    if not feed:
        print("（未取得 dashboard feed）", file=sys.stderr)
        sys.exit(1)
    if args.json:
        print(json.dumps([quadrant(it) for it in feed["items"] if quadrant(it)], ensure_ascii=False, indent=1))
        return
    md = build_md(feed)
    if args.out:
        with io.open(args.out, "w", encoding="utf-8") as f:
            f.write(md)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(md)


if __name__ == "__main__":
    main()