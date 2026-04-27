#!/usr/bin/env python3
"""
SMART STOCK — 每日台股盤後自動分析腳本
由 GitHub Actions 每日 16:30 自動執行
"""
import json, os, requests, anthropic
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── 設定 ──────────────────────────────────────────────────────────────────
TW_TZ = timezone(timedelta(hours=8))
TODAY  = datetime.now(TW_TZ).strftime('%Y-%m-%d')
DATA_DIR = Path('data')
DATA_DIR.mkdir(exist_ok=True)

# 追蹤的 256 支股票（從 category sheet 匯入）
# 這份清單對應 HTML 裡的 CATEGORY_STOCKS
TRACKED_CODES = [
    # 軍工
    "2630","6753",
    # 生醫
    "1734","1762","4952","6547","6548","4174","4166","6197","6919",
    # AI/算力
    "2382","3231","2356","6770",
    # 半導體
    "2330","2454","6415","3711","2379","2337","3034","2303",
    # PCB
    "8358","2313","3037","6269","2316","3189","4927",
    # 電動車
    "1536","3665",
    # 低軌衛星
    "3008","4739","6443","6462","3228",
    # 機器人
    "2059","1723","1521","2049","2358",
    # 光通訊
    "3491","6669","3338","4956",
    # 航運
    "2603","2609","2615","2617","2637","2634",
    # 雷射
    "2233","3707","6671","3548","1528",
    # 其他（部分）
    "2412","2308","2317","2881","2882","2886","2891","5880",
]

DANGER_CODES = {"6770","1314","3128","2911","2314","2002","6140","8045"}

HEADERS = {'User-Agent': 'Mozilla/5.0 SmartStock/3.0'}

def fetch_twse_all():
    """抓取證交所全部股票當日收盤數據"""
    print("📡 抓取 TWSE 全部收盤數據...")
    try:
        r = requests.get(
            'https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL',
            headers=HEADERS, timeout=30
        )
        r.raise_for_status()
        data = r.json()
        result = {}
        for s in data:
            code = s.get('Code','').strip()
            if not code: continue
            def parse(x): return float(str(x).replace(',','')) if x and str(x) not in ('--','-','') else 0.0
            result[code] = {
                'code':   code,
                'name':   s.get('Name','').strip(),
                'close':  parse(s.get('ClosingPrice',0)),
                'change': parse(s.get('Change',0)),
                'volume': int(str(s.get('TradeVolume',0)).replace(',','') or 0),
                'high':   parse(s.get('HighestPrice',0)),
                'low':    parse(s.get('LowestPrice',0)),
                'open':   parse(s.get('OpeningPrice',0)),
            }
        print(f"  ✅ 取得 {len(result)} 支股票數據")
        return result
    except Exception as e:
        print(f"  ❌ TWSE 失敗: {e}")
        return {}

def fetch_legal_persons():
    """抓取三大法人買賣超"""
    print("📡 抓取三大法人數據...")
    try:
        r = requests.get(
            'https://openapi.twse.com.tw/v1/fund/T86',
            headers=HEADERS, timeout=30
        )
        r.raise_for_status()
        data = r.json()
        result = {}
        for s in data:
            code = s.get('Securities_code','').strip()
            if not code: continue
            def parse_int(x):
                try: return int(str(x).replace(',',''))
                except: return 0
            foreign = parse_int(s.get('Foreign_Investor_net_buy_or_sell',0))
            trust   = parse_int(s.get('Investment_Trust_net_buy_or_sell',0))
            dealer  = parse_int(s.get('Dealer_net_buy_or_sell',0))
            result[code] = {
                'foreign': foreign,
                'trust':   trust,
                'dealer':  dealer,
                'net':     foreign + trust + dealer,
            }
        print(f"  ✅ 取得 {len(result)} 支法人數據")
        return result
    except Exception as e:
        print(f"  ❌ 法人數據失敗: {e}")
        return {}

