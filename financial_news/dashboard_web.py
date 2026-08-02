#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Financial news web dashboard (Flask, local only).

Views:
  /              - real-time market snapshot + recent events
  /analysis      - analyzed events (category/sentiment/severity), watch list
  /history       - historical reports & events by date
  /api/events    - JSON API for the recent events

Run:
  python dashboard_web.py
  then open http://127.0.0.1:5050
"""
import os
import sys
import glob
from datetime import datetime, timezone, timedelta

from flask import Flask, jsonify, render_template_string, request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db
import market_data

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
KB_REPORT_DIR = os.path.join(APP_ROOT, "..", "knowledge-base", "金融", "每日報告")

app = Flask(__name__)

BASE_HTML = """
<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>金融情報儀表板</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: "Segoe UI", "Microsoft JhengHei", sans-serif; margin: 0; background: #f4f5f7; color:#222; }
  .dark body { background:#15181d; color:#e6e8ec; }
  header { background:#1f2937; color:#fff; padding:12px 20px; display:flex; align-items:center; gap:18px; flex-wrap:wrap; }
  header h1 { font-size:18px; margin:0; }
  nav a { color:#cbd5e1; margin-right:14px; text-decoration:none; font-size:14px; }
  nav a.active { color:#fff; font-weight:bold; border-bottom:2px solid #f59e0b; }
  main { max-width:1100px; margin:16px auto; padding:0 16px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin-bottom:18px; }
  .card { background:#fff; border-radius:10px; padding:14px; box-shadow:0 1px 3px rgba(0,0,0,.08); }
  .dark .card { background:#20242c; }
  .card h3 { margin:0 0 8px; font-size:14px; color:#64748b; }
  .price { font-size:22px; font-weight:bold; }
  .up { color:#16a34a; } .down { color:#dc2626; } .flat { color:#94a3b8; }
  table { width:100%; border-collapse:collapse; font-size:13px; }
  th, td { text-align:left; padding:8px 10px; border-bottom:1px solid #e2e8f0; vertical-align:top; }
  .dark th, .dark td { border-color:#2b3039; }
  th { background:#f1f5f9; color:#475569; }
  .dark th { background:#252b35; color:#aab4c3; }
  .badge { display:inline-block; padding:2px 8px; border-radius:10px; font-size:12px; color:#fff; }
  .b-sev3 { background:#dc2626; } .b-sev2 { background:#f59e0b; } .b-sev1 { background:#3b82f6; } .b-sev0 { background:#94a3b8; }
  .b-pos { background:#16a34a; } .b-neg { background:#dc2626; } .b-neu { background:#64748b; }
  .sev { width:100%; }
  .control { margin:10px 0 14px; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  select, input, button { padding:7px 12px; border-radius:8px; border:1px solid #cbd5e1; font-size:13px; background:#fff; }
  .dark select, .dark input, .dark button { background:#20242c; color:#e6e8ec; border-color:#3a4250; }
  .muted { color:#94a3b8; font-size:12px; }
  .autoref { margin-left:auto; font-size:12px; color:#f59e0b; }
</style>
</head>
<body>
<header>
  <h1>📊 金融情報儀表板</h1>
  <nav>
    <a href="/" class="active" id="nav-live">即時</a>
    <a href="/analysis">分析</a>
    <a href="/history">歷史</a>
  </nav>
  <span class="autoref" id="clock"></span>
</header>
<main>
{{ content }}
</main>
<script>
function updateClock(){ var d=new Date(); var tw=new Date(d.getTime()+8*3600*1000).toISOString().slice(0,19).replace('T',' '); document.getElementById('clock').textContent='台灣時間 '+tw; }
setInterval(updateClock,1000); updateClock();
{% if auto_refresh %}$SCRIPT.setInterval(function(){location.reload();},60000);{% endif %}
</script>
</body>
</html>
"""


def _render(template_str, **ctx):
    return render_template_string(BASE_HTML.replace("{{ content }}", template_str), **ctx)


def _sev_class(s):
    return f"b-sev{s}" if s in (0, 1, 2, 3) else "b-sev0"


def _senti_class(s):
    return {"positive": "b-pos", "negative": "b-neg", "neutral": "b-neu"}.get(s, "b-neu")


def _fmt_ts(ts):
    if not ts:
        return ""
    try:
        d = datetime.fromisoformat(ts)
        if d.tzinfo:
            d = d.astimezone(timezone(timedelta(hours=8)))
        return d.strftime("%m-%d %H:%M")
    except Exception:
        return ts or ""


LIVE_TEMPLATE = """
<div class="control">
  <button onclick="location.reload()">重新整理</button>
  <span class="muted">每 60 秒自動更新</span>
</div>
<div class="grid">
  {% for s in snapshots %}
  <div class="card">
    <h3>{{ s.name }}</h3>
    <div class="price {{ s.cls }}">{{ s.price }} <small>{{ s.currency }}</small></div>
    <div class="{{ s.cls }}">{{ s.arrow }}</div>
  </div>
  {% endfor %}
</div>
<h2>最新事件</h2>
<table>
  <tr><th>時間</th><th>重要性</th><th>標題</th><th>分類</th><th>情緒</th></tr>
  {% for e in events %}
  <tr>
    <td class="muted">{{ e.published_s }}</td>
    <td><span class="badge {{ e.sev_c }}">{{ e.sev_label }}</span></td>
    <td><a href="{{ e.link }}" target="_blank">{{ e.title }}</a></td>
    <td>{{ e.category or '' }}</td>
    <td><span class="badge {{ e.senti_c }}">{{ e.sentiment or 'neutral' }}</span></td>
  </tr>
  {% endfor %}
</table>
"""


@app.route("/")
def live():
    snapshots = []
    for s in market_data.latest_structured():
        chg = s["change_pct"]
        if chg is None:
            cls, arrow = "flat", "― 平盤"
        elif chg > 0:
            cls, arrow = "up", f"▲ +{chg:.2f}%"
        elif chg < 0:
            cls, arrow = "down", f"▼ {chg:.2f}%"
        else:
            cls, arrow = "flat", "― 平盤"
        snapshots.append({
            "name": s["name"], "price": f"{s['price']:,.2f}",
            "currency": s["currency"], "cls": cls, "arrow": arrow,
        })
    events = []
    for e in db.recent_events(limit=30):
        events.append({
            "title": e["title"],
            "link": e["link"] or "#",
            "category": e["category"],
            "sentiment": e["sentiment"],
            "severity": e["severity"],
            "sev_c": _sev_class(e["severity"]),
            "sev_label": {0: "低", 1: "中低", 2: "中高", 3: "高"}.get(e["severity"], "低"),
            "senti_c": _senti_class(e["sentiment"]),
            "published_s": _fmt_ts(e["published"]),
        })
    return _render(LIVE_TEMPLATE, snapshots=snapshots, events=events, auto_refresh=True)


ANALYSIS_TEMPLATE = """
<div class="control">
  <form method="get" style="display:flex;gap:10px;align-items:center;">
    <label class="muted">分類:</label>
    <select name="category">
      <option value="">全部</option>
      {% for c in categories %}<option value="{{ c }}" {{ 'selected' if c==cur_cat }}>{{ c }}</option>{% endfor %}
    </select>
    <label class="muted">最小重要性:</label>
    <select name="sev">
      {% for v in [0,1,2,3] %}<option value="{{ v }}" {{ 'selected' if v==cur_sev }}>sev{{ v }}</option>{% endfor %}
    </select>
    <button type="submit">篩選</button>
  </form>
</div>
<table>
  <tr><th>重要性</th><th>情緒</th><th>時間</th><th>標題</th><th>影響說明</th><th>標的</th></tr>
  {% for e in events %}
  <tr>
    <td><span class="badge {{ e.sev_c }}">{{ e.sev_label }}</span></td>
    <td><span class="badge {{ e.senti_c }}">{{ e.sentiment }}</span></td>
    <td class="muted">{{ e.published_s }}</td>
    <td><a href="{{ e.link }}" target="_blank">{{ e.title }}</a></td>
    <td style="font-size:12px;color:#64748b;">{{ e.impact_notes or '' }}</td>
    <td style="font-size:12px;">{{ e.related_tickers or '' }}</td>
  </tr>
  {% endfor %}
</table>
"""


@app.route("/analysis")
def analysis():
    category = request.args.get("category") or ""
    sev = int(request.args.get("sev") or 0)
    events_raw = db.recent_events(limit=200, severity_min=sev, category=category or None)
    categories = ["stock", "bond", "currency", "commodity", "geopolitics", "macro", "other"]
    events = [{
        "title": e["title"], "link": e["link"] or "#",
        "category": e["category"], "sentiment": e["sentiment"],
        "severity": e["severity"], "impact_notes": e["impact_notes"],
        "related_tickers": e["related_tickers"],
        "sev_c": _sev_class(e["severity"]),
        "sev_label": {0: "低", 1: "中低", 2: "中高", 3: "高"}.get(e["severity"], "低"),
        "senti_c": _senti_class(e["sentiment"]),
        "published_s": _fmt_ts(e["published"]),
    } for e in events_raw]
    return _render(ANALYSIS_TEMPLATE, events=events, categories=categories,
                   cur_cat=category, cur_sev=sev, auto_refresh=False)


HISTORY_TEMPLATE = """
<div class="control">
  <form method="get" style="display:flex;gap:10px;align-items:center;">
    <label class="muted">選擇日期:</label>
    <select name="date">
      {% for d in dates %}<option value="{{ d }}" {{ 'selected' if d==cur_date }}>{{ d }}</option>{% endfor %}
    </select>
    <button type="submit">查看</button>
  </form>
</div>
{% if report_md %}
<pre style="white-space:pre-wrap;font-family:inherit;background:#fff;padding:16px;border-radius:10px;border:1px solid #e2e8f0;">
{{ report_md }}
</pre>
{% else %}
<div class="muted">該日無報告。</div>
{% endif %}
<hr style="margin:24px 0;">
<h2>歷史事件趨勢（最近 7 天）</h2>
<table>
  <tr><th>日期</th><th>重大事件</th><th>全部事件</th></tr>
  {% for row in trend %}
  <tr>
    <td>{{ row[0] }}</td>
    <td><span class="badge b-sev2">{{ row[1] }}</span></td>
    <td>{{ row[2] }}</td>
  </tr>
  {% endfor %}
</table>
"""


@app.route("/history")
def history():
    dates = []
    if os.path.isdir(KB_REPORT_DIR):
        dates = sorted(
            (os.path.basename(p).replace(".md", "") for p in glob.glob(os.path.join(KB_REPORT_DIR, "*.md"))),
            reverse=True,
        )
    cur = request.args.get("date") or (dates[0] if dates else "")
    report_md = ""
    if cur:
        p = os.path.join(KB_REPORT_DIR, f"{cur}.md")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                report_md = f.read()
    trend = []
    for t in db.event_trend(days=7):
        imp = t["imp"] or 0
        total = t["total"] or 0
        trend.append((t["d"], imp, total))
    return _render(HISTORY_TEMPLATE, dates=dates, cur_date=cur, report_md=report_md,
                   trend=trend, auto_refresh=False)


@app.route("/api/events")
def api_events():
    return jsonify(db.recent_events(limit=50))


if __name__ == "__main__":
    port = int(os.environ.get("FINANCE_DASH_PORT", "5050"))
    print(f"Dashboard: http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
