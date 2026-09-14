"""
通知模組 v2 - 支援新格式 (name + user_id/email)
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests


class LineNotifier:
    def __init__(self, config):
        self.enabled = config.get("enabled", False)
        self.token = config.get("channel_access_token", "")
        self.user_ids = config.get("user_ids", [])
        self.api_url = "https://api.line.me/v2/bot/message/push"

    def send(self, message, dashboard_url="", history_url=""):
        if not self.enabled or not self.token:
            print("  [LINE] 未啟用，跳過")
            return False
        
        full_message = message
        if dashboard_url:
            full_message += f"\n\n看板連結:\n{dashboard_url}"
        if history_url:
            full_message += f"\n歷史紀錄:\n{history_url}"
        
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {self.token}"}
        success = True
        
        for user in self.user_ids:
            uid = user.get("user_id", "") if isinstance(user, dict) else user
            name = user.get("name", "") if isinstance(user, dict) else ""
            if not uid:
                continue
            
            payload = {"to": uid, "messages": [{"type": "text", "text": full_message}]}
            try:
                resp = requests.post(self.api_url, headers=headers, json=payload, timeout=10)
                if resp.status_code == 200:
                    print(f"  [LINE] 已發送給 {name or uid[:8]}")
                else:
                    print(f"  [LINE] 發送失敗: {resp.status_code}")
                    success = False
            except Exception as e:
                print(f"  [LINE] 錯誤: {e}")
                success = False
        return success

    def build_message(self, analysis_result):
        market = analysis_result.get("market_summary", {})
        alerts = analysis_result.get("alerts")
        date = market.get("date", "")
        idx_today = market.get("index_today", 0)
        idx_change = market.get("index_change", 0)
        idx_pct = market.get("index_change_pct", 0)
        margin_change = market.get("margin_change_total", 0)
        arrow = "↑" if idx_change >= 0 else "↓"
        margin_arrow = "↑" if margin_change >= 0 else "↓"
        
        # 三大法人資料
        institutional = analysis_result.get("institutional_summary", {})
        foreign_net = institutional.get("foreign_net", 0)
        trust_net = institutional.get("trust_net", 0)
        dealer_net = institutional.get("dealer_net", 0)
        total_inst_net = institutional.get("total_net", 0)
        
        inst_arrow_f = "↑" if foreign_net >= 0 else "↓"
        inst_arrow_t = "↑" if trust_net >= 0 else "↓"
        inst_arrow_d = "↑" if dealer_net >= 0 else "↓"
        inst_arrow_all = "↑" if total_inst_net >= 0 else "↓"
        
        msg = f"台股融資券分析 {date}\n"
        msg += f"{'='*30}\n"
        msg += f"加權指數: {idx_today:,.0f} {arrow}{abs(idx_pct):.2f}%\n"
        msg += f"融資增減: {margin_arrow}{abs(margin_change):,.0f}張\n"
        msg += f"{'='*30}\n"

        # 四象限狀態
        quadrant = analysis_result.get("quadrant", {})
        qmarket = quadrant.get("market")
        if qmarket:
            msg += f"\n【大盤四象限】{qmarket['label']}\n"
            msg += f"建議: {qmarket['advice']}\n"
        
        # 三大法人買賣超
        if total_inst_net != 0:
            msg += f"\n【三大法人買賣超】\n"
            msg += f"外陸資: {inst_arrow_f}{abs(foreign_net):,}股\n"
            msg += f"投  信: {inst_arrow_t}{abs(trust_net):,}股\n"
            msg += f"自營商: {inst_arrow_d}{abs(dealer_net):,}股\n"
            msg += f"合  計: {inst_arrow_all}{abs(total_inst_net):,}股\n"
        
        alert_count = len(alerts) if alerts is not None and not alerts.empty else 0
        msg += f"\n今日警示股: {alert_count} 檔\n"
        
        if alerts is not None and not alerts.empty:
            msg += "\n【警示股 TOP 5】\n"
            for i, (_, row) in enumerate(alerts.head(5).iterrows()):
                msg += f"{i+1}. {row.get('stock_id','')} {row.get('stock_name','')} "
                msg += f"跌幅{row.get('pct_change',0):+.1f}% 融資{row.get('margin_change',0):+,}張\n"
        return msg


class EmailNotifier:
    def __init__(self, config):
        self.enabled = config.get("enabled", False)
        self.smtp_server = config.get("smtp_server", "smtp.gmail.com")
        self.smtp_port = config.get("smtp_port", 587)
        self.sender_email = config.get("sender_email", "")
        self.sender_password = config.get("sender_password", "")
        self.recipients = config.get("recipients", [])

    def send(self, subject, html_content):
        if not self.enabled or not self.sender_email:
            print("  [Email] 未啟用，跳過")
            return False
        
        # 支援新格式 (name + email) 和舊格式 (string)
        email_list = []
        for r in self.recipients:
            if isinstance(r, dict):
                email_list.append(r.get("email", ""))
            else:
                email_list.append(r)
        email_list = [e for e in email_list if e]
        
        if not email_list:
            print("  [Email] 無收件者")
            return False
        
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.sender_email
        msg["To"] = ", ".join(email_list)
        msg.attach(MIMEText(html_content, "html", "utf-8"))
        
        try:
            server = smtplib.SMTP(self.smtp_server, self.smtp_port)
            server.starttls()
            server.login(self.sender_email, self.sender_password)
            server.sendmail(self.sender_email, email_list, msg.as_string())
            server.quit()
            print(f"  [Email] 已發送給 {len(email_list)} 位")
            return True
        except Exception as e:
            print(f"  [Email] 錯誤: {e}")
            return False

    def build_html(self, analysis_result, dashboard_url="", history_url=""):
        market = analysis_result.get("market_summary", {})
        alerts = analysis_result.get("alerts")
        date = market.get("date", "")
        idx_today = market.get("index_today", 0)
        idx_change = market.get("index_change", 0)
        idx_pct = market.get("index_change_pct", 0)
        arrow = "▲" if idx_change >= 0 else "▼"
        color = "#10b981" if idx_change >= 0 else "#ef4444"
        alert_count = len(alerts) if alerts is not None and not alerts.empty else 0
        
        # 三大法人資料
        institutional = analysis_result.get("institutional_summary", {})
        foreign_net = institutional.get("foreign_net", 0)
        trust_net = institutional.get("trust_net", 0)
        dealer_net = institutional.get("dealer_net", 0)
        total_inst_net = institutional.get("total_net", 0)
        
        def fmt_inst(val):
            c = "#10b981" if val > 0 else ("#ef4444" if val < 0 else "#94a3b8")
            return f'<span style="color:{c}">{val:+,}</span>'

        # 四象限狀態
        quadrant_html = ""
        qmarket = analysis_result.get("quadrant", {}).get("market")
        if qmarket:
            quadrant_html = f"""<div style="background:#1e293b;border-radius:12px;padding:16px;margin:16px 0;border-left:4px solid {qmarket['color']}">
