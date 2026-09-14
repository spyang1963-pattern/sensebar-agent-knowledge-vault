"""
台股融資券分析看板 - 主流程 v3
每日 18:00 自動執行，產生分析看板 + 通知
使用本地 CSV 快取比對融資增減（免費方案）
"""
import os
import sys
import yaml
import pandas as pd
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.twse_fetcher import TWSEFetcher
from src.analyzer import StockAnalyzer
from src.generate_dashboard import DashboardGenerator
from src.notifier import LineNotifier, EmailNotifier
from src.margin_cache import load_cache, save_today, compute_margin_changes, get_cache_info
from src.institutional_fetcher import fetch_institutional_data


def load_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def find_last_trading_day(fetcher, max_days=7):
    """往前找最近一個有資料的交易日，同時抓取資料"""
    # 先嘗試不帶日期，API 會回傳最新可用資料
    print("  嘗試抓取最新可用資料...")
    margin, actual_date = fetcher.fetch_margin_data_twse()
    if margin is not None and not margin.empty and actual_date:
        print(f"  找到最新交易日: {actual_date}")
        return actual_date, margin
    
    # 如果失敗，嘗試其他日期
    today = datetime.now()
    for i in range(max_days):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        print(f"  嘗試 {d} ...")
        margin, actual_date = fetcher.fetch_margin_data_twse(d)
        if margin is not None and not margin.empty:
            print(f"  找到交易日: {actual_date or d}")
            return actual_date or d, margin
        import time
        time.sleep(1)
    return None, None