def fetch_market_index():
    """抓取大盤指數"""
    print("📡 抓取大盤指數...")
    try:
        r = requests.get(
            'https://openapi.twse.com.tw/v1/exchangeReport/FMTQIK',
            headers=HEADERS, timeout=15
        )
        r.raise_for_status()
        data = r.json()
        if data:
            idx = data[-1]  # 最新一筆
            return {
                'date':       idx.get('Date',''),
                'taiex':      idx.get('Index','').replace(',',''),
                'change':     idx.get('Change',''),
                'change_pct': idx.get('ChangePercent',''),
                'volume':     idx.get('TradeVolume',''),
            }
    except Exception as e:
        print(f"  ❌ 大盤指數失敗: {e}")
    return {}

def build_analysis_summary(twse, legal):
    """整理追蹤股票的真實數據，供 AI 分析"""
    lines = []
    for code in TRACKED_CODES:
        if code in DANGER_CODES: continue
        d = twse.get(code)
        l = legal.get(code)
        if not d or not d['close']: continue
        chg_pct = (d['change'] / (d['close'] - d['change']) * 100) if (d['close'] - d['change']) > 0 else 0
        legal_str = f" 法人:{'+' if l['net']>0 else ''}{l['net']}" if l else ""
        lines.append(
            f"{d['name']}({code}) 收{d['close']} "
            f"{'▲' if d['change']>=0 else '▼'}{abs(d['change'])}({chg_pct:+.1f}%) "
            f"量{d['volume']//1000}張{legal_str}"
        )
    return '\n'.join(lines)

def run_ai_analysis(twse_summary, market_info):
    """呼叫 Claude API 進行選股分析"""
    print("🤖 呼叫 Claude AI 分析...")
    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

    market_str = f"大盤指數 {market_info.get('taiex','—')}，漲跌 {market_info.get('change','—')}({market_info.get('change_pct','—')}%)" if market_info else "大盤數據未取得"

    prompt = f"""你是台灣股市資深分析師，今天是 {TODAY}（台灣時間）。

【今日大盤】{market_str}

【追蹤標的今日真實盤後數據】
{twse_summary}

請根據以下十大條件，從上方數據中精選 5 支最值得關注的股票：

① 趨勢突破：突破近期整理區、當天明顯放量、收盤站穩壓力線
② 均線多頭排列：股價強勢、均線上彎
③ 爆量紅K：成交量異常放大（>均量2倍）、收紅K
④ 回檔不破：回檔量縮、不跌破關鍵均線
⑤ 法人連買：外資/投信淨買超（正值）
⑥ 題材剛啟動：熱門題材、剛開始上漲
⑦ 低檔轉強：止跌後放量長紅
⑧ 強勢續強：持續創高、回檔量縮（8zz風格）
⑨ 基本面成長：營收/EPS成長
⑩ 技術共振：MACD翻多、RSI>50

請特別注意：
- 成交量異常大（>5000張）且收漲的股票優先考慮
- 法人淨買超大的股票加分
- 漲幅超過 3% 且量大的優先

只輸出 JSON，格式如下，不要任何其他文字：
{{
  "date": "{TODAY}",
  "market_summary": "今日大盤一句話概況",
  "hot_category": "今日最熱題材",
  "picks": [
    {{
      "rank": 1,
      "name": "股票名稱",
      "code": "代號",
      "price": "收盤價（數字）",
      "change": "+X.XX",
      "change_pct": "+X.X%",
      "up": true,
      "category": "類別",
      "criteria_met": [1, 3, 5],
      "criteria_scores": [85, 0, 90, 0, 80, 0, 0, 0, 0, 70],
      "signals": ["今日放量突破", "外資買超", "MACD翻多"],
      "analysis": "約60字分析，說明為何今日特別值得注意，用第一人稱，不說建議買入",
      "volume_score": 85,
      "trend_score": 80,
      "news_score": 70,
      "fundamental_score": 65,
      "buy_low": "估計建議買入低點",
      "buy_high": "估計建議買入高點",
      "target_price": "目標價",
      "stop_loss": "建議停損價",
      "near_resistance": false,
      "profit_pct": 0,
      "eightZZ_signal": "8zz 無相關訊號"
    }}
  ]
}}"""

    response = client.messages.create(
        model='claude-sonnet-4-20250514',
        max_tokens=4000,
        messages=[{'role':'user','content':prompt}]
    )

    text = response.content[0].text
    # Extract JSON
    depth, start, end = 0, -1, -1
    for i, c in enumerate(text):
        if c == '{':
            if depth == 0: start = i
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0 and start > -1:
                end = i
                break

    if start == -1:
        raise ValueError(f"No JSON in response: {text[:200]}")

    result = json.loads(text[start:end+1])
    print(f"  ✅ 分析完成，選出 {len(result.get('picks',[]))} 支")
    return result

