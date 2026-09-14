"""
精美看板 HTML 生成器 v2
大盤籌碼 + 個股篩選 + 三大觸發條件
"""
import os
import json
import html
from datetime import datetime


class DashboardGenerator:
    """產生靜態 HTML 看板"""

    def __init__(self, output_dir="output/dashboard"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def generate(self, analysis_result, index_history=None):
        """產生完整 HTML 看板"""
        alerts = analysis_result.get("alerts")
        market = analysis_result.get("market_summary", {})
        industry = analysis_result.get("industry_stats", {})
        triggers = analysis_result.get("triggers", {})
        all_stocks = analysis_result.get("all_stocks")

        alerts_data = []
        if alerts is not None and not alerts.empty:
            for _, row in alerts.head(30).iterrows():
                alerts_data.append({
                    "stock_id": str(row.get("stock_id", "")),
                    "stock_name": str(row.get("stock_name", "")),
                    "close": round(float(row.get("close", 0)), 2),
                    "pct_change": round(float(row.get("pct_change", 0)), 2),
                    "margin_balance": int(row.get("margin_balance", 0)),
                    "margin_change": int(row.get("margin_change", 0)),
                    "margin_usage_rate": round(float(row.get("margin_usage_rate", 0)), 2),
                    "est_maintenance_rate": round(float(row.get("est_maintenance_rate", 0)), 2),
                    "volume": int(row.get("volume", 0)),
                })

        html = self._build_html(alerts_data, market, industry, triggers, index_history, analysis_result)
        date_str = market.get("date", datetime.now().strftime("%Y-%m-%d"))
        filename = f"dashboard_{date_str}.html"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(html)
        latest = os.path.join(self.output_dir, "index.html")
        with open(latest, "w", encoding="utf-8") as f:
            f.write(html)
        self._update_history_page()
        print(f"  看板已產生: {filepath}")
        return filepath

    def _update_history_page(self):
        """更新歷史目錄頁，列出所有歷史看板"""
        files = sorted(
            [f for f in os.listdir(self.output_dir) if f.startswith("dashboard_") and f.endswith(".html")],
            reverse=True,
        )
        links = ""
        for f in files:
            date = f.replace("dashboard_", "").replace(".html", "")
            links += f'<li><a href="{f}">{date}</a></li>\n'

        html = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <title>歷史看板</title>
    <style>
        body {{ font-family: sans-serif; background: #0f172a; color: #e2e8f0; padding: 40px; }}
        a {{ color: #60a5fa; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        li {{ margin: 8px 0; font-size: 1.1em; }}
    </style>
</head>
<body>
    <h1>歷史看板目錄</h1>
    <ul>{links}</ul>
    <p><a href="index.html">← 回最新看板</a></p>
</body>
</html>"""
        path = os.path.join(self.output_dir, "history.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)

    def _build_html(self, alerts, market, industry, triggers, index_history, analysis_result):
        date_str = market.get("date", datetime.now().strftime("%Y-%m-%d"))
        idx_today = market.get("index_today", 0)
        idx_change = market.get("index_change", 0)
        idx_pct = market.get("index_change_pct", 0)
        total_margin_b = market.get("total_margin_balance_billion", 0)
        margin_change_b = market.get("margin_change_billion", 0)
        maintenance = market.get("est_maintenance_rate", 0)
        if maintenance is None:
            maintenance = 0
        alert_count = len(alerts)

        idx_color = "#10b981" if idx_change >= 0 else "#ef4444"
        idx_arrow = "▲" if idx_change >= 0 else "▼"
        margin_color = "#10b981" if margin_change_b >= 0 else "#ef4444"
        margin_arrow = "▲" if margin_change_b >= 0 else "▼"
        maint_color = "#ef4444" if maintenance < 130 else ("#f59e0b" if maintenance < 145 else "#10b981")

        mc_stocks = triggers.get("margin_call", [])
        ps_stocks = triggers.get("panic_sell", [])
        ib_stocks = triggers.get("institutional_buy", [])
        
        # 三大法人資料
        institutional = analysis_result.get("institutional_summary", {})
        inst_top_buyers = institutional.get("top_buyers", [])
        inst_top_sellers = institutional.get("top_sellers", [])
        foreign_net = institutional.get("foreign_net", 0)
        trust_net = institutional.get("trust_net", 0)
        dealer_net = institutional.get("dealer_net", 0)
        total_inst_net = institutional.get("total_net", 0)

        quadrant_html = self._build_quadrant_html(analysis_result.get("quadrant"))
        chart_payload_json = json.dumps(analysis_result.get("chart_payload") or {}, ensure_ascii=False)
        try:
            from src.advanced_data import get_tdcc_shareholding
        except ImportError:
            from advanced_data import get_tdcc_shareholding
        tdcc_data = get_tdcc_shareholding() or {"week": "", "cur": {}, "prev": {}}
        tdcc_json = json.dumps(tdcc_data, ensure_ascii=False)

        categories = [
            ("融資斷頭潮", [(s['stock_id'], s['stock_name']) for s in mc_stocks]),
            ("恐慌停損", [(s['stock_id'], s['stock_name']) for s in ps_stocks]),
            ("主力換手", [(s['stock_id'], s['stock_name']) for s in ib_stocks]),
            ("警示篩選", [(a['stock_id'], a['stock_name']) for a in alerts]),
            ("法人淨買超", [(s.get('code', ''), s.get('name', '')) for s in inst_top_buyers]),
            ("法人淨賣超", [(s.get('code', ''), s.get('name', '')) for s in inst_top_sellers]),
        ]
        quads = (analysis_result.get("quadrant") or {}).get("quadrants") or {}
        for qk, ql in [("Q1", "象限一·警訊"), ("Q2", "象限二·多頭"), ("Q3", "象限三·波段末端"), ("Q4", "象限四·打底")]:
            categories.append((ql, [(s.get('code', ''), s.get('name', '')) for s in quads.get(qk, [])]))
        bulk_copy_html = self._build_bulk_copy_buttons(categories)

        return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>台股融資券分析看板 - {date_str}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft JhengHei', sans-serif;
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%);
            color: #e2e8f0;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        .header {{
            text-align: center;
            padding: 30px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 30px;
        }}
        .header h1 {{
            font-size: 2.2em;
            background: linear-gradient(90deg, #60a5fa, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }}
        .header .date {{ color: #94a3b8; font-size: 1.1em; }}
        .cards {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .card {{
            background: rgba(30, 41, 59, 0.8);
            border-radius: 16px;
            padding: 20px;
            border: 1px solid rgba(255,255,255,0.08);
            backdrop-filter: blur(10px);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .card:hover {{
            transform: translateY(-4px);
            box-shadow: 0 12px 40px rgba(0,0,0,0.3);
        }}
        .card .label {{ color: #94a3b8; font-size: 0.85em; margin-bottom: 6px; }}
        .card .value {{ font-size: 1.8em; font-weight: 700; }}
        .card .sub {{ font-size: 0.8em; margin-top: 4px; }}
        .section {{
            background: rgba(30, 41, 59, 0.8);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            border: 1px solid rgba(255,255,255,0.08);
        }}
        .section h2 {{
            font-size: 1.3em;
            margin-bottom: 20px;
            color: #e2e8f0;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .section h2::before {{ content: ''; width: 4px; height: 20px; border-radius: 2px; }}
        .section h2.red::before {{ background: #ef4444; }}
        .section h2.yellow::before {{ background: #f59e0b; }}
        .section h2.green::before {{ background: #10b981; }}
        .section h2.blue::before {{ background: #60a5fa; }}
        .trigger-section {{ margin-bottom: 20px; padding: 20px; border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); }}
        .trigger-section.mc {{ background: rgba(239,68,68,0.08); border-color: rgba(239,68,68,0.3); }}
        .trigger-section.ps {{ background: rgba(245,158,11,0.08); border-color: rgba(245,158,11,0.3); }}
        .trigger-section.ib {{ background: rgba(16,185,129,0.08); border-color: rgba(16,185,129,0.3); }}
        .trigger-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 12px;
        }}
        .trigger-badge {{
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 600;
        }}
        .trigger-badge.mc {{ background: rgba(239,68,68,0.2); color: #ef4444; }}
        .trigger-badge.ps {{ background: rgba(245,158,11,0.2); color: #f59e0b; }}
        .trigger-badge.ib {{ background: rgba(16,185,129,0.2); color: #10b981; }}
        .trigger-desc {{ color: #94a3b8; font-size: 0.85em; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.95em;
        }}
        th {{
            background: rgba(51, 65, 85, 0.5);
            padding: 12px 10px;
            text-align: left;
            font-weight: 600;
            color: #94a3b8;
            border-bottom: 2px solid rgba(255,255,255,0.1);
            position: sticky;
            top: 0;
        }}
        td {{
            padding: 12px 10px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }}
        tr:hover {{ background: rgba(51, 65, 85, 0.3); }}
        .negative {{ color: #ef4444; }}
        .positive {{ color: #10b981; }}
        .neutral {{ color: #94a3b8; }}
        .stock-id {{
            font-weight: 700;
            color: #60a5fa;
            cursor: pointer;
        }}
        .stock-id:hover {{ text-decoration: underline; }}
        .stock-name {{
            color: #e2e8f0;
            cursor: pointer;
        }}
        .stock-name:hover {{ text-decoration: underline; color: #60a5fa; }}
        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 24px;
            margin-bottom: 24px;
        }}
        .chart-box {{
            background: rgba(30, 41, 59, 0.8);
            border-radius: 16px;
            padding: 24px;
            border: 1px solid rgba(255,255,255,0.08);
        }}
        .chart-box h3 {{
            margin-bottom: 16px;
            color: #e2e8f0;
            font-size: 1.1em;
        }}
        #industryChart {{ max-height: 150px; width: 100%; }}
        .footer {{
            text-align: center;
            padding: 20px;
            color: #64748b;
            font-size: 0.85em;
            border-top: 1px solid rgba(255,255,255,0.05);
            margin-top: 20px;
        }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 0.8em;
            font-weight: 600;
        }}
        .badge-danger {{ background: rgba(239,68,68,0.2); color: #ef4444; }}
        .badge-warning {{ background: rgba(245,158,11,0.2); color: #f59e0b; }}
        .badge-success {{ background: rgba(16,185,129,0.2); color: #10b981; }}
        .table-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            margin: 16px 0 8px 0;
        }}
        .table-header h3 {{ font-size: 1em; color: #e2e8f0; margin: 0; }}
        .copy-btn {{
            background: rgba(96, 165, 250, 0.15);
            border: 1px solid rgba(96, 165, 250, 0.4);
            color: #60a5fa;
            padding: 5px 14px;
            border-radius: 20px;
            font-size: 0.85em;
            cursor: pointer;
            transition: all 0.2s;
            white-space: nowrap;
        }}
        .copy-btn:hover {{ background: rgba(96, 165, 250, 0.3); }}
        .copy-btn.copied {{ background: rgba(16,185,129,0.2); border-color: rgba(16,185,129,0.5); color: #10b981; }}
        .copy-btns {{ display: flex; gap: 8px; margin-left: auto; }}
        .bulk-copy {{
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
            margin: 14px 0;
            padding: 10px 16px;
            background: rgba(51,65,85,0.25);
            border: 1px dashed rgba(148,163,184,0.35);
            border-radius: 10px;
        }}
        .bulk-label {{ color: #94a3b8; font-size: 0.85em; }}
        .bulk-note {{ color: #64748b; font-size: 0.75em; width: 100%; }}
        @media (max-width: 768px) {{
            .cards {{ grid-template-columns: 1fr 1fr; }}
            .charts-grid {{ grid-template-columns: 1fr; }}
            .header h1 {{ font-size: 1.5em; }}
            table {{ font-size: 0.85em; }}
            td, th {{ padding: 10px 6px; }}
        }}
        .quad-market {{
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 20px;
            border: 1px solid;
            background: rgba(30,41,59,0.6);
            display: flex;
            flex-direction: column;
            gap: 6px;
        }}
        .quad-market .qm-title {{ font-size: 1.15em; font-weight: 700; }}
        .quad-market .qm-advice {{ font-weight: 600; }}
        .quad-legend {{
            background: rgba(30,41,59,0.6);
            border: 1px solid;
            border-radius: 8px;
            padding: 4px 10px;
            font-size: 0.85em;
            white-space: nowrap;
        }}
        .panel-title {{ color: #e2e8f0; font-size: 1.1em; margin-bottom: 16px; }}
        .quad-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 16px;
        }}
        .quad-box {{
            border-radius: 12px;
            padding: 16px;
            border: 1px solid rgba(255,255,255,0.1);
            background: rgba(30,41,59,0.5);
        }}
        .quad-box .qb-head {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 10px;
        }}
        .quad-box .qb-label {{ font-size: 1.05em; font-weight: 700; }}
        .quad-box .qb-count {{ font-size: 1.6em; font-weight: 700; }}
        .quad-box .qb-desc {{ color: #94a3b8; font-size: 0.85em; margin-bottom: 10px; }}
        .stock-chip {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(51,65,85,0.5);
            border-radius: 20px;
            padding: 3px 10px;
            margin: 3px;
            font-size: 0.8em;
            cursor: pointer;
            border: 1px solid rgba(255,255,255,0.08);
        }}
        .stock-chip:hover {{ background: rgba(96,165,250,0.2); }}
        .stock-chip .sc-code {{ color: #60a5fa; font-weight: 700; }}
        .stock-chip .sc-pct {{ font-weight: 600; }}
        .echart-box {{ width: 100%; height: 380px; }}
        .echart-tall {{ width: 100%; height: 620px; }}
        .zoom-toggle {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            margin-left: 14px;
            font-size: 0.62em;
            font-weight: 500;
            color: #94a3b8;
            background: rgba(51,65,85,0.5);
            border: 1px solid rgba(255,255,255,0.1);
            padding: 4px 10px;
            border-radius: 20px;
            cursor: pointer;
            user-select: none;
            vertical-align: middle;
        }}
        .zoom-toggle input {{ accent-color: #60a5fa; cursor: pointer; }}
        .tip-sel {{
            background: rgba(51,65,85,0.6);
            color: #94a3b8;
            border: 1px solid rgba(96,165,250,0.4);
            border-radius: 8px;
            padding: 5px 8px;
            font-size: 0.8em;
            cursor: pointer;
        }}
        .tip-sel option {{ background: #1e293b; color: #e2e8f0; }}
        .cat-badge {{
            background: rgba(51,65,85,0.5);
            border: 1px solid rgba(255,255,255,0.15);
            color: #94a3b8;
            padding: 2px 10px;
            border-radius: 12px;
            font-size: 0.78em;
            white-space: nowrap;
        }}
        .tabs {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 20px; }}
        .tab-btn {{
            background: rgba(51,65,85,0.5);
            border: 1px solid rgba(255,255,255,0.1);
            color: #94a3b8;
            padding: 8px 16px;
            border-radius: 20px;
            cursor: pointer;
            font-size: 0.95em;
            transition: all 0.2s;
        }}
        .tab-btn:hover {{ color: #e2e8f0; background: rgba(96,165,250,0.15); }}
        .tab-btn.active {{ background: rgba(96,165,250,0.25); border-color: rgba(96,165,250,0.5); color: #60a5fa; font-weight: 600; }}
        .tab-panel {{ display: none; }}
        .tab-panel.active {{ display: block; }}
        #stockSelect {{
            background: rgba(51,65,85,0.6);
            color: #e2e8f0;
            border: 1px solid rgba(96,165,250,0.4);
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 1em;
            margin-bottom: 16px;
            min-width: 260px;
        }}
        #stockSelect option {{ background: #1e293b; color: #e2e8f0; }}
        .q-input {{
            background: rgba(51,65,85,0.6);
            color: #e2e8f0;
            border: 1px solid rgba(96,165,250,0.4);
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 1em;
            width: 130px;
        }}
        .q-input:focus {{ outline: none; border-color: #60a5fa; }}
        .q-btn {{
            background: linear-gradient(90deg, #60a5fa, #a78bfa);
            color: #0f172a;
            border: none;
            border-radius: 8px;
            padding: 8px 14px;
            font-size: 1em;
            font-weight: 600;
            cursor: pointer;
            transition: opacity 0.2s;
        }}
        .q-btn:hover {{ opacity: 0.85; }}
        .q-btn:disabled {{ opacity: 0.5; cursor: wait; }}
        .q-msg {{ color: #94a3b8; font-size: 0.9em; }}
        .q-msg.ok {{ color: #34d399; }}
        .q-msg.err {{ color: #ef4444; }}
        .chart-note {{
            font-size: 0.82em;
            color: #94a3b8;
            line-height: 1.6;
            margin: 6px 0 10px;
            padding: 8px 12px;
            background: rgba(51,65,85,0.25);
            border-left: 3px solid #475569;
            border-radius: 4px;
        }}
        .chart-note b {{ color: #f97316; }}
        .chart-note i {{ color: #10b981; font-style: normal; }}
        .tdcc-card {{
            margin: 6px 0 10px;
            padding: 10px 14px;
            border-radius: 6px;
            background: rgba(15,23,42,0.55);
            border: 1px solid #334155;
            font-size: 0.85em;
            line-height: 1.6;
        }}
        .tdcc-title {{ color: #e2e8f0; font-weight: 600; margin-bottom: 6px; }}
        .tdcc-title .wk {{ color: #94a3b8; font-weight: 400; margin-left: 6px; }}
        .tdcc-stats {{ display: flex; flex-wrap: wrap; gap: 18px; margin-bottom: 4px; }}
        .tdcc-stat span {{ color: #94a3b8; margin-right: 4px; }}
        .tdcc-stat b {{ color: #f8fafc; }}
        .tdcc-stat em {{ font-style: normal; margin-left: 4px; }}
        .tdcc-stat em.up {{ color: #ef4444; }}
        .tdcc-stat em.down {{ color: #10b981; }}
        .tdcc-stat em.flat {{ color: #94a3b8; }}
        .tdcc-read {{ color: #f1f5f9; padding: 6px 8px; margin-top: 6px; background: rgba(148,163,184,0.10); border-radius: 4px; }}
        .tdcc-read b {{ color: #fbbf24; }}
        .tdcc-warn {{ color: #64748b; font-size: 0.9em; margin-top: 6px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>台股融資券分析看板</h1>
            <div class="date">{date_str} | 每日 21:30 自動更新</div>
        </div>

        <!-- 大盤籌碼 -->
        <div class="cards">
            <div class="card">
                <div class="label">加權指數</div>
                <div class="value" style="color:{idx_color}">{idx_today:,.0f}</div>
                <div class="sub" style="color:{idx_color}">{idx_arrow} {abs(idx_change):,.0f} ({idx_pct:+.2f}%)</div>
            </div>
            <div class="card">
                <div class="label">大盤融資餘額（億元）</div>
                <div class="value" style="color:{margin_color}">{total_margin_b:,.2f}</div>
                <div class="sub" style="color:{margin_color}">{margin_arrow} {abs(margin_change_b):,.2f} 億</div>
            </div>
            <div class="card">
                <div class="label">整體融資維持率</div>
                <div class="value" style="color:{maint_color}">{maintenance:,.2f}%</div>
                <div class="sub" style="color:{maint_color}">{"⚠ 低於警戒" if maintenance < 130 else "正常" if maintenance > 145 else "偏高"}</div>
            </div>
            <div class="card">
                <div class="label">今日警示股</div>
                <div class="value" style="color:#f59e0b">{alert_count}</div>
                <div class="sub">跌幅>{abs(2.0)}% + 融資減</div>
            </div>
            <div class="card">
                <div class="label">融資斷頭警示</div>
                <div class="value" style="color:#ef4444">{len(mc_stocks)}</div>
                <div class="sub">3日累計跌>10% + 維持率<135%</div>
            </div>
            <div class="card">
                <div class="label">恐慌停損</div>
                <div class="value" style="color:#f59e0b">{len(ps_stocks)}</div>
                <div class="sub">今日跌>4% + 融資大減</div>
            </div>
            <div class="card">
                <div class="label">主力換手</div>
                <div class="value" style="color:#10b981">{len(ib_stocks)}</div>
                <div class="sub">今日漲 + 融資減 = 籌碼好轉</div>
            </div>
        </div>

        <!-- 三大法人買賣超 -->
        <div class="cards" style="margin-top: -8px;">
            <div class="card">
                <div class="label">外陸資淨買超</div>
                <div class="value" style="color:{'#10b981' if foreign_net >= 0 else '#ef4444'}">{foreign_net:+,}</div>
                <div class="sub">外陸資買賣超股數</div>
            </div>
            <div class="card">
                <div class="label">投信淨買超</div>
                <div class="value" style="color:{'#10b981' if trust_net >= 0 else '#ef4444'}">{trust_net:+,}</div>
                <div class="sub">投信買賣超股數</div>
            </div>
            <div class="card">
                <div class="label">自營商淨買超</div>
                <div class="value" style="color:{'#10b981' if dealer_net >= 0 else '#ef4444'}">{dealer_net:+,}</div>
                <div class="sub">自營商買賣超股數</div>
            </div>
            <div class="card">
                <div class="label">三大法人合計</div>
                <div class="value" style="color:{'#10b981' if total_inst_net >= 0 else '#ef4444'}">{total_inst_net:+,}</div>
                <div class="sub">合計淨買超股數</div>
            </div>
        </div>

        <!-- 產業分布 -->
        <div class="section">
            <h2 class="green">產業分布</h2>
            <canvas id="industryChart" style="max-height:150px;width:100%"></canvas>
        </div>

        <!-- 大盤綜合圖 -->
        <div class="section">
            <h2 class="red">大盤走勢 + 成交量 + 融資 + 維持率 + 三大法人（綜合）
                <label class="zoom-toggle"><input type="checkbox" id="comboZoomChk" checked onchange="toggleZoom('combo', this.checked)"> dataZoom</label>
                <select class="tip-sel" id="comboTipSel" onchange="setTooltip('combo', this.value)">
                    <option value="follow">提示:跟隨</option>
                    <option value="fixed" selected>提示:固定</option>
                    <option value="off">提示:關閉</option>
                </select>
            </h2>
            <div id="marketComboChart" style="width:100%;height:660px"></div>
            <div class="chart-note"><b>線圖判讀：</b>融資餘額：<b>警戒線</b>＝近半年自身 75 分位（橙虛線，以上為<b>紅底危險區</b>）、<i>安全線</i>＝25 分位（綠虛線，以下為<i>綠底安全區</i>）。維持率（紫線，右側 % 軸）：<b>130% 警戒</b>＝整體維持率低於此逼近追繳斷頭、<i>160% 安全</i>。</div>
        </div>

        <!-- 個股分析（分頁） -->
        <div class="section">
            <h2 class="blue">個股分析（K線 + 籌碼 / 三大觸發 / 法人排行 / 個股篩選 / 四象限）</h2>
            <div class="tabs">
                <button class="tab-btn active" data-tab="tab-kline" onclick="switchTab('tab-kline', this)">K線 + 籌碼</button>
                <button class="tab-btn" data-tab="tab-triggers" onclick="switchTab('tab-triggers', this)">三大觸發</button>
                <button class="tab-btn" data-tab="tab-inst" onclick="switchTab('tab-inst', this)">法人買賣超排行</button>
                <button class="tab-btn" data-tab="tab-alerts" onclick="switchTab('tab-alerts', this)">個股篩選</button>
                <button class="tab-btn" data-tab="tab-quadrant" onclick="switchTab('tab-quadrant', this)">四象限定位</button>
            </div>

            {bulk_copy_html}

            <div id="tab-kline" class="tab-panel active">
                <div style="display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap">
                    <select id="stockSelect"></select>
                    <input type="text" id="stockQuery" class="q-input" placeholder="任意股代號 如 2330" maxlength="6"
                           onkeydown="if(event.key==='Enter')queryStock()">
                    <button class="q-btn" id="stockQueryBtn" onclick="queryStock()">查詢</button>
                    <span class="q-msg" id="stockQueryMsg"></span>
                    <label class="zoom-toggle" style="margin-left:0"><input type="checkbox" id="stockZoomChk" checked onchange="toggleZoom('stock', this.checked)"> dataZoom</label>
                    <select class="tip-sel" id="stockTipSel" onchange="setTooltip('stock', this.value)">
                        <option value="follow">提示:跟隨</option>
                        <option value="fixed" selected>提示:固定</option>
                        <option value="off">提示:關閉</option>
                    </select>
                </div>
                <div id="stockCats" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;min-height:26px"></div>
                <div id="stockChart" class="echart-tall"></div>
                <div id="tdccCard"></div>
                <div class="chart-note"><b>融資餘額判讀：</b><b>警戒線</b>＝該股近半年自身 75 分位（橙虛線，以上為<b>紅底危險區</b>＝散戶槓桿高、回檔易斷頭）、<i>安全線</i>＝25 分位（綠虛線，以下為<i>綠底安全區</i>）。</div>
            </div>

            <div id="tab-triggers" class="tab-panel">
                <div class="trigger-section mc">
                    <div class="trigger-header">
                        <span class="trigger-badge mc">融資斷頭潮</span>
                        <span class="trigger-desc">3日累計跌>10% + 今日融資大減 + 維持率<135% → 散戶被強制斷頭</span>
                    </div>
                    {self._build_trigger_table(mc_stocks, "mc")}
                </div>

                <div class="trigger-section ps">
                    <div class="trigger-header">
                        <span class="trigger-badge ps">恐慌停損</span>
                        <span class="trigger-desc">今日跌>4% + 融資大減 + 維持率>145% → 散戶心態崩潰主動停損</span>
                    </div>
                    {self._build_trigger_table(ps_stocks, "ps")}
                </div>

                <div class="trigger-section ib">
                    <div class="trigger-header">
                        <span class="trigger-badge ib">主力換手 / 獲利停利</span>
                        <span class="trigger-desc">今日大漲 + 融資大減 → 散戶下車、大戶接走，後市看好</span>
                    </div>
                    {self._build_trigger_table(ib_stocks, "ib")}
                </div>
            </div>

            <div id="tab-inst" class="tab-panel">
                {self._build_institutional_table(inst_top_buyers, "淨買超前5名", "buy")}
                {self._build_institutional_table(inst_top_sellers, "淨賣超前5名", "sell")}
            </div>

            <div id="tab-alerts" class="tab-panel">
                {self._build_alerts_table(alerts)}
            </div>

            <div id="tab-quadrant" class="tab-panel">
                {quadrant_html}
            </div>
        </div>

        <div class="footer">
            台股融資券分析看板 | 資料來源：台灣證券交易所 | 每日 21:30 自動更新<br>
            &copy; {date_str[:4]} 胚騰 AI Agent
        </div>
    </div>

    <script>
        const chartPayload = {chart_payload_json};
const tdccData = {tdcc_json};
        const industryData = {json.dumps(industry, ensure_ascii=False)};

        if (Object.keys(industryData).length > 0) {{
            const colors = ['#60a5fa','#a78bfa','#34d399','#fbbf24','#f87171','#fb923c','#e879f9','#22d3ee','#4ade80','#f472b6'];
            new Chart(document.getElementById('industryChart'), {{
                type: 'doughnut',
                data: {{
                    labels: Object.keys(industryData),
                    datasets: [{{ data: Object.values(industryData), backgroundColor: colors.slice(0, Object.keys(industryData).length), borderWidth: 0 }}]
                }},
                options: {{
                    responsive: true,
                    plugins: {{
                        legend: {{ position: 'right', labels: {{ color: '#94a3b8', padding: 15 }} }}
                    }}
                }}
            }});
        }}

        function symRange(arr) {{
            const m = Math.max.apply(null, arr.map(v => Math.abs(v || 0)).concat([1]));
            return [-m, m];
        }}

        // ---------- 1. 大盤綜合圖（指數 + 融資 + 維持率 + 法人） ----------
        // ---------- 1. 大盤綜合圖 ----------
        let comboChart = null;
        const comboZoomDef = [
            {{ type: 'inside', xAxisIndex: [0, 1, 2, 3], start: 0, end: 100 }},
            {{ type: 'slider', xAxisIndex: [0, 1, 2, 3], start: 0, end: 100, bottom: 2, height: 16,
               textStyle: {{ color: '#64748b', fontSize: 10 }}, borderColor: '#334155',
               backgroundColor: 'rgba(15,23,42,0.6)',
               dataBackground: {{ lineStyle: {{ color: '#475569', opacity: 0.5 }}, areaStyle: {{ color: 'rgba(71,85,105,0.12)' }} }},
               fillerColor: 'rgba(96,165,250,0.2)',
               handleStyle: {{ color: '#60a5fa' }}, moveHandleStyle: {{ color: '#60a5fa' }},
               emphasis: {{ handleStyle: {{ color: '#93c5fd' }} }} }}
        ];
        const stockZoomDef = [
            {{ type: 'inside', xAxisIndex: [0, 1, 2, 3, 4], start: 30, end: 100 }},
            {{ type: 'slider', xAxisIndex: [0, 1, 2, 3, 4], start: 30, end: 100, bottom: 2, height: 16,
               textStyle: {{ color: '#64748b', fontSize: 10 }}, borderColor: '#334155',
               backgroundColor: 'rgba(15,23,42,0.6)',
               dataBackground: {{ lineStyle: {{ color: '#475569', opacity: 0.5 }}, areaStyle: {{ color: 'rgba(71,85,105,0.12)' }} }},
               fillerColor: 'rgba(96,165,250,0.2)',
               handleStyle: {{ color: '#60a5fa' }}, moveHandleStyle: {{ color: '#60a5fa' }},
               emphasis: {{ handleStyle: {{ color: '#93c5fd' }} }} }}
        ];

        function toggleZoom(key, on) {{
            const ch = key === 'combo' ? comboChart : stockChart;
            if (!ch) return;
            ch.setOption({{ dataZoom: on ? (key === 'combo' ? comboZoomDef : stockZoomDef) : [] }}, {{ replaceMerge: 'dataZoom' }});
        }}

        function setTooltip(key, mode) {{
            const ch = key === 'combo' ? comboChart : stockChart;
            if (!ch) return;
            const t = {{ trigger: 'axis', axisPointer: {{ type: 'cross' }}, confine: true }};
            if (mode === 'off') {{
                t.trigger = 'none';
            }} else if (mode === 'fixed') {{
                t.position = [12, 78];
            }}
            ch.setOption({{ tooltip: t }}, {{ replaceMerge: 'tooltip' }});
        }}

        if (chartPayload.market && chartPayload.market.dates.length > 1) {{
            const mk = chartPayload.market;
            comboChart = echarts.init(document.getElementById('marketComboChart'), null, {{ devicePixelRatio: Math.max(window.devicePixelRatio || 1, 2) }});

            // 法人序列對齊到市場日期
            const instIdx = {{}};
            (mk.inst_dates || []).forEach((d, i) => {{ instIdx[d] = i; }});
            const align = (arr) => mk.dates.map(d => (instIdx[d] !== undefined ? arr[instIdx[d]] : null));
            const iForeign = align(mk.inst_foreign);
            const iTrust = align(mk.inst_trust);
            const iDealer = align(mk.inst_dealer);
            const mSym = symRange(mk.margin_change);
            // 大盤融資餘額警戒/安全線：依大盤自身融資餘額分位數動態計算
            const mBal = (mk.margin_total || []).filter(v => v != null);
            let mSafe = null, mWarn = null;
            if (mBal.length >= 8) {{
                const mSorted = mBal.slice().sort((a, b) => a - b);
                mSafe = mSorted[Math.round(mSorted.length * 0.25) - 1];
                mWarn = mSorted[Math.round(mSorted.length * 0.75) - 1];
            }}

            comboChart.setOption({{
                backgroundColor: 'transparent',
                animation: false,
                legend: {{ data: ['K線', 'MA8', 'MA21', 'MA55', '成交量', '融資增減', '融資餘額', '維持率', '外資', '投信', '自營'], top: 0,
                    textStyle: {{ color: '#94a3b8', fontSize: 13 }} }},
                tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }} }},
                axisPointer: {{ link: [{{ xAxisIndex: 'all' }}] }},
                grid: [
                    {{ left: 70, right: 100, top: '1%', height: '38%' }},
                    {{ left: 70, right: 100, top: '40%', height: '15%' }},
                    {{ left: 70, right: 100, top: '56%', height: '17%' }},
                    {{ left: 70, right: 100, top: '74%', height: '22%' }}
                ],
                xAxis: [
                    {{ type: 'category', data: mk.dates, gridIndex: 0, axisLabel: {{ color: '#94a3b8' }}, axisLine: {{ lineStyle: {{ color: '#475569' }} }} }},
                    {{ type: 'category', data: mk.dates, gridIndex: 1, axisLabel: {{ show: false }} }},
                    {{ type: 'category', data: mk.dates, gridIndex: 2, axisLabel: {{ show: false }} }},
                    {{ type: 'category', data: mk.dates, gridIndex: 3, axisLabel: {{ color: '#94a3b8', fontSize: 12 }} }}
                ],
                yAxis: [
                    {{ gridIndex: 0, scale: true, name: '指數', axisLabel: {{ color: '#60a5fa', fontSize: 12 }}, nameTextStyle: {{ color: '#60a5fa', fontSize: 13 }},
                       splitLine: {{ lineStyle: {{ color: 'rgba(255,255,255,0.06)' }} }} }},
                    {{ gridIndex: 1, scale: true, name: '成交量(億股)', axisLabel: {{ color: '#94a3b8', fontSize: 12 }}, nameTextStyle: {{ color: '#94a3b8', fontSize: 13 }},
                       splitLine: {{ show: false }} }},
                    {{ gridIndex: 2, position: 'left', offset: 0, min: mSym[0], max: mSym[1], name: '增減(張)', axisLabel: {{ color: '#94a3b8', fontSize: 11 }}, nameTextStyle: {{ color: '#94a3b8', fontSize: 12 }},
                       splitLine: {{ show: false }} }},
                    {{ gridIndex: 2, position: 'right', offset: 0, scale: true, name: '餘額', axisLabel: {{ color: '#f59e0b', fontSize: 11 }}, nameTextStyle: {{ color: '#f59e0b', fontSize: 12 }},
                       splitLine: {{ show: false }} }},
                    {{ gridIndex: 2, position: 'right', offset: 50, min: 100, name: '維持率%', axisLabel: {{ color: '#a78bfa', fontSize: 11 }}, nameTextStyle: {{ color: '#a78bfa', fontSize: 12 }},
                       splitLine: {{ show: false }} }},
                    {{ gridIndex: 3, name: '買賣超(千張)', axisLabel: {{ color: '#94a3b8', fontSize: 12 }}, nameTextStyle: {{ color: '#94a3b8', fontSize: 13 }},
                       splitLine: {{ lineStyle: {{ color: 'rgba(255,255,255,0.06)' }} }} }}
                ],
                dataZoom: comboZoomDef,
                series: [
                    {{ name: 'K線', type: 'candlestick', xAxisIndex: 0, yAxisIndex: 0,
                       data: mk.c.map((_, i) => (mk.o[i] != null ? [mk.o[i], mk.c[i], mk.l[i], mk.h[i]] : null)),
                       itemStyle: {{ color: '#ef4444', color0: '#10b981', borderColor: '#ef4444', borderColor0: '#10b981' }} }},
                    {{ name: 'MA8', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: calcMA(mk.c, 8),
                       showSymbol: false, sampling: 'lttb', lineStyle: {{ width: 1.2, color: '#f59e0b' }} }},
                    {{ name: 'MA21', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: calcMA(mk.c, 21),
                       showSymbol: false, sampling: 'lttb', lineStyle: {{ width: 1.2, color: '#60a5fa' }} }},
                    {{ name: 'MA55', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: calcMA(mk.c, 55),
                       showSymbol: false, sampling: 'lttb', lineStyle: {{ width: 1.2, color: '#ec4899' }} }},
                    {{ name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1,
                       data: (mk.volume || []).map((v, i) => ({{ value: v / 1e8, itemStyle: {{ color: (i > 0 && mk.c[i] >= mk.c[i-1]) ? '#ef4444' : '#10b981' }} }})),
                       barMaxWidth: 12 }},
                    {{ name: '融資增減', type: 'bar', xAxisIndex: 2, yAxisIndex: 2,
                       data: mk.margin_change.map(v => (v == null ? null : {{ value: v, itemStyle: {{ color: v >= 0 ? '#ef4444' : '#10b981' }} }})),
                       barMaxWidth: 14 }},
                    {{ name: '融資餘額', type: 'line', xAxisIndex: 2, yAxisIndex: 3, data: mk.margin_total,
                       sampling: 'lttb', smooth: true, symbol: 'none', lineStyle: {{ color: '#f59e0b', width: 2 }},
                       itemStyle: {{ color: '#f59e0b' }},
                       markLine: mWarn == null ? undefined : {{
                           symbol: 'none', silent: true,
                           label: {{ show: true, fontSize: 10, color: '#e2e8f0', formatter: '{{b}}' }},
                           data: [
                               {{ name: '警戒線', yAxis: mWarn, lineStyle: {{ color: '#f97316', width: 1, type: 'dashed' }},
                                  label: {{ color: '#f97316', formatter: '餘額警戒(75分位)', fontSize: 10 }} }},
                               {{ name: '安全線', yAxis: mSafe, lineStyle: {{ color: '#10b981', width: 1, type: 'dashed' }},
                                  label: {{ color: '#10b981', formatter: '餘額安全(25分位)', fontSize: 10 }} }}
                           ]
                       }},
                       markArea: mWarn == null ? undefined : {{
                           silent: true,
                           label: {{ show: false }},
                           data: [
                               [{{ yAxis: mWarn, itemStyle: {{ color: 'rgba(239,68,68,0.10)' }} }}, {{ yAxis: 'max' }}],
                               [{{ yAxis: 'min', itemStyle: {{ color: 'rgba(16,185,129,0.08)' }} }}, {{ yAxis: mSafe }}]
                           ]
                       }} }},
                    {{ name: '維持率', type: 'line', xAxisIndex: 2, yAxisIndex: 4, data: mk.maintenance,
                       sampling: 'lttb', smooth: true, symbol: 'none', lineStyle: {{ color: '#a78bfa', width: 1.5 }},
                       markLine: {{
                           symbol: 'none',
                           data: [
                                {{ yAxis: 130, name: '警戒線', lineStyle: {{ color: '#ef4444', width: 1.5 }},
                                   label: {{ color: '#ef4444', formatter: '維持率<130% 警戒', fontSize: 10 }} }},
                                {{ yAxis: 160, name: '安全線', lineStyle: {{ color: '#10b981', width: 1, type: 'dashed' }},
                                   label: {{ color: '#10b981', formatter: '維持率>160% 安全', fontSize: 10 }} }}
                           ]
                       }} }},
                    {{ name: '外資', type: 'bar', xAxisIndex: 3, yAxisIndex: 5, stack: 'inst', data: iForeign.map(v => v / 1000),
                       barMaxWidth: 12, itemStyle: {{ color: '#60a5fa' }} }},
                    {{ name: '投信', type: 'bar', xAxisIndex: 3, yAxisIndex: 5, stack: 'inst', data: iTrust.map(v => v / 1000),
                       barMaxWidth: 12, itemStyle: {{ color: '#34d399' }} }},
                    {{ name: '自營', type: 'bar', xAxisIndex: 3, yAxisIndex: 5, stack: 'inst', data: iDealer.map(v => v / 1000),
                       barMaxWidth: 12, itemStyle: {{ color: '#a78bfa' }} }}
                ]
            }});
            setTooltip('combo', document.getElementById('comboTipSel').value);
            window.addEventListener('resize', () => comboChart.resize());
        }}

        // ---------- 2. 個股 K 線 + 籌碼 ----------
        let stockChart = null;
        const stockSel = document.getElementById('stockSelect');

        function calcMA(kc, n) {{
            return kc.map((_, i) => {{
                if (i < n - 1) return null;
                let sum = 0, cnt = 0;
                for (let j = i - n + 1; j <= i; j++) {{
                    if (kc[j] != null) {{ sum += kc[j]; cnt++; }}
                }}
                if (cnt < n * 0.6) return null;
                return +(sum / cnt).toFixed(2);
            }});
        }}

        function drawStock(s, code) {{
            const kd = s.kline.dates;
            const mSym = symRange(s.margin.change);
            const sSym = symRange(s.short.change);
            const iSym = symRange(s.inst.total.concat(s.inst.foreign, s.inst.trust, s.inst.dealer));
            // 融資餘額警戒/安全線：依該股自身融資餘額分位數動態計算
            const balVals = (s.margin.balance || []).filter(v => v != null);
            let safeVal = null, warnVal = null;
            if (balVals.length >= 8) {{
                const sorted = balVals.slice().sort((a, b) => a - b);
                safeVal = sorted[Math.round(sorted.length * 0.25) - 1];
                warnVal = sorted[Math.round(sorted.length * 0.75) - 1];
            }}
            stockChart = stockChart || echarts.init(document.getElementById('stockChart'), null, {{ devicePixelRatio: Math.max(window.devicePixelRatio || 1, 2) }});
            stockChart.setOption({{
                backgroundColor: 'transparent',
                animation: false,
                legend: {{ data: ['K線', 'MA8', 'MA21', 'MA55', '成交量', '融資增減', '融資餘額', '融券增減', '融券餘額', '外資', '投信', '自營'],
                    top: 0, textStyle: {{ color: '#94a3b8', fontSize: 13 }} }},
                tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }} }},
                axisPointer: {{ link: [{{ xAxisIndex: 'all' }}] }},
                grid: [
                    {{ left: 70, right: 80, top: '1%', height: '34%' }},
                    {{ left: 70, right: 80, top: '36%', height: '13%' }},
                    {{ left: 70, right: 80, top: '50%', height: '16%' }},
                    {{ left: 70, right: 80, top: '67%', height: '16%' }},
                    {{ left: 70, right: 80, top: '84%', height: '14%' }}
                ],
                xAxis: [
                    {{ type: 'category', data: kd, gridIndex: 0, axisLabel: {{ color: '#94a3b8', fontSize: 12 }}, axisLine: {{ lineStyle: {{ color: '#475569' }} }} }},
                    {{ type: 'category', data: kd, gridIndex: 1, axisLabel: {{ show: false }} }},
                    {{ type: 'category', data: kd, gridIndex: 2, axisLabel: {{ show: false }} }},
                    {{ type: 'category', data: kd, gridIndex: 3, axisLabel: {{ show: false }} }},
                    {{ type: 'category', data: kd, gridIndex: 4, axisLabel: {{ color: '#94a3b8', fontSize: 12 }} }}
                ],
                yAxis: [
                    {{ gridIndex: 0, scale: true, axisLabel: {{ color: '#94a3b8', fontSize: 12 }},
                       splitLine: {{ lineStyle: {{ color: 'rgba(255,255,255,0.06)' }} }} }},
                    {{ gridIndex: 1, scale: true, axisLabel: {{ color: '#94a3b8', fontSize: 12 }}, splitLine: {{ show: false }} }},
                    {{ gridIndex: 2, min: mSym[0], max: mSym[1], axisLabel: {{ color: '#94a3b8', fontSize: 12 }}, splitLine: {{ show: false }} }},
                    {{ gridIndex: 2, scale: true, axisLabel: {{ color: '#fbbf24', fontSize: 12 }}, splitLine: {{ show: false }} }},
                    {{ gridIndex: 3, min: sSym[0], max: sSym[1], axisLabel: {{ color: '#94a3b8', fontSize: 12 }}, splitLine: {{ show: false }} }},
                    {{ gridIndex: 3, scale: true, axisLabel: {{ color: '#22d3ee', fontSize: 12 }}, splitLine: {{ show: false }} }},
                    {{ gridIndex: 4, min: iSym[0], max: iSym[1], axisLabel: {{ color: '#94a3b8', fontSize: 12 }}, splitLine: {{ show: false }} }}
                ],
                dataZoom: stockZoomDef,
                series: [
                    {{ name: 'K線', type: 'candlestick', xAxisIndex: 0, yAxisIndex: 0,
                       data: kd.map((_, i) => [s.kline.o[i], s.kline.c[i], s.kline.l[i], s.kline.h[i]]),
                       itemStyle: {{ color: '#ef4444', color0: '#10b981', borderColor: '#ef4444', borderColor0: '#10b981' }} }},
                    {{ name: 'MA8', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: calcMA(s.kline.c, 8),
                       showSymbol: false, sampling: 'lttb', lineStyle: {{ width: 1.2, color: '#f59e0b' }} }},
                    {{ name: 'MA21', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: calcMA(s.kline.c, 21),
                       showSymbol: false, sampling: 'lttb', lineStyle: {{ width: 1.2, color: '#60a5fa' }} }},
                    {{ name: 'MA55', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: calcMA(s.kline.c, 55),
                       showSymbol: false, sampling: 'lttb', lineStyle: {{ width: 1.2, color: '#ec4899' }} }},
                    {{ name: '成交量', type: 'bar', xAxisIndex: 1, yAxisIndex: 1,
                       data: kd.map((_, i) => ({{ value: s.kline.v[i], itemStyle: {{ color: s.kline.c[i] >= s.kline.o[i] ? '#ef4444' : '#10b981' }} }})),
                       barMaxWidth: 12 }},
                    {{ name: '融資增減', type: 'bar', xAxisIndex: 2, yAxisIndex: 2,
                       data: s.margin.change.map(v => ({{ value: v, itemStyle: {{ color: v == null ? 'rgba(0,0,0,0)' : (v >= 0 ? '#ef4444' : '#10b981') }} }})),
                       barMaxWidth: 14 }},
                    {{ name: '融資餘額', type: 'line', xAxisIndex: 2, yAxisIndex: 3, data: s.margin.balance,
                       showSymbol: false, sampling: 'lttb', lineStyle: {{ width: 1, color: '#fbbf24' }},
                       markLine: safeVal == null ? undefined : {{
                           symbol: 'none', silent: true,
                           label: {{ show: true, fontSize: 10, color: '#e2e8f0', formatter: '{{b}}' }},
                           data: [
                               {{ name: '警戒線', yAxis: warnVal, lineStyle: {{ color: '#f97316', width: 1, type: 'dashed' }},
                                  label: {{ color: '#f97316', formatter: '餘額警戒(75分位)', fontSize: 10 }} }},
                               {{ name: '安全線', yAxis: safeVal, lineStyle: {{ color: '#10b981', width: 1, type: 'dashed' }},
                                  label: {{ color: '#10b981', formatter: '餘額安全(25分位)', fontSize: 10 }} }}
                           ]
                       }},
                       markArea: safeVal == null ? undefined : {{
                           silent: true,
                           label: {{ show: false }},
                           data: [
                               [{{ yAxis: warnVal, itemStyle: {{ color: 'rgba(239,68,68,0.10)' }} }}, {{ yAxis: 'max' }}],
                               [{{ yAxis: 'min', itemStyle: {{ color: 'rgba(16,185,129,0.08)' }} }}, {{ yAxis: safeVal }}]
                           ]
                       }} }},
                    {{ name: '融券增減', type: 'bar', xAxisIndex: 3, yAxisIndex: 4,
                       data: s.short.change.map(v => ({{ value: v, itemStyle: {{ color: v == null ? 'rgba(0,0,0,0)' : (v >= 0 ? '#ef4444' : '#10b981') }} }})),
                       barMaxWidth: 14 }},
                    {{ name: '融券餘額', type: 'line', xAxisIndex: 3, yAxisIndex: 5, data: s.short.balance,
                       showSymbol: false, sampling: 'lttb', lineStyle: {{ width: 1, color: '#22d3ee' }} }},
                    {{ name: '外資', type: 'bar', xAxisIndex: 4, yAxisIndex: 6, data: s.inst.foreign, barMaxWidth: 10, itemStyle: {{ color: '#60a5fa' }} }},
                    {{ name: '投信', type: 'bar', xAxisIndex: 4, yAxisIndex: 6, data: s.inst.trust, barMaxWidth: 10, itemStyle: {{ color: '#34d399' }} }},
                    {{ name: '自營', type: 'bar', xAxisIndex: 4, yAxisIndex: 6, data: s.inst.dealer, barMaxWidth: 10, itemStyle: {{ color: '#a78bfa' }} }}
                ]
            }}, true);
            setTooltip('stock', document.getElementById('stockTipSel').value);
            renderTdccCard(code, s);
        }}

        function renderStock(code) {{
            renderCats(code);
            const s = chartPayload.stocks && chartPayload.stocks[code];
            if (!s || !s.kline.dates.length) return;
            drawStock(s, code);
        }}

        // ---------- 千張大戶資訊卡（集保每週資料，內嵌 tdccData） ----------
        function marginTrend(bal) {{
            const vals = (bal || []).filter(v => v != null && v > 0);
            if (vals.length < 8) return null;  // 樣本不足
            const a = vals.slice(-5), b = vals.slice(-10, -5);
            const avg = arr => arr.reduce((x, y) => x + y, 0) / arr.length;
            if (avg(b) <= 0) return null;
            const r = avg(a) / avg(b);
            return r > 1.02 ? '上升' : (r < 0.98 ? '下降' : '平');
        }}

        function renderTdccCard(code, s) {{
            const box = document.getElementById('tdccCard');
            if (!box) return;
            const cur = tdccData && tdccData.cur ? tdccData.cur[code] : null;
            if (cur == null) {{
                box.innerHTML = '<div class="tdcc-card tdcc-title">千張大戶持股：集保查無此代號（或非上市櫃個股）</div>';
                return;
            }}
            const prev = tdccData.prev ? tdccData.prev[code] : null;
            const week = tdccData.week || '';
            const delta = prev != null ? Math.round((cur - prev) * 100) / 100 : null;
            const conc = cur >= 60 ? '高' : (cur >= 40 ? '中' : '低');
            const mt = marginTrend(s && s.margin ? s.margin.balance : null);
            const upDown = cl => '<em class="' + cl + '">' + cl + '</em>';

            let dir = '', dirCls = 'flat', dirTxt = '持平';
            if (delta != null) {{
                if (delta >= 0.10) {{ dir = 'up'; dirTxt = '大戶增持'; }}
                else if (delta <= -0.10) {{ dir = 'down'; dirTxt = '大戶減持'; }}
            }}
            dirCls = dir || 'flat';

            let read = '';
            if (delta == null) {{
                read = '僅有本週資料，當週增減需待下週集保更新後比對。';
            }} else {{
                const up = delta >= 0.10, down = delta <= -0.10;
                if (up && (mt === '下降' || mt === '平' || mt === null)) {{
                    read = '<b>千張占比上升</b>、融資餘額' + (mt === '下降' ? '滑落' : (mt === '平' ? '持穩' : '資料不足')) + ' → 籌碼往大戶集中、散戶槓桿減輕，屬<b>鎖碼/換手跡象</b>（籌碼面偏多）。';
                }} else if (up && mt === '上升') {{
                    read = '<b>千張占比與融資餘額同步上升</b> → 大戶與散戶同步做多；若股價未跟漲，需留意大戶<b>融資鎖碼</b>的高槓桿風險。';
                }} else if (down && mt === '上升') {{
                    read = '<b>千張占比下滑、融資餘額上升</b> → 大戶減碼、散戶接刀，典型的<b>大戶倒貨風險</b>（籌碼面轉差）。';
                }} else if (down && (mt === '下降' || mt === '平' || mt === null)) {{
                    read = '<b>千張占比與融資同步下滑</b> → 大戶與散戶同步撤出，觀察是否為落底前的清洗，不宜急於進場。';
                }} else if (mt === '上升') {{
                    read = '千張占比持平、<b>融資餘額上升</b> → 大戶未增持但散戶槓桿增加，籌碼略鬆散，追高風險偏高。';
                }} else if (mt === '下降') {{
                    read = '千張占比持平、<b>融資餘額下降</b> → 散戶槓桿減輕、籌碼趨穩。';
                }} else {{
                    read = '千張占比持平；融資樣本不足，建議以日頻籌碼數據輔助判讀。';
                }}
            }}

            box.innerHTML =
                '<div class="tdcc-card">' +
                '<div class="tdcc-title">千張大戶持股<span class="wk">集保每週結算 · ' + week + '</span></div>' +
                '<div class="tdcc-stats">' +
                '<div class="tdcc-stat"><span>千張占比</span><b>' + cur.toFixed(2) + '%</b>' +
                (delta == null ? '' : '<em class="' + dirCls + '">' + (delta >= 0 ? '+' : '') + delta.toFixed(2) + 'pp</em>') + '</div>' +
                '<div class="tdcc-stat"><span>大戶動向</span><b style="color:' + (dir === 'up' ? '#ef4444' : (dir === 'down' ? '#10b981' : '#94a3b8')) + '">' + dirTxt + '</b></div>' +
                '<div class="tdcc-stat"><span>集中度</span><b>' + conc + '</b></div>' +
                '<div class="tdcc-stat"><span>融資趨勢(近5日)</span><b>' + (mt || '資料不足') + '</b></div>' +
                '</div>' +
                '<div class="tdcc-read">解讀：' + read + '</div>' +
                '<div class="tdcc-warn">註：千張大戶含外資保管機構與公司派，為週頻落後指標，非即時訊號；請搭配上方融資分位線與日頻法人動向判讀。</div>' +
                '</div>';
        }}

        let currentTabId = 'tab-kline';

        function switchTab(id, btn, opts) {{
            const el = document.getElementById(id);
            if (!el) return;
            if (currentTabId === id && el.classList.contains('active')) {{
                if (btn) {{
                    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                }}
                return;
            }}
            document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            el.classList.add('active');
            if (btn) btn.classList.add('active');
            const fromPop = !!(opts && opts.pop);
            if (!fromPop) {{
                const prev = history.state;
                try {{
                    if (prev && prev.tab === id) history.replaceState({{ tab: id }}, '', '#' + id);
                    else history.pushState({{ tab: id }}, '', '#' + id);
                }} catch (e) {{}}
            }}
            currentTabId = id;
            if (id === 'tab-kline') {{
                if (stockChart) stockChart.resize();
                if (!fromPop) {{
                    const sc = document.getElementById('stockChart');
                    if (sc) sc.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                }}
            }}
        }}

        (function initTabs() {{
            const m = location.hash.match(/^#(tab-[a-z]+)/);
            if (m) {{
                const target = m[1];
                const btn = document.querySelector('.tab-btn[data-tab="' + target + '"]');
                if (document.getElementById(target)) switchTab(target, btn, {{ pop: true }});
            }}
            try {{ history.replaceState({{ tab: currentTabId }}, '', location.pathname + location.search + '#' + currentTabId); }} catch (e) {{}}
        }})();

        window.addEventListener('popstate', function (e) {{
            const st = e.state;
            const target = st && st.tab;
            if (!target || !document.getElementById(target)) return;
            const btn = document.querySelector('.tab-btn[data-tab="' + target + '"]');
            switchTab(target, btn, {{ pop: true }});
        }});

        function selectStock(code) {{
            if (stockSel && chartPayload.stocks && chartPayload.stocks[code]) {{
                stockSel.value = code;
                renderStock(code);
                switchTab('tab-kline', document.querySelector('.tab-btn[data-tab="tab-kline"]'));
            }} else if (/^[0-9A-Za-z]{{4,6}}$/.test(code)) {{
                loadLiveStock(code);
            }} else {{
                window.open('https://tw.stock.yahoo.com/quote/' + code + '.TW', '_blank');
            }}
        }}

        // ---------- 任意股即時查詢（純前端直連 TWSE，CORS OK） ----------
        function qMsg(txt, cls) {{
            const el = document.getElementById('stockQueryMsg');
            if (el) {{ el.textContent = txt || ''; el.className = 'q-msg' + (cls ? ' ' + cls : ''); }}
        }}

        async function twseFetch(url, params) {{
            const q = new URLSearchParams(params).toString();
            const r = await fetch(url + '?' + q, {{ headers: {{ 'Accept': 'application/json' }} }});
            if (!r.ok) throw new Error('HTTP ' + r.status);
            return r.json();
        }}

        const sleep = ms => new Promise(r => setTimeout(r, ms));

        function parseNum(v) {{
            const n = parseFloat(String(v == null ? '' : v).replace(/,/g, ''));
            return isNaN(n) ? 0 : n;
        }}

        function rocDate(row) {{
            const p = String(row).split('/');
            if (p.length !== 3) return String(row);
            return (parseInt(p[0]) + 1911) + '-' + p[1].padStart(2, '0') + '-' + p[2].padStart(2, '0');
        }}

        async function fetchLiveKline(code) {{
            // STOCK_DAY 一次回傳一個月（需用西元 8 位數格式才回正確歷史月），抓近 6 個月
            const byDate = {{}};
            let name = null;
            const now = new Date();
            for (let m = 0; m < 6; m++) {{
                const t = new Date(now.getFullYear(), now.getMonth() - m, 1);
                const params = {{ response: 'json', date: t.getFullYear() + String(t.getMonth() + 1).padStart(2, '0') + '01', stockNo: code }};
                const d = await twseFetch('https://www.twse.com.tw/exchangeReport/STOCK_DAY', params);
                if (!d || d.stat !== 'OK') continue;
                if (!name && d.title) {{
                    const parts = String(d.title).trim().split(/\s+/);
                    if (parts.length >= 3) name = parts[2];
                }}
                (d.data || []).forEach(row => {{
                    const date = rocDate(row[0]);
                    byDate[date] = {{
                        o: parseNum(row[3]), h: parseNum(row[4]), l: parseNum(row[5]),
                        c: parseNum(row[6]), v: parseNum(row[1])
                    }};
                }});
            }}
            const dates = Object.keys(byDate).sort();
            return {{
                name: name,
                dates: dates,
                o: dates.map(d => byDate[d].o), h: dates.map(d => byDate[d].h),
                l: dates.map(d => byDate[d].l), c: dates.map(d => byDate[d].c),
                v: dates.map(d => byDate[d].v)
            }};
        }}

        async function fetchLiveMargin(code, dates) {{
            const bal = {{}}, short = {{}};
            let name = null;
            for (const d of dates) {{
                try {{
                    const j = await twseFetch('https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN',
                        {{ response: 'json', date: d.replace(/-/g, ''), selectType: 'ALL' }});
                    const tbl = (j.tables || [])[1];
                    const row = (tbl && tbl.data || []).find(r => String(r[0]).trim() === code);
                    if (row) {{
                        if (!name) name = String(row[1]).trim();
                        bal[d] = parseNum(row[6]);
                        short[d] = parseNum(row[12]);
                    }}
                }} catch (e) {{ /* 單日失敗略過 */ }}
                await sleep(60);
            }}
            return {{ bal: bal, short: short, name: name }};
        }}

        async function fetchLiveInst(code, dates) {{
            const inst = {{}};
            let name = null;
            for (const d of dates) {{
                try {{
                    const j = await twseFetch('https://www.twse.com.tw/fund/T86',
                        {{ response: 'json', date: d.replace(/-/g, ''), selectType: 'ALL' }});
                    const row = (j.data || []).find(r => String(r[0]).trim() === code);
                    if (row) {{
                        if (!name) name = String(row[1]).trim();
                        inst[d] = {{ f: parseNum(row[4]), t: parseNum(row[10]), d2: parseNum(row[11]), tot: parseNum(row[18]) }};
                    }}
                }} catch (e) {{ /* 單日失敗略過 */ }}
                await sleep(60);
            }}
            return {{ data: inst, name: name }};
        }}

        async function loadLiveStock(code) {{
            const btn = document.getElementById('stockQueryBtn');
            if (btn) btn.disabled = true;
            // 先切到 K線頁籤，讓使用者看到查詢進度
            switchTab('tab-kline', document.querySelector('.tab-btn[data-tab="tab-kline"]'));
            qMsg('查詢中…', '');
            try {{
                const k = await fetchLiveKline(code);
                if (!k.dates.length) throw new Error('查無資料，請確認代號');
                const master = k.dates;
                const name0 = k.name || code;
                // 先畫 K 線（籌碼面板留空），立即有圖
                drawStock({{
                    name: name0,
                    kline: {{ dates: master, o: k.o, h: k.h, l: k.l, c: k.c, v: k.v }},
                    margin: {{ dates: master, balance: master.map(() => null), change: master.map(() => null) }},
                    short: {{ dates: master, balance: master.map(() => null), change: master.map(() => null) }},
                    inst: {{ dates: master, foreign: master.map(() => null), trust: master.map(() => null), dealer: master.map(() => null), total: master.map(() => null) }}
                }}, code);
                qMsg('K線完成，抓籌碼中…', '');
                // 取最後 20 個交易日的融資/法人
                const last = master.slice(-20);
                const [mar, inst] = await Promise.all([fetchLiveMargin(code, last), fetchLiveInst(code, last)]);
                const mbal = master.map(d => (d in mar.bal ? mar.bal[d] : null));
                const mchg = master.map((d, i) => (d in mar.bal && i > 0 && master[i - 1] in mar.bal) ? mar.bal[d] - mar.bal[master[i - 1]] : null);
                const sbal = master.map(d => (d in mar.short ? mar.short[d] : null));
                const schg = master.map((d, i) => (d in mar.short && i > 0 && master[i - 1] in mar.short) ? mar.short[d] - mar.short[master[i - 1]] : null);
                const iF = master.map(d => (d in inst.data ? inst.data[d].f : null));
                const iT = master.map(d => (d in inst.data ? inst.data[d].t : null));
                const iD = master.map(d => (d in inst.data ? inst.data[d].d2 : null));
                const iTot = master.map(d => (d in inst.data ? inst.data[d].tot : null));
                const name = mar.name || inst.name || name0;
                const s = {{
                    name: name,
                    kline: {{ dates: master, o: k.o, h: k.h, l: k.l, c: k.c, v: k.v }},
                    margin: {{ dates: master, balance: mbal, change: mchg }},
                    short: {{ dates: master, balance: sbal, change: schg }},
                    inst: {{ dates: master, foreign: iF, trust: iT, dealer: iD, total: iTot }}
                }};
                // 填充摘要卡：融資餘額、融券餘額、法人買賣超最新值 + 資料天數
                const box = document.getElementById('stockCats');
                const mDays = mbal.filter(v => v != null).length;
                const iDays = iTot.filter(v => v != null).length;
                const fmt = v => v == null ? '—' : (v >= 0 ? '+' : '') + Number(v).toLocaleString();
                const lastMBal = mbal.filter(v => v != null).pop();
                const lastSBal = sbal.filter(v => v != null).pop();
                const lastF = iF.filter(v => v != null).pop();
                const lastT = iT.filter(v => v != null).pop();
                const lastD2 = iD.filter(v => v != null).pop();
                const lastTot = iTot.filter(v => v != null).pop();
                const cardHtml = '<div class="stock-info-cards" style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:8px">' +
                    '<div class="card" style="flex:1;min-width:120px"><div class="label">融資餘額</div>' +
                    '<div class="value">' + (lastMBal != null ? Number(lastMBal).toLocaleString() + ' 張' : '無資料') + '</div>' +
                    '<div class="sub">' + mDays + '/' + last.length + ' 日有資料</div></div>' +
                    '<div class="card" style="flex:1;min-width:120px"><div class="label">融券餘額</div>' +
                    '<div class="value">' + (lastSBal != null ? Number(lastSBal).toLocaleString() + ' 張' : '無資料') + '</div>' +
                    '<div class="sub">近' + last.length + ' 日最新值</div></div>' +
                    '<div class="card" style="flex:1;min-width:120px"><div class="label">外資買賣超</div>' +
                    '<div class="value" style="color:' + (lastF == null ? '#94a3b8' : (lastF >= 0 ? '#ef4444' : '#10b981')) + '">' + fmt(lastF) + '</div>' +
                    '<div class="sub">最新交易日</div></div>' +
                    '<div class="card" style="flex:1;min-width:120px"><div class="label">投信買賣超</div>' +
                    '<div class="value" style="color:' + (lastT == null ? '#94a3b8' : (lastT >= 0 ? '#ef4444' : '#10b981')) + '">' + fmt(lastT) + '</div>' +
                    '<div class="sub">最新交易日</div></div>' +
                    '<div class="card" style="flex:1;min-width:120px"><div class="label">自營商買賣超</div>' +
                    '<div class="value" style="color:' + (lastD2 == null ? '#94a3b8' : (lastD2 >= 0 ? '#ef4444' : '#10b981')) + '">' + fmt(lastD2) + '</div>' +
                    '<div class="sub">最新交易日</div></div>' +
                    '<div class="card" style="flex:1;min-width:120px"><div class="label">三大法人合計</div>' +
                    '<div class="value" style="color:' + (lastTot == null ? '#94a3b8' : (lastTot >= 0 ? '#ef4444' : '#10b981')) + '">' + fmt(lastTot) + '</div>' +
                    '<div class="sub">' + iDays + '/' + last.length + ' 日有資料</div></div>' +
                    '</div>';
                if (box) box.innerHTML = cardHtml;
                qMsg(name + '（即時查詢 · 融資' + mDays + '日 法人' + iDays + '日）', 'ok');
                drawStock(s, code);
            }} catch (e) {{
                qMsg('查詢失敗：' + e.message, 'err');
                const box2 = document.getElementById('stockCats');
                if (box2) box2.innerHTML = '';
            }} finally {{
                if (btn) btn.disabled = false;
            }}
        }}

        function queryStock() {{
            const v = document.getElementById('stockQuery').value.trim();
            if (!/^[0-9A-Za-z]{{4,6}}$/.test(v)) {{ qMsg('請輸入 4~6 位代號（如 2330）', 'err'); return; }}
            const code = v.toUpperCase();
            if (chartPayload.stocks && chartPayload.stocks[code]) {{
                selectStock(code);
                qMsg('（看板內建資料）', 'ok');
                return;
            }}
            loadLiveStock(code);
        }}

        const catColors = {{
            '自選': '#60a5fa', '0050': '#818cf8', '警示股': '#ef4444', '融資斷頭': '#f97316',
            '恐慌停損': '#f59e0b', '主力換手': '#10b981', '法人買超前5': '#22d3ee',
            '法人賣超前5': '#a78bfa', '四象限Q1': '#34d399', '四象限Q2': '#f472b6',
            '四象限Q3': '#fbbf24', '四象限Q4': '#94a3b8'
        }};

        function renderCats(code) {{
            const box = document.getElementById('stockCats');
            if (!box) return;
            const cats = (chartPayload.stockCats && chartPayload.stockCats[code]) || [];
            box.innerHTML = '';
            (cats.length ? cats : ['無分類']).forEach(c => {{
                const sp = document.createElement('span');
                sp.className = 'cat-badge';
                const col = catColors[c] || '#94a3b8';
                sp.style.color = col;
                sp.style.borderColor = col;
                sp.style.background = col + '22';
                sp.textContent = c;
                box.appendChild(sp);
            }});
        }}

        const order = chartPayload.stockOrder || [];
        if (order.length > 0 && chartPayload.stocks) {{
            order.forEach(code => {{
                const s = chartPayload.stocks[code];
                const cats = (chartPayload.stockCats && chartPayload.stockCats[code]) || [];
                const opt = document.createElement('option');
                opt.value = code;
                let label = (s && s.name ? s.name + ' ' : '') + code;
                if (cats.length) label += ' [' + cats.join('/') + ']';
                opt.textContent = label;
                stockSel.appendChild(opt);
            }});
            stockSel.value = order[0];
            stockSel.addEventListener('change', () => renderStock(stockSel.value));
            renderStock(stockSel.value);
            window.addEventListener('resize', () => stockChart && stockChart.resize());
        }}

        function copySection(btn) {{
            const text = JSON.parse('"' + btn.dataset.copy + '"');
            const label = btn.textContent;
            const done = () => {{
                btn.classList.add('copied');
                btn.textContent = '✓ 已複製';
                setTimeout(() => {{
                    btn.classList.remove('copied');
                    btn.textContent = label;
                }}, 1500);
            }};
            if (navigator.clipboard && window.isSecureContext) {{
                navigator.clipboard.writeText(text).then(done).catch(() => fallbackCopy(text, done));
            }} else {{
                fallbackCopy(text, done);
            }}
        }}

        function fallbackCopy(text, done) {{
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            try {{ document.execCommand('copy'); }} catch (e) {{}}
            document.body.removeChild(ta);
            done();
        }}
    </script>
</body>
</html>"""

    def _copy_button(self, copy_text, tsv_text):
        payload = html.escape(json.dumps(copy_text)[1:-1])
        tsv_payload = html.escape(json.dumps(tsv_text)[1:-1])
        return (f'<div class="copy-btns">'
                f'<button class="copy-btn" data-copy="{payload}" onclick="copySection(this)">複製清單</button>'
                f'<button class="copy-btn" data-copy="{tsv_payload}" onclick="copySection(this)">複製Excel</button>'
                f'</div>')

    def _tsv_payload(self, text):
        return html.escape(json.dumps(text)[1:-1])

    def _build_bulk_copy_buttons(self, categories):
        """一鍵複製全部分析結果的股號+股名，兩種排列（直行 / 橫列併欄）"""
        nonempty = [(label, [s for s in stocks if s[0]]) for label, stocks in categories]
        nonempty = [(label, stocks) for label, stocks in nonempty if stocks]
        if not nonempty:
            return ""
        # 直行排列：各類別依序往下接續，股號占 A 欄、股名占 B 欄，類別間空一行
        v_lines = []
        for label, stocks in nonempty:
            v_lines.append(label)
            v_lines.extend(f"{code}\t{name}" for code, name in stocks)
            v_lines.append("")
        vertical = "\n".join(v_lines).rstrip("\n")
        # 橫列排列：各類別橫向併欄，每類別占 2 欄（股號+股名）再空 1 欄
        max_rows = max(len(stocks) for _, stocks in nonempty)
        h_rows = ["\t".join(cell for label, _ in nonempty for cell in (label, "", ""))]
        for i in range(max_rows):
            row = []
            for _, stocks in nonempty:
                if i < len(stocks):
                    code, name = stocks[i]
                    row += [code, name, ""]
                else:
                    row += ["", "", ""]
            h_rows.append("\t".join(row))
        horizontal = "\n".join(h_rows)
        return (f'<div class="bulk-copy">'
                f'<span class="bulk-label">一鍵複製全部分析結果（股號+股名）：</span>'
                f'<button class="copy-btn" data-copy="{self._tsv_payload(vertical)}" onclick="copySection(this)">直行排列（A/B 欄往下接續）</button>'
                f'<button class="copy-btn" data-copy="{self._tsv_payload(horizontal)}" onclick="copySection(this)">橫列排列（A/B、D/E 併欄）</button>'
                f'<span class="bulk-note">複製後可直接貼到 Excel（Tab 分隔，各類別間隔一欄/一行）</span>'
                f'</div>')

    def _build_trigger_table(self, stocks, trigger_type):
        if not stocks:
            return '<p style="color:#94a3b8;text-align:center;padding:20px">今日無觸發</p>'
        rows = ""
        copy_lines = []
        tsv_lines = []
        for i, s in enumerate(stocks):
            pct_class = "negative" if s["pct_change"] < 0 else "positive"
            m_class = "negative" if s["margin_change"] < 0 else "positive"
            rate_color = "#ef4444" if s["est_maintenance_rate"] < 135 else ("#f59e0b" if s["est_maintenance_rate"] < 145 else "#10b981")
            cum_class = "negative" if s.get("cum_3d_change", 0) < 0 else "positive"
            copy_lines.append(f"{s['stock_id']} {s['stock_name']} 收盤{s['close']:,.2f} 漲跌幅{s['pct_change']:+.2f}% 3日累計{s.get('cum_3d_change', 0):+.2f}% 融資變動{s['margin_change']:,} 使用率{s['margin_usage_rate']:.1f}% 維持率{s['est_maintenance_rate']:.1f}%")
            tsv_lines.append(f"{s['stock_id']}\t{s['stock_name']}\t{s['close']:.2f}\t{s['pct_change']:.2f}\t{s.get('cum_3d_change', 0):.2f}\t{s['margin_change']}\t{s['margin_usage_rate']:.1f}\t{s['est_maintenance_rate']:.1f}")
            rows += f"""<tr>
                <td>{i+1}</td>
                <td><a href="javascript:void(0)" onclick="selectStock('{s['stock_id']}')" class="stock-id" title="點擊查看 K線+籌碼">{s['stock_id']}</a></td>
                <td><a href="javascript:void(0)" onclick="selectStock('{s['stock_id']}')" class="stock-name" title="點擊查看 K線+籌碼">{s['stock_name']}</a></td>
                <td>{s['close']:,.2f}</td>
                <td class="{pct_class}">{s['pct_change']:+.2f}%</td>
                <td class="{cum_class}">{s.get('cum_3d_change', 0):+.2f}%</td>
                <td class="{m_class}">{s['margin_change']:,}</td>
                <td>{s['margin_usage_rate']:.1f}%</td>
                <td style="color:{rate_color}">{s['est_maintenance_rate']:.1f}%</td>
            </tr>"""
        return f"""<div class="table-header">{self._copy_button(chr(10).join(copy_lines), "代號\t名稱\t收盤價\t漲跌幅\t3日累計\t融資變動\t使用率\t維持率\n" + chr(10).join(tsv_lines))}</div>
        <table>
            <thead><tr>
                <th>#</th><th>代號</th><th>名稱</th><th>收盤價</th>
                <th>漲跌幅</th><th>3日累計</th><th>融資變動</th><th>融資使用率</th><th>維持率</th>
            </tr></thead>
            <tbody>{rows}</tbody>
        </table>"""

    def _build_alerts_table(self, alerts):
        if not alerts:
            return '<p style="color:#94a3b8;text-align:center;padding:40px">今日無符合條件的警示股</p>'
        rows = ""
        copy_lines = []
        tsv_lines = []
        for i, a in enumerate(alerts):
            pct_class = "negative" if a["pct_change"] < 0 else "positive"
            m_class = "negative" if a["margin_change"] < 0 else "positive"
            rate_color = "#ef4444" if a["est_maintenance_rate"] < 135 else ("#f59e0b" if a["est_maintenance_rate"] < 145 else "#10b981")
            badge = "badge-danger" if a["pct_change"] <= -3 else "badge-warning"
            copy_lines.append(f"{a['stock_id']} {a['stock_name']} 收盤{a['close']:,.2f} 跌幅{a['pct_change']:+.2f}% 成交量{a['volume']:,} 融資餘額{a['margin_balance']:,} 融資變動{a['margin_change']:,} 使用率{a['margin_usage_rate']:.1f}% 維持率{a['est_maintenance_rate']:.1f}%")
            tsv_lines.append(f"{a['stock_id']}\t{a['stock_name']}\t{a['close']:.2f}\t{a['pct_change']:.2f}\t{a['volume']}\t{a['margin_balance']}\t{a['margin_change']}\t{a['margin_usage_rate']:.1f}\t{a['est_maintenance_rate']:.1f}")
            rows += f"""<tr>
                <td>{i+1}</td>
                <td><a href="javascript:void(0)" onclick="selectStock('{a['stock_id']}')" class="stock-id" title="點擊查看 K線+籌碼">{a['stock_id']}</a></td>
                <td><a href="javascript:void(0)" onclick="selectStock('{a['stock_id']}')" class="stock-name" title="點擊查看 K線+籌碼">{a['stock_name']}</a></td>
                <td>{a['close']:,.2f}</td>
                <td class="{pct_class}"><span class="badge {badge}">{a['pct_change']:+.2f}%</span></td>
                <td>{a['volume']:,}</td>
                <td>{a['margin_balance']:,}</td>
                <td class="{m_class}">{a['margin_change']:,}</td>
                <td>{a['margin_usage_rate']:.1f}%</td>
                <td style="color:{rate_color}">{a['est_maintenance_rate']:.1f}%</td>
            </tr>"""
        return f"""<div style="overflow-x:auto">
        <div class="table-header">{self._copy_button(chr(10).join(copy_lines), "代號\t名稱\t收盤價\t跌幅\t成交量\t融資餘額\t融資變動\t使用率\t維持率\n" + chr(10).join(tsv_lines))}</div>
        <table>
            <thead><tr>
                <th>#</th><th>代號</th><th>名稱</th><th>收盤價</th>
                <th>跌幅</th><th>成交量</th><th>融資餘額</th><th>融資變動</th><th>使用率</th><th>維持率</th>
            </tr></thead>
            <tbody>{rows}</tbody>
        </table></div>"""

    def _build_quadrant_html(self, quadrant):
        """四象限區塊 HTML"""
        if not quadrant or not quadrant.get("market"):
            return ""
        qm = quadrant["market"]
        counts = quadrant.get("counts", {})
        quads = quadrant.get("quadrants", {})

        html = f"""
        <h3 class="panel-title">四象限精準定位（價 × 資）</h3>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px">
            <span class="quad-legend" style="color:#ef4444;border-color:#ef4444">Q1 警訊 · 資增價跌（散戶攤平，觀望）</span>
            <span class="quad-legend" style="color:#10b981;border-color:#10b981">Q2 多頭 · 資減價漲（籌碼轉佳）</span>
            <span class="quad-legend" style="color:#f59e0b;border-color:#f59e0b">Q3 波段末端 · 資增價漲（散戶追高）</span>
            <span class="quad-legend" style="color:#60a5fa;border-color:#60a5fa">Q4 打底 · 資減價跌（等落底）</span>
        </div>
        <div class="quad-market" style="border-color:{qm['color']}">
            <div class="qm-title" style="color:{qm['color']}">大盤狀態：{qm['label']}</div>
            <div class="qm-desc">指數 {qm['index_pct']:+.2f}% ｜ 大盤融資 {qm['margin_change']:+,} 張</div>
            <div class="qm-advice" style="color:{qm['color']}">操作建議：{qm['advice']}</div>
        </div>
        <div class="quad-grid">
        """

        from src.advanced_data import QUADRANT_INFO
        for qkey in ["Q1", "Q2", "Q3", "Q4"]:
            info = QUADRANT_INFO[qkey]
            qlist = quads.get(qkey, [])
            chips = ""
            for s in qlist[:8]:
                pct_cls = "positive" if s["pct"] >= 0 else "negative"
                m_cls = "positive" if s["margin_change"] >= 0 else "negative"
                chips += (f'<span class="stock-chip" onclick="selectStock(\'{s["code"]}\')">'
                          f'<span class="sc-code">{s["code"]}</span>{s["name"]} '
                          f'<span class="sc-pct {pct_cls}">{s["pct"]:+.1f}%</span> '
                          f'<span class="{m_cls}">資{s["margin_change"]:+,}</span></span>')
            if not chips:
                chips = '<div style="color:#64748b;font-size:0.85em">今日無此類型個股</div>'
            html += f"""
            <div class="quad-box" style="border-top:3px solid {info['color']}">
                <div class="qb-head">
                    <span class="qb-label" style="color:{info['color']}">{info['emoji']} {info['label']}</span>
                    <span class="qb-count" style="color:{info['color']}">{counts.get(info['label'], 0)}</span>
                </div>
                <div class="qb-desc">{info['desc']}｜{info['advice']}</div>
                <div>{chips}</div>
            </div>
            """
        html += "</div>"
        return html

    def _build_institutional_table(self, stocks, title, direction):
        if not stocks:
            return f'<p style="color:#94a3b8;text-align:center;padding:20px">今日無{title}</p>'
        
        rows = ""
        copy_lines = []
        tsv_lines = []
        for i, s in enumerate(stocks):
            code = s.get("code", "")
            name = s.get("name", "")
            foreign_net = s.get("foreign_net", 0)
            trust_net = s.get("trust_net", 0)
            dealer_net = s.get("dealer_net", 0)
            total_net = s.get("total_net", 0)
            
            copy_lines.append(f"{code} {name} 外陸資{foreign_net:+,} 投信{trust_net:+,} 自營商{dealer_net:+,} 合計{total_net:+,}")
            tsv_lines.append(f"{code}\t{name}\t{foreign_net}\t{trust_net}\t{dealer_net}\t{total_net}")
            
            def fmt_net(val):
                cls = "positive" if val > 0 else ("negative" if val < 0 else "neutral")
                return f'<td class="{cls}">{val:+,}</td>'
            
            rows += f"""<tr>
                <td>{i+1}</td>
                <td><a href="javascript:void(0)" onclick="selectStock('{code}')" class="stock-id" title="點擊查看 K線+籌碼">{code}</a></td>
                <td><a href="javascript:void(0)" onclick="selectStock('{code}')" class="stock-name" title="點擊查看 K線+籌碼">{name}</a></td>
                {fmt_net(foreign_net)}
                {fmt_net(trust_net)}
                {fmt_net(dealer_net)}
                {fmt_net(total_net)}
            </tr>"""
        
        return f"""<div class="table-header"><h3 style="color:{'#10b981' if direction == 'buy' else '#ef4444'}; margin: 0; font-size: 1em;">{title}</h3>{self._copy_button(chr(10).join(copy_lines), "代號\t名稱\t外陸資\t投信\t自營商\t合計\n" + chr(10).join(tsv_lines))}</div>
        <table>
            <thead><tr>
                <th>#</th><th>代號</th><th>名稱</th>
                <th>外陸資</th><th>投信</th><th>自營商</th><th>合計</th>
            </tr></thead>
            <tbody>{rows}</tbody>
        </table>"""
