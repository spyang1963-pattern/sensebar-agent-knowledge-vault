# futures_fetcher.py
"""
期貨即時行情模組
抓取 TAIFEX 期貨即時行情（含日盤、夜盤）
"""
import requests
import json
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

TAIFEX_API_URL = "https://mis.taifex.com.tw/futures/api/getQuoteList"

# 常用期貨代碼
FUTURES_SYMBOLS = {
    # 台指期
    "TX": {"name": "台指期", "type": "index"},
    "MTX": {"name": "小台", "type": "index"},
    "TE": {"name": "電子期", "type": "index"},
    "TF": {"name": "金融期", "type": "index"},
    # 個股期貨
    "CD": {"name": "台積電期", "type": "stock", "stock_code": "2330"},
    "CC": {"name": "聯電期", "type": "stock", "stock_code": "2303"},
    "NF": {"name": "鴻海期", "type": "stock", "stock_code": "2317"},
    "SQ": {"name": "聯發科期", "type": "stock", "stock_code": "2454"},
}


def fetch_futures_data(symbols: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """
    抓取期貨即時行情
    
    Args:
        symbols: 期貨代碼列表，如 ["TX", "MTX"]，None 則抓全部
        
    Returns:
        {
            "TX": {
                "symbol": "TXF",
                "name": "台指期",
                "price": 24000.0,
                "yesterday_settle": 23800.0,
                "open": 23900.0,
                "high": 24100.0,
                "low": 23850.0,
                "volume": 50000,
                "change": 200.0,
                "change_pct": 0.84
            },
            ...
        }
    """
    try:
        # 抓取全部期貨行情
        payload = {"market": 0, "kind": 1}
        headers = {"Content-Type": "application/json"}
        
        logger.info("[TAIFEX] 抓取期貨即時行情...")
        resp = requests.post(TAIFEX_API_URL, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        
        raw = resp.json()
        
        if raw.get("RtCode") != "0":
            logger.warning(f"[TAIFEX] API 回傳異常: {raw.get('RtMsg')}")
            return None
        
        quote_list = raw.get("RtData", {}).get("QuoteList", [])
        if not quote_list:
            logger.warning("[TAIFEX] 無期貨行情資料")
            return None
        
        result = {}
        
        for item in quote_list:
            symbol_id = item.get("SymbolID", "")
            if not symbol_id:
                continue
            
            # 解析代碼
            # TXF-P -> TX近月, TXF-S -> TX次月
            # TXFH6-F -> 台指06月合約
            if symbol_id.endswith("-P"):
                base_symbol = symbol_id.replace("-P", "").replace("F", "")
            elif symbol_id.endswith("-S"):
                base_symbol = symbol_id.replace("-S", "").replace("F", "")
            elif symbol_id.endswith("-F") or symbol_id.endswith("-M"):
                # 特定月份合約 TXF06-F -> TX
                base_symbol = symbol_id.split("-")[0].replace("F", "")
            else:
                base_symbol = symbol_id
            
            # 如果有指定 symbols，只抓指定的
            if symbols and base_symbol not in symbols:
                continue
            
            # 跳過近月合約（通常無成交）
            if symbol_id.endswith("-P"):
                continue
            
            try:
                def safe_float(val, default=0):
                    if val is None or val == "" or val == "-":
                        return default
                    try:
                        return float(val)
                    except (ValueError, TypeError):
                        return default
                
                def safe_int(val, default=0):
                    if val is None or val == "" or val == "-":
                        return default
                    try:
                        return int(val)
                    except (ValueError, TypeError):
                        return default
                
                price = safe_float(item.get("CLastPrice"))
                yesterday_settle = safe_float(item.get("CRefPrice"))
                open_price = safe_float(item.get("COpenPrice"))
                high = safe_float(item.get("CHighPrice"))
                low = safe_float(item.get("CLowPrice"))
                volume = safe_int(item.get("CTotalVolume"))
                change = safe_float(item.get("CDiff"))
                change_pct = safe_float(item.get("CDiffRate"))
                
                # 只保留有成交的合約
                if price <= 0 and volume <= 0:
                    continue
                
                # 取得中文名稱
                disp_name = item.get("DispCName", "")
                if base_symbol in FUTURES_SYMBOLS:
                    name = FUTURES_SYMBOLS[base_symbol]["name"]
                else:
                    name = disp_name if disp_name else base_symbol
                
                result[base_symbol] = {
                    "symbol": symbol_id,
                    "name": name,
                    "price": price,
                    "yesterday_settle": yesterday_settle,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "volume": volume,
                    "change": change,
                    "change_pct": change_pct,
                    "date": item.get("CDate", ""),
                    "time": item.get("CTime", "")
                }
                
            except Exception as e:
                logger.warning(f"[TAIFEX] 解析 {symbol_id} 資料錯誤: {e}")
                continue
        
        return result if result else None
        
    except requests.exceptions.RequestException as e:
        logger.error(f"[TAIFEX] 抓取期貨行情失敗: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"[TAIFEX] 解析 JSON 失敗: {e}")
        return None


def get_futures_list() -> List[Dict[str, str]]:
    """
    取得可監控的期貨清單
    
    Returns:
        [{"symbol": "TX", "name": "台指期", "type": "index"}, ...]
    """
    result = []
    for symbol, info in FUTURES_SYMBOLS.items():
        result.append({
            "symbol": symbol,
            "name": info["name"],
            "type": info["type"]
        })
    return result


if __name__ == "__main__":
    # 測試用
    data = fetch_futures_data(["TX", "MTX", "CD"])
    if data:
        print("期貨即時行情：")
        for symbol, info in data.items():
            print(f"  {info['name']} ({symbol}): {info['price']:,.0f} ({info['change_pct']:+.2f}%)")
    else:
        print("無法取得期貨資料")