def save_results(twse, legal, analysis, market):
    """儲存所有結果到 data/ 資料夾"""
    # 今日完整分析結果
    output = {
        'date':      TODAY,
        'generated': datetime.now(TW_TZ).isoformat(),
        'market':    market,
        'analysis':  analysis,
        'raw_data': {
            code: {**twse[code], 'legal': legal.get(code,{})}
            for code in TRACKED_CODES
            if code in twse
        }
    }

    # 存今日結果
    today_file = DATA_DIR / f'{TODAY}.json'
    with open(today_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"  💾 儲存：{today_file}")

    # 更新 latest.json（HTML 會讀這個）
    latest_file = DATA_DIR / 'latest.json'
    with open(latest_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"  💾 更新：{latest_file}")

    # 更新 history.json（最近 50 日）
    history_file = DATA_DIR / 'history.json'
    history = []
    if history_file.exists():
        try:
            history = json.loads(history_file.read_text(encoding='utf-8'))
        except: history = []

    # 移除今日舊記錄（如果有）
    history = [h for h in history if h.get('date') != TODAY]
    history.insert(0, {
        'date':    TODAY,
        'picks':   [p['name']+'('+p['code']+')' for p in analysis.get('picks',[])],
        'market':  analysis.get('market_summary',''),
        'hot_cat': analysis.get('hot_category',''),
    })
    # 保留最近 50 筆
    history = history[:50]

    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"  💾 更新：{history_file}（共 {len(history)} 筆）")

def main():
    print(f"\n{'='*50}")
    print(f"SMART STOCK 每日自動分析 — {TODAY}")
    print(f"{'='*50}\n")

    # 1. 抓取真實數據
    twse   = fetch_twse_all()
    legal  = fetch_legal_persons()
    market = fetch_market_index()

    if not twse:
        print("⚠️  今日為休市日或 API 暫時無法使用，跳過分析")
        return

    # 2. 確認是否有追蹤股票的數據
    tracked_with_data = [c for c in TRACKED_CODES if c in twse and twse[c]['close'] > 0]
    print(f"\n📊 追蹤股票有數據：{len(tracked_with_data)}/{len(TRACKED_CODES)} 支")

    if len(tracked_with_data) < 10:
        print("⚠️  數據不足，可能為休市日，跳過分析")
        return

    # 3. AI 分析
    twse_summary = build_analysis_summary(twse, legal)
    analysis = run_ai_analysis(twse_summary, market)

    # 4. 儲存結果
    print("\n💾 儲存結果...")
    save_results(twse, legal, analysis, market)

    print(f"\n✅ 完成！今日精選：")
    for p in analysis.get('picks', []):
        criteria_count = len(p.get('criteria_met', []))
        print(f"  {p['rank']}. {p['name']}({p['code']}) {p.get('change','')} | {criteria_count}/10條件 | {p.get('analysis','')[:40]}...")

    print(f"\n{'='*50}\n")

if __name__ == '__main__':
    main()