<h3 style="color:{qmarket['color']}">大盤四象限｜{qmarket['label']}</h3>
<div style="color:#94a3b8;margin-top:6px;font-size:14px">指數 {qmarket['index_pct']:+.2f}% ｜ 融資 {qmarket['margin_change']:+,} 張</div>
<div style="color:#e2e8f0;margin-top:6px;font-size:14px">操作建議：{qmarket['advice']}</div>
</div>"""
        
        inst_html = ""
        if total_inst_net != 0:
            inst_html = f"""<div style="background:#1e293b;border-radius:12px;padding:16px;margin:16px 0">
<h3 style="color:#10b981">三大法人買賣超</h3>
<table style="width:100%;border-collapse:collapse;font-size:14px;margin-top:10px">
<tr style="background:#334155"><th>外陸資</th><th>投信</th><th>自營商</th><th>合計</th></tr>
<tr><td style="text-align:center">{fmt_inst(foreign_net)}</td><td style="text-align:center">{fmt_inst(trust_net)}</td><td style="text-align:center">{fmt_inst(dealer_net)}</td><td style="text-align:center">{fmt_inst(total_inst_net)}</td></tr>
</table>
</div>"""
        
        rows_html = ""
        if alerts is not None and not alerts.empty:
            for i, (_, row) in enumerate(alerts.head(10).iterrows()):
                pct = row.get("pct_change", 0)
                m_chg = row.get("margin_change", 0)
                pct_color = "#ef4444" if pct < 0 else "#10b981"
                m_color = "#ef4444" if m_chg < 0 else "#10b981"
                rows_html += f"""<tr>
                    <td>{i+1}</td>
                    <td><b>{row.get('stock_id','')}</b></td>
                    <td>{row.get('stock_name','')}</td>
                    <td>{row.get('close',0):,.1f}</td>
                    <td style="color:{pct_color}">{pct:+.2f}%</td>
                    <td style="color:{m_color}">{m_chg:,}張</td>
                </tr>"""
        
        return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="font-family:'Microsoft JhengHei',sans-serif;background:#0f172a;color:#e2e8f0;padding:20px">
<div style="max-width:600px;margin:0 auto">
<h1 style="color:#60a5fa;text-align:center">台股融資券分析 - {date}</h1>
<div style="background:#1e293b;border-radius:12px;padding:20px;margin:16px 0;text-align:center">
<div style="font-size:32px;font-weight:700;color:{color}">{idx_today:,.0f}</div>
<div style="color:{color}">{arrow} {abs(idx_change):,.0f} ({idx_pct:+.2f}%)</div>
</div>
{quadrant_html}
{inst_html}
<div style="background:#1e293b;border-radius:12px;padding:16px;margin:16px 0">
<h3 style="color:#f59e0b">警示股 ({alert_count} 檔)</h3>
<table style="width:100%;border-collapse:collapse;font-size:14px">
<tr style="background:#334155"><th>#</th><th>代號</th><th>名稱</th><th>收盤</th><th>跌幅</th><th>融資變動</th></tr>
{rows_html}
</table>
</div>
{f'<a href="{dashboard_url}" style="display:block;text-align:center;background:#3b82f6;color:white;padding:12px;border-radius:8px;text-decoration:none;margin:16px 0">查看完整看板</a>' if dashboard_url else ''}
{f'<a href="{history_url}" style="display:block;text-align:center;background:#475569;color:white;padding:10px;border-radius:8px;text-decoration:none;margin:8px 0">歷史紀錄查詢</a>' if history_url else ''}
<p style="text-align:center;color:#64748b;font-size:12px">胚騰 AI Agent | 每日自動更新</p>
</div></body></html>"""
