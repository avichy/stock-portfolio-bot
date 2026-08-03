import os
import json
import datetime
import yfinance as yf
import google.generativeai as genai

# קובץ מטמון ל-AI
CACHE_FILE = "ai_cache.json"

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_cache(data):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Error saving cache: {e}")

def get_gemini_response(prompt_text):
    # רוטציה בין מפתחות API מרובים מתוך משתני הסביבה
    api_keys = []
    for i in range(1, 6):
        key = os.getenv(f"GEMINI_API_KEY_{i}")
        if key:
            api_keys.append(key)
    single_key = os.getenv("GEMINI_API_KEY")
    if single_key and single_key not in api_keys:
        api_keys.append(single_key)
        
    if not api_keys:
        print("No Gemini API keys found in environment variables.")
        return None

    for api_key in api_keys:
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-1.5-pro')
            response = model.generate_content(prompt_text)
            if response and response.text:
                return response.text
        except Exception as e:
            print(f"API key failed, trying next... Error: {e}")
            continue
    return None

def fetch_market_data(tickers):
    data = {}
    for ticker in tickers:
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="5d")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
                prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
                change = ((current_price - prev_close) / prev_close) * 100
                
                info = t.info
                target = info.get('targetMeanPrice', 0)
                
                data[ticker] = {
                    "price": float(current_price),
                    "change": float(change),
                    "target": float(target) if target else 0
                }
        except Exception as e:
            print(f"Error fetching data for {ticker}: {e}")
            data[ticker] = {"price": 0, "change": 0, "target": 0}
    return data

def format_num(val):
    if val is None:
        return "0.00"
    return f"{val:,.2f}"

def format_pct_colored(val):
    if val is None:
        return "0.00%"
    sign = "+" if val > 0 else ""
    return f"{sign}{val:.2f}%"

def main():
    print("Starting market dashboard update script...")
    
    # הגדרת רשימת המניות בתיק האישי ובמעקב
    portfolio_stocks = [
        {"symbol": "AMD", "shares": 10, "avg_price": 120.0},
        {"symbol": "INTC", "shares": 15, "avg_price": 30.0},
        {"symbol": "MU", "shares": 8, "avg_price": 90.0},
        {"symbol": "NVDA", "shares": 5, "avg_price": 100.0}
    ]
    
    watchlist = [s["symbol"] for s in portfolio_stocks] + ["TSLA", "AAPL", "MSFT"]
    watchlist = list(set(watchlist)) # הסרת כפיפויות
    
    # 1. שליפת נתונים פיננסיים בזמן אמת
    market_data = fetch_market_data(watchlist)
    
    # 2. ניהול מטמון וקריאת AI
    cache = load_cache()
    now = datetime.datetime.now()
    
    ai_prompt = "תן לי ניתוח קצר למניות NVDA, TSLA, AMD בפורמט JSON הכולל רשימת long_term ו-swing עם שדות: symbol, name, rationale, target, sector_desc."
    
    ai_raw_text = get_gemini_response(ai_prompt)
    if ai_raw_text:
        try:
            clean_json = ai_raw_text.replace("```json", "").replace("
