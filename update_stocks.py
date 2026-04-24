import requests
import pandas as pd
import json
import os
from datetime import datetime

def fetch_market_data():
    """從證交所 OpenAPI 抓取全市場最新行情"""
    print("正在從證交所抓取即時行情...")
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    try:
        response = requests.get(url, timeout=30)
        if response.status_code == 200:
            # 轉換為字典格式： { "股號": { "收盤價": "xx", "漲跌": "xx", "成交量": "xx" } }
            data = response.json()
            market_map = {
                item['Code']: {
                    "price": item['ClosingPrice'],
                    "change": item['Change'],
                    "volume": item['TradeVolume']
                } for item in data
            }
            return market_map
    except Exception as e:
        print(f"API 抓取失敗: {e}")
    return {}

def update_stocks():
    # 1. 讀取您的 256 隻標的清單
    csv_file = '標的篩選.xlsx - category.csv'
    if not os.path.exists(csv_file):
        print(f"錯誤：找不到 {csv_file}")
        return

    df_targets = pd.read_csv(csv_file)
    
    # 2. 獲取市場真實數據
    market_data = fetch_market_data()
    
    # 3. 整合數據
    final_picks = []
    for _, row in df_targets.iterrows():
        ticker = str(row['股號']).strip()
        name = row['股名']
        category = row['類別']
        
        # 取得 API 數據，若抓不到則留白
        real_info = market_data.get(ticker, {"price": "N/A", "change": "0", "volume": "0"})
        
        # 簡單邏輯：如果漲幅 > 2% 則給予高強度 (這部分可自行修改邏輯)
        try:
            change_val = float(real_info['change'])
            strength = 3 if change_val > 0 else 2
        except:
            strength = 2

        final_picks.append({
            "ticker": ticker,
            "name": name,
            "category": category,
            "price": real_info['price'],
            "change": real_info['change'],
            "volume": real_info['volume'],
            "strength": strength,
            "reason": f"【{category}】題材，目前報價 {real_info['price']}。"
        })

    # 4. 輸出 JSON
    output = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "picks": final_picks
    }

    os.makedirs('data', exist_ok=True)
    with open('data/picks.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"更新完成！共處理 {len(final_picks)} 隻標的。")

if __name__ == "__main__":
    update_stocks()
