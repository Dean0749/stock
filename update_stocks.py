import requests
import pandas as pd

def fetch_latest_prices():
    # 呼叫證交所 OpenAPI (當日所有股票收盤行情)
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    response = requests.get(url)
    
    if response.status_code == 200:
        data = response.json()
        df_all = pd.DataFrame(data)
        # 轉換為容易查詢的格式
        # 欄位通常包含: 證券代號, 證券名稱, 收盤價, 漲跌價差...
        price_map = df_all.set_index('證券代號')['收盤價'].to_dict()
        return price_map
    return {}

# 整合到您的 JSON 產生流程
def update_json_with_real_price():
    prices = fetch_latest_prices()
    # 讀取您的 category.csv 並填入真實股價
    # ... (其餘邏輯同前一則回覆)
