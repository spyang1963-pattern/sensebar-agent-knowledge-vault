# institutional_fetcher.py
"""
三大法人買賣超資料模組
抓取 TWSE 三大法人買賣超日報資料
"""
import requests
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

TWSE_INST_URL = "https://www.twse.com.tw/fund/T86"


def fetch_institutional_data(date: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """
    抓取三大法人買賣超資料
    
    Args:
        date: 指定日期，None 則為今日
        
    Returns:
        {
            "date": "2026/07/23",
            "data": [
                {
                    "code": "0050",
                    "name": "元大台灣50",
                    "foreign_net": 1609,      # 外陸資淨買
                    "trust_net": -725,         # 投信淨買
                    "dealer_net": -747,        # 自營商淨買
                    "total_net": 1120          # 三大法人合計淨買
                },
                ...
            ]
        }
    """
    if date is None:
        # 不帶 date 參數，TWSE 會回傳最新交易日資料（週末/例假日安全）
        params = {
            "response": "json",
            "selectType": "ALL"
        }
        date_label = "latest"
    else:
        formatted_date = date.strftime("%Y%m%d")
        params = {
            "response": "json",
            "date": formatted_date,
            "selectType": "ALL"
        }
        date_label = formatted_date
    
    try:
        logger.info(f"[TWSE] 抓取三大法人資料: {date_label}")
        resp = requests.get(TWSE_INST_URL, params=params, timeout=30)
        resp.raise_for_status()
        
        raw = resp.json()
        
        if raw.get("stat") != "OK":
            logger.warning(f"[TWSE] 三大法人 API 回傳異常: {raw.get('stat')}")
            return None
        
        data_rows = raw.get("data", [])
        if not data_rows:
            logger.warning(f"[TWSE] 三大法人資料為空: {date_label}")
            return None
        
        # 欄位名稱
        fields = raw.get("fields", [])
        logger.info(f"[TWSE] 三大法人共 {len(data_rows)} 檔股票")
        
        result = {
            "date": raw.get("date", date_label),
            "data": []
        }
        
        for row in data_rows:
            try:
                # 欄位順序依 TWSE API 實際回傳
                # [證券代號, 證券名稱, 外陸資買進, 外陸資賣出, 外陸資買賣超,
                #  外資自營商買進, 外資自營商賣出, 外資自營商買賣超,
                #  投信買進, 投信賣出, 投信買賣超,
                #  自營商買賣超, 自營商買進(自行), 自營商賣出(自行), 自營商買賣超(自行),
                #  自營商買進(避險), 自營商賣出(避險), 自營商買賣超(避險), 三大法人買賣超]
                
                code = row[0].strip()
                name = row[1].strip()
                
                # 解析數字（含逗號）
                def parse_num(s):
                    try:
                        return int(s.replace(",", ""))
                    except (ValueError, AttributeError):
                        return 0
                
                foreign_net = parse_num(row[4])   # 外陸資買賣超
                trust_net = parse_num(row[10])     # 投信買賣超
                dealer_net = parse_num(row[11])    # 自營商買賣超
                total_net = parse_num(row[18])     # 三大法人買賣超
                
                result["data"].append({
                    "code": code,
                    "name": name,
                    "foreign_net": foreign_net,
                    "trust_net": trust_net,
                    "dealer_net": dealer_net,
                    "total_net": total_net
                })
            except (IndexError, ValueError) as e:
                logger.warning(f"[TWSE] 解析三大法人資料錯誤: {row[:2]}, {e}")
                continue
        
        return result
        
    except requests.exceptions.RequestException as e:
        logger.error(f"[TWSE] 抓取三大法人資料失敗: {e}")
        return None
    except json.JSONDecodeError as e:
        logger.error(f"[TWSE] 解析三大法人 JSON 失敗: {e}")
        return None


def get_stock_institutional(code: str, date: Optional[datetime] = None) -> Optional[Dict[str, Any]]:
    """
    取得個股的三大法人買賣超資料
    
    Args:
        code: 股票代號
        date: 指定日期
        
    Returns:
        {
            "code": "2330",
            "name": "台積電",
            "foreign_net": 12345,
            "trust_net": -1000,
            "dealer_net": 500,
            "total_net": 11845,
            "date": "2026/07/23"
        }
    """
    result = fetch_institutional_data(date)
    if result is None:
        return None
    
    for item in result["data"]:
        if item["code"] == code:
            item["date"] = result["date"]
            return item
    
    return None


def get_top_buyers(date: Optional[datetime] = None, top_n: int = 10) -> Optional[List[Dict[str, Any]]]:
    """
    取得三大法人淨買超前 N 名
    
    Args:
        date: 指定日期
        top_n: 前幾名
        
    Returns:
        [
            {"code": "0050", "name": "元大台灣50", "total_net": 12345, "foreign_net": ..., ...},
            ...
        ]
    """
    result = fetch_institutional_data(date)
    if result is None:
        return None
    
    # 按三大法人合計淨買超排序
    sorted_data = sorted(result["data"], key=lambda x: x["total_net"], reverse=True)
    return sorted_data[:top_n]


def get_top_sellers(date: Optional[datetime] = None, top_n: int = 10) -> Optional[List[Dict[str, Any]]]:
    """
    取得三大法人淨賣超前 N 名
    
    Args:
        date: 指定日期
        top_n: 前幾名
        
    Returns:
        [
            {"code": "0050", "name": "元大台灣50", "total_net": -12345, ...},
            ...
        ]
    """
    result = fetch_institutional_data(date)
    if result is None:
        return None
    
    # 按三大法人合計淨賣超排序（負數，所以 reverse=False）
    sorted_data = sorted(result["data"], key=lambda x: x["total_net"])
    return sorted_data[:top_n]


if __name__ == "__main__":
    # 測試用
    result = fetch_institutional_data()
    if result:
        print(f"日期: {result['date']}")
        print(f"共 {len(result['data'])} 檔股票")
        
        top_buy = get_top_buyers()
        if top_buy:
            print("\n【三大法人淨買超前10名】")
            for i, item in enumerate(top_buy, 1):
                print(f"{i}. {item['code']} {item['name']}: {item['total_net']:,} 股")
    else:
        print("無法取得三大法人資料")