def main():
    print("=" * 60)
    print("  台股融資券分析看板 v3 - 開始執行")
    print(f"  時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    config = load_config()
    analysis_config = config.get("analysis", {})
    output_config = analysis_config.get("output", {})
    dashboard_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), output_config.get("dashboard_dir", "output/dashboard"))
    os.makedirs(dashboard_dir, exist_ok=True)

    fetcher = TWSEFetcher()
    analyzer = StockAnalyzer(config.get("analysis", {}))
    generator = DashboardGenerator(dashboard_dir)
    line = LineNotifier(config.get("channels", {}).get("line", {}))
    email = EmailNotifier(config.get("channels", {}).get("email", {}))
    fetch_only = "--fetch-only" in sys.argv
    if fetch_only:
        print("[MODE] --fetch-only：只抓資料寫 cache，跳過看板/通知/部署")

    # === Step 1: 找最近交易日 ===
    print("\n[Step 1] 尋找最近交易日...")
    # --date YYYY-MM-DD：指定交易日重產（補歷史看板用）
    specified_date = None
    if "--date" in sys.argv:
        di = sys.argv.index("--date")
        if di + 1 < len(sys.argv):
            specified_date = sys.argv[di + 1]
            try:
                datetime.strptime(specified_date, "%Y-%m-%d")
            except ValueError:
                print(f"  [ERROR] 無效日期格式: {specified_date}，需為 YYYY-MM-DD")
                return None
            print(f"  指定交易日: {specified_date}")

    if specified_date:
        margin, actual_date = fetcher.fetch_margin_data_twse(specified_date)
        if margin is not None and not margin.empty:
            trading_day = actual_date or specified_date
            margin_today = margin
        else:
            print(f"  [ERROR] 指定日期 {specified_date} 無融資券資料")
            return None
    else:
        trading_day, margin_today = find_last_trading_day(fetcher)
    
    # 如果找不到新的交易日，使用快取資料
    use_cache_only = False
    if trading_day is None:
        print("  [WARNING] TWSE 尚無最新資料，使用本地快取...")
        use_cache_only = True
        cache_info = get_cache_info()
        if cache_info.get("最新日期"):
            trading_day = cache_info["最新日期"]
            print(f"  使用快取日期: {trading_day}")
        else:
            print("  [ERROR] 無快取資料可供使用！")
            return None

    # === Step 2: 處理融資融券資料 ===
    print(f"\n[Step 2] 處理 {trading_day} 的融資融券...")
    import time
    
    # 如果 Step 1 沒有抓到資料，嘗試從快取載入
    if margin_today is None or margin_today.empty:
        if use_cache_only:
            print("  使用快取資料生成看板...")
        else:
            # 嘗試從快取載入 (70 天窗口：--date 重產舊日期時仍能找到該日資料)
            cache = load_cache(max_days=70)
            cache_for_today = [r for r in cache if r["date"] == trading_day]
            if cache_for_today:
                margin_today = pd.DataFrame(cache_for_today)
                for col in ["margin_balance", "short_balance"]:
                    if col in margin_today.columns:
                        margin_today[col] = pd.to_numeric(margin_today[col], errors="coerce").fillna(0).astype(int)
                print(f"  從快取載入 {len(margin_today)} 檔融資資料")
            else:
                print("  [ERROR] 無法取得融資資料！")
                return None

    # === Step 3: 抓今日股價 ===
    print("\n[Step 3] 抓取今日股價...")
    prices_today = fetcher.fetch_stock_prices(trading_day)

    if prices_today.empty:
        print("  今日股價尚未公佈，嘗試抓取前一個交易日股價...")
        dt = datetime.strptime(trading_day, "%Y-%m-%d")
        for i in range(1, 5):
            d = (dt - timedelta(days=i)).strftime("%Y-%m-%d")
            prices_today = fetcher.fetch_stock_prices(d)
            if not prices_today.empty:
                print(f"  使用 {d} 的股價資料")
                break
            time.sleep(0.5)

    time.sleep(0.5)

    # === Step 4: 存入 CSV 快取 + 載入歷史 ===
    print("\n[Step 4] 管理本地快取...")
    cache_info = get_cache_info()
    print(f"  {cache_info['raw']}")

    # 只有在有新資料時才存入快取
    if not use_cache_only and margin_today is not None and not margin_today.empty:
        margin_records = []
        for _, row in margin_today.iterrows():
            margin_records.append({
                "stock_id": str(row.get("stock_id", "")),
                "stock_name": str(row.get("stock_name", "")),
                "margin_balance": int(row.get("margin_balance", 0)),
                "short_balance": int(row.get("short_balance", 0)),
            })
        save_today(margin_records, trading_day)

    # 載入歷史快取 (70 天：確保重產舊日期時 prev_date 比對資料仍在窗口內)
    cache = load_cache(max_days=70)
    print(f"  快取已載入: {len(cache)} 筆")

    # 從快取建立「昨天」的 DataFrame 給 analyzer 用
    all_dates = sorted(set(r["date"] for r in cache))
    prev_date = None
    for d in reversed(all_dates):
        if d < trading_day:
            prev_date = d
            break

    if prev_date:
        print(f"  比對日期: {trading_day} vs {prev_date}")
        prev_rows = [r for r in cache if r["date"] == prev_date]
        yesterday_margin = pd.DataFrame(prev_rows)
        # 確保欄位類型正確
        for col in ["margin_balance", "short_balance"]:
            if col in yesterday_margin.columns:
                yesterday_margin[col] = pd.to_numeric(yesterday_margin[col], errors="coerce").fillna(0).astype(int)
    else:
        print("  [WARNING] 無歷史比對資料，融資增減暫為 0（跑幾天後就有資料了）")
        yesterday_margin = pd.DataFrame()

    # === Step 5: 抓歷史收盤價（計算3天累計漲跌）===
    print("\n[Step 5] 抓取歷史收盤價...")
    price_history = fetcher.fetch_stock_prices_multi_day(trading_day, days=4)

    # === Step 5.5: 抓取三大法人買賣超 ===
    print("\n[Step 5.5] 抓取三大法人買賣超...")
    if specified_date:
        from datetime import datetime as _dt
        institutional_data = fetch_institutional_data(_dt.strptime(specified_date, "%Y-%m-%d"))
    else:
        institutional_data = fetch_institutional_data()
    institutional_summary = {"top_buyers": [], "top_sellers": [], "foreign_net": 0, "trust_net": 0, "dealer_net": 0, "total_net": 0}
    
    if institutional_data:
        print(f"  三大法人資料日期: {institutional_data.get('date', 'N/A')}")
        print(f"  共 {len(institutional_data.get('data', []))} 檔股票")
        
        # 計算三大法人整體淨買超
        data = institutional_data.get("data", [])
        for item in data:
            institutional_summary["foreign_net"] += item.get("foreign_net", 0)
            institutional_summary["trust_net"] += item.get("trust_net", 0)
            institutional_summary["dealer_net"] += item.get("dealer_net", 0)
            institutional_summary["total_net"] += item.get("total_net", 0)
        
        # 取得淨買超前5名和淨賣超前5名
        sorted_by_total = sorted(data, key=lambda x: x.get("total_net", 0), reverse=True)
        institutional_summary["top_buyers"] = sorted_by_total[:5]
        institutional_summary["top_sellers"] = sorted_by_total[-5:]
        
        print(f"  三大法人合計淨買超: {institutional_summary['total_net']:,} 股")
        print(f"  外資: {institutional_summary['foreign_net']:,} 股")
        print(f"  投信: {institutional_summary['trust_net']:,} 股")
        print(f"  自營商: {institutional_summary['dealer_net']:,} 股")
    else:
        print("  [WARNING] 無法取得三大法人資料")

    # === Step 6: 分析資料 ===
    print("\n[Step 6] 分析資料...")
    today_data = {
        "margin": margin_today,
        "prices": prices_today,
        "index": None,
        "date": trading_day,
        "institutional": institutional_data,
        "institutional_summary": institutional_summary,
    }
    yesterday_data = {
        "margin": yesterday_margin,
        "prices": pd.DataFrame(),
        "index": None,
        "date": prev_date or trading_day,
    }
    analysis = analyzer.analyze(today_data, yesterday_data, price_history)
    alerts = analysis["alerts"]
    triggers = analysis["triggers"]
    alert_count = len(alerts) if alerts is not None and not alerts.empty else 0
    print(f"  找到 {alert_count} 檔警示股")
    print(f"  融資斷頭: {len(triggers.get('margin_call', []))} 檔")
    print(f"  恐慌停損: {len(triggers.get('panic_sell', []))} 檔")
    print(f"  主力換手: {len(triggers.get('institutional_buy', []))} 檔")

    # === Step 7: 抓取大盤指數 ===
    print("\n[Step 7] 抓取大盤指數...")
    if specified_date:
        today_index = fetcher.fetch_twse_index_at(specified_date)
    else:
        today_index = fetcher.fetch_twse_index(trading_day)
    analysis["market_summary"]["index_today"] = today_index["index"] if today_index else 0
    analysis["market_summary"]["index_change"] = today_index.get("change", 0) if today_index else 0
    analysis["market_summary"]["index_change_pct"] = today_index.get("pct", 0) if today_index else 0
    
    # 加入三大法人資料到分析結果
    analysis["institutional_summary"] = institutional_summary

    # === Step 8: 抓取指數歷史 ===
    print("\n[Step 8] 抓取指數歷史...")
    index_history = fetcher.fetch_index_history(30)

    # === Step 8.5: 更新歷史資料（融資/法人/大盤）＋建置圖表資料 ===
    print("\n[Step 8.5] 更新歷史資料並建置圖表...")
    if "--skip-history" not in sys.argv:
        from src.advanced_data import HistoryData, build_chart_payload
        hd = HistoryData()
        refreshed = hd.refresh()
        payload = build_chart_payload(config, analysis)
        analysis["chart_payload"] = payload
        analysis["quadrant"] = payload["quadrant"]
        # 以回補資料的真實整體維持率覆蓋舊的簡易估算值
        maint_series = payload["market"].get("maintenance", [])
        valid_maint = [v for v in maint_series if v is not None]
        if valid_maint:
            analysis["market_summary"]["est_maintenance_rate"] = valid_maint[-1]
        print(f"  歷史更新: {'完成' if refreshed else '已是最新'}")
        print(f"  圖表資料: 大盤 {len(payload['market']['dates'])} 日, 個股 {len(payload['stockOrder'])} 檔")
        print(f"  整體維持率: {analysis['market_summary']['est_maintenance_rate']:.2f}%")
    else:
        print("  跳過歷史更新與圖表建置（--skip-history）")

    # fetch-only 也要抓 TDCC（正常流程在 Step 9 產看板時才抓，fetch-only 跳過看板需補抓）
    if fetch_only:
        print("\n[Step 8.6] 抓取千張大戶（TDCC）...")
        try:
            from src.advanced_data import get_tdcc_shareholding
            get_tdcc_shareholding()
        except Exception as e:
            print(f"    [TDCC] 抓取失敗: {e}")

    # === Step 9: 產生看板 ===
    if fetch_only:
        print("\n[Step 9-11] 跳過看板/通知/部署（--fetch-only 模式，資料已寫入 cache）")
        print("=" * 60)
        print("  抓取完成")
        return None
    print("\n[Step 9] 產生看板...")
    dashboard_path = generator.generate(analysis, index_history)
    dashboard_filename = os.path.basename(dashboard_path)
    print(f"  看板路徑: {dashboard_path}")

    # === Step 10: 發送通知 ===
    no_notify = "--no-notify" in sys.argv
    if no_notify:
        print("\n[Step 10] 跳過通知（--no-notify 模式，由 message_scheduler 處理）")
    else:
        print("\n[Step 10] 發送通知...")
        # 使用 GitHub Pages 完整網址（帶日期版本參數跳過 CDN/瀏覽器快取）
        base_url = "https://spyang1963-pattern.github.io/sensebar-agent-knowledge-vault"
        ver = trading_day.replace("-", "")
        dashboard_url = f"{base_url}/{dashboard_filename}?d={ver}"
        history_url = f"{base_url}/history.html?d={ver}"
        line_msg = line.build_message(analysis)
        line.send(line_msg, dashboard_url=dashboard_url, history_url=history_url)
        email_html = email.build_html(analysis, dashboard_url=dashboard_url, history_url=history_url)
        email.send(f"台股融資券分析 {trading_day}", email_html)

    # === Step 11: 推送到 GitHub Pages ===
    print("\n[Step 11] 推送到 GitHub Pages...")
    try:
        from deploy_github import main as deploy
        deploy()
    except Exception as e:
        print(f"  [WARNING] 推送失敗: {e}")

    # === 完成 ===
    print("\n" + "=" * 60)
    print("  執行完成！")
    print(f"  看板路徑: {dashboard_path}")
    print(f"  看板網址: https://spyang1963-pattern.github.io/sensebar-agent-knowledge-vault/")
    print(f"  警示股數: {alert_count}")
    print(f"  融資斷頭: {len(triggers.get('margin_call', []))} 檔")
    print(f"  恐慌停損: {len(triggers.get('panic_sell', []))} 檔")
    print(f"  主力換手: {len(triggers.get('institutional_buy', []))} 檔")
    if institutional_summary["total_net"] != 0:
        print(f"  三大法人淨買超: {institutional_summary['total_net']:,} 股")
        print(f"    外資: {institutional_summary['foreign_net']:,} 股")
        print(f"    投信: {institutional_summary['trust_net']:,} 股")
        print(f"    自營商: {institutional_summary['dealer_net']:,} 股")
    print(f"  {get_cache_info()}")
    print("=" * 60)
    # 明確標記：讓 scheduler 判斷是否有今日資料
    print(f"DATA_DATE:{trading_day}")
    print(f"ALERT_COUNT:{alert_count}")
    print(f"MARGIN_CALL:{len(triggers.get('margin_call', []))}")
    print(f"PANIC_SELL:{len(triggers.get('panic_sell', []))}")
    print(f"INSTITUTIONAL_BUY:{len(triggers.get('institutional_buy', []))}")
    qm = analysis.get("quadrant", {}).get("market")
    if qm:
        print(f"QUADRANT:{qm['code']}|{qm['label']}|{qm['advice']}")
    return dashboard_path


if __name__ == "__main__":
    main()
