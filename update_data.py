from datetime import datetime
import json
import os
import subprocess
import time
import traceback
import pytz
import requests
import yfinance as yf

AI_CACHE_FILE = "ai_cache.json"

def load_ai_cache():
    if os.path.exists(AI_CACHE_FILE):
        try:
            with open(AI_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_ai_cache(data):
    try:
        with open(AI_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving AI cache: {e}")

def format_num(val, decimals=2):
    try:
        num = float(val)
        if decimals == 0:
            return f"{num:,.0f}"
        return f"{num:,.{decimals}f}"
    except (ValueError, TypeError):
        return str(val)

def format_pct_colored(val):
    try:
        num = float(val)
        sign = "+" if num > 0 else ""
        color = "#2ecc71" if num >= 0 else "#e74c3c"
        return f'<span style="color: {color}; font-weight: bold;">{sign}{num:.2f}%</span>'
    except (ValueError, TypeError):
        return str(val)

def get_default_ai_insights():
    """נתוני גיבוי למקרה שה-AI חורג מהמכסה, כדי שהדשבורד לעולם לא יישאר ריק"""
    default_stock = {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "target": "240.00",
        "sector_desc": "טכנולוגיה ומוצרי אלקטרוניקה צרכנית",
        "rationale": "חברה יציבה עם תזרים מזומנים חזק, מובילה בעולם הטכנולוגיה והשירותים הדיגיטליים.",
        "news_title": "עדכון שוק וסקירה טכנית שוטפת",
        "news_content": "הפעילות העסקית נמשכת ביציבות עם דגש על חדשנות וגידול בהכנסות ממגזר השירותים.",
        "news_impact": "השפעה חיובית ומתונה על המגמה הראשית בתיק ההשקעות."
    }
    
    stocks_list = [
        {**default_stock, "symbol": "AAPL", "name": "Apple"},
        {**default_stock, "symbol": "MSFT", "name": "Microsoft"},
        {**default_stock, "symbol": "GOOGL", "name": "Alphabet"},
        {**default_stock, "symbol": "AMZN", "name": "Amazon"},
        {**default_stock, "symbol": "NVDA", "name": "NVIDIA"},
        {**default_stock, "symbol": "META", "name": "Meta Platforms"},
        {**default_stock, "symbol": "TSLA", "name": "Tesla"},
        {**default_stock, "symbol": "BRK-B", "name": "Berkshire Hathaway"},
        {**default_stock, "symbol": "JPM", "name": "JPMorgan Chase"},
        {**default_stock, "symbol": "V", "name": "Visa"}
    ]

    return {
        "SP500_ANALYSIS": "מדד S&P 500 ממשיך להיסחר סביב רמות מפתח תוך בחינת נתוני המאקרו והאינפלציה.",
        "NASDAQ_ANALYSIS": "מדד הטכנולוגיה מוביל את הסנטימנט בשוק עם דגש על חברות הבינה המלאכותית.",
        "DOW_ANALYSIS": "מניות הערך במדד הדאו ג'ונס מספקות יציבות ועוגן לתיק המסחר.",
        "VIX_ANALYSIS": "מדד התנודתיות משקף רמת רגיעה מתונה בשווקים ללא לחצים חריגים.",
        "DXY_ANALYSIS": "מדד הדולר העולמי נסחר במגמה מעורבת אל מול המטבעות המרכזיים.",
        "long_term_stocks": stocks_list,
        "swing_stocks": stocks_list,
        "USD_ILS_EXPLANATION": "השפעה ישירה על עלות ייבוא, מוצרים דולריים ותיק ההשקעות המקומי.",
        "OIL_EXPLANATION": "משפיע ישירות על עלויות האנרגיה, התחבורה ושיעורי האינפלציה הגלובליים.",
        "GOLD_EXPLANATION": "משמש כנכס מקלט בטוח וגידור מרכזי מפני אי-יציבות גיאו-פוליטית.",
        "BTC_EXPLANATION": "אינדיקטור מוביל לסנטימנט סיכון ונזילות בנכסים אלטרנטיביים.",
        "US_MARKET_MACRO_NEWS": "נתוני המאקרו ממשיכים להוות מנוע ניווט מרכזי עבור הבנק המרכזי והמשקיעים.",
        "IL_MARKET_MACRO_NEWS": "השוק המקומי מגיב להתפתחויות הביטחוניות והכלכליות באזור.",
        "RISK_MANAGEMENT_TEXT": "ניהול סיכונים קפדני באמצעות פיזור השקעות ופקודות הגנה.",
        "ACTION_RECOMMENDATIONS_TEXT": "בחינה מדודה של פוזיציות קיימות והיערכות להזדמנויות סלקטיביות."
    }

israel_tz = pytz.timezone("Asia/Jerusalem")
now_il = datetime.now(israel_tz)
day_name = {
    0: "שני",
    1: "שלישי",
    2: "רביעי",
    3: "חמישי",
    4: "שישי",
    5: "שבת",
    6: "ראשון",
}[now_il.weekday()]

portfolio_buys = {
    "NVDA": {"shares": 3, "buy": 184.90},
    "AMD": {"shares": 20, "buy": 211.34},
    "MU": {"shares": 6, "buy": 316.32},
    "SNDK": {"shares": 4, "buy": 630.26},
    "WDC": {"shares": 6, "buy": 223.23},
    "INTC": {"shares": 20, "buy": 43.05},
    "SIMO": {"shares": 30, "buy": 131.32},
    "IREN": {"shares": 54, "buy": 52.75},
    "CIFR": {"shares": 28, "buy": 17.50},
    "META": {"shares": 2, "buy": 661.00},
    "AMZN": {"shares": 6, "buy": 229.29},
    "GOOG": {"shares": 4, "buy": 317.95},
    "TTWO": {"shares": 5, "buy": 235.50},
    "WMT": {"shares": 16, "buy": 119.45},
    "NFLX": {"shares": 14, "buy": 94.03},
    "MA": {"shares": 4, "buy": 503.99},
    "IBIT": {"shares": 14, "buy": 60.48},
    "GTEC": {"shares": 260, "buy": 1.27},
    "TQQQ": {"shares": 28, "buy": 56.53},
}

base_market_tickers = [
    "GC=F",
    "CL=F",
    "BTC-USD",
    "USDILS=X",
    "^GSPC",
    "^IXIC",
    "^DJI",
    "^VIX",
] + list(portfolio_buys.keys())

def fetch_market_data(tickers):
    market_data = {}
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            info = stock.info
            target_mean = info.get("targetMeanPrice")
            if not hist.empty:
                current_price = round(hist["Close"].iloc[-1], 2)
                prev_close = hist["Close"].iloc[-2] if len(hist) > 1 else current_price
                change = round(((current_price - prev_close) / prev_close) * 100, 2)
                market_data[ticker] = {
                    "price": current_price,
                    "change": change,
                    "target": target_mean if target_mean else 0.0,
                }
            else:
                market_data[ticker] = {"price": 0.0, "change": 0.0, "target": 0.0}
        except Exception as e:
            market_data[ticker] = {"price": 0.0, "change": 0.0, "target": 0.0}
    return market_data

current_key_index = 0

def generate_ai_insights(market_data):
    global current_key_index
    api_keys = []
    for i in range(1, 6):
        k = os.environ.get(f"GEMINI_API_KEY_{i}")
        if k:
            api_keys.append(k)
    general_k = os.environ.get("GEMINI_API_KEY")
    if general_k and general_k not in api_keys:
        api_keys.append(general_k)
    valid_keys = [k for k in api_keys if k]
    if not valid_keys:
        print("Error: No Gemini API keys found. Using fallback data.")
        return get_default_ai_insights()

    market_json = json.dumps(market_data, ensure_ascii=False)
    prompt_raw = (
        "אתה אנליסט בכיר בשוק ההון. נתח את נתוני המאקרו והשוק הבאים:\n"
        f"{market_json}\n\n"
        "כללי חובה קשיחים:\n"
        "1. ספק ניתוח אנליסטי מפורט וגנרי תחת SP500_ANALYSIS, NASDAQ_ANALYSIS, DOW_ANALYSIS, VIX_ANALYSIS, DXY_ANALYSIS.\n"
        "2. בחר והחזר בדיוק **10 מניות** להשקעה ארוכת טווח (Long-Term Core) תחת המפתח 'long_term_stocks' כמערך JSON הכולל את השדות: symbol, name, target, rationale, news_title, news_content, news_impact.\n"
        "3. בחר והחזר בדיוק **10 מניות** למסחר סווינג קצר טווח (Swing Trading) תחת המפתח 'swing_stocks' כמערך JSON הכולל את השדות: symbol, name, target, sector_desc, rationale, news_title, news_content, news_impact.\n"
        "4. הוסף הסברים קצרים בשפה פשוטה ומעודכנית למצב השוק הנוכחי עבור ארבעת הנכסים הבאים תחת המפתחות:\n"
        "   - USD_ILS_EXPLANATION\n"
        "   - OIL_EXPLANATION\n"
        "   - GOLD_EXPLANATION\n"
        "   - BTC_EXPLANATION\n"
        "5. הוסף ניתוחי מאקרו כלליים תחת המפתחות: US_MARKET_MACRO_NEWS, IL_MARKET_MACRO_NEWS, RISK_MANAGEMENT_TEXT, ACTION_RECOMMENDATIONS_TEXT.\n"
        "6. החזר אובייקט JSON תקף בלבד, ללא שום טקסט נוסף מסביב.\n"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt_raw}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "max_output_tokens": 8192,
        },
    }

    max_attempts = len(valid_keys) * 2
    attempts = 0
    while attempts < max_attempts:
        api_key = valid_keys[current_key_index % len(valid_keys)]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        try:
            res = requests.post(url, json=payload, timeout=60)
            res_data = res.json()
            if "candidates" in res_data:
                text_response = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text_response.startswith("```json"):
                    text_response = text_response[7:]
                if text_response.startswith("```"):
                    text_response = text_response[3:]
                if text_response.endswith("```"):
                    text_response = text_response[:-3]
                parsed_res = json.loads(text_response.strip())
                if isinstance(parsed_res, dict) and len(parsed_res) > 0:
                    return parsed_res
            print(f"API Warning/Error response: {res_data}")
            current_key_index += 1
            time.sleep(5)
        except Exception as e:
            print(f"Exception during AI generation: {e}")
            current_key_index += 1
            time.sleep(5)
        attempts += 1
    
    print("All AI attempts failed or quota exceeded. Returning default fallback insights.")
    return get_default_ai_insights()

try:
    base_market_data = fetch_market_data(base_market_tickers)

    trigger_event = os.environ.get("TRIGGER_EVENT", "")
    current_hour = now_il.hour
    current_minute = now_il.minute
    ai_hours = [10, 13, 16, 19, 22, 0]

    run_ai = (trigger_event == "workflow_dispatch") or (
        (current_hour in ai_hours) and (current_minute < 15)
    )

    ai_insights = {}
    if run_ai:
        print("Running Gemini AI generation...")
        ai_insights = generate_ai_insights(base_market_data)
        if ai_insights and len(ai_insights.get("long_term_stocks", [])) > 0:
            save_ai_cache(ai_insights)
        else:
            ai_insights = load_ai_cache()
            if not ai_insights:
                ai_insights = get_default_ai_insights()
    else:
        ai_insights = load_ai_cache()
        if not ai_insights or len(ai_insights.get("long_term_stocks", [])) == 0:
            ai_insights = get_default_ai_insights()

    date_str = now_il.strftime("%d.%m.%Y")
    time_str = now_il.strftime("%H:%M")

    sp500 = base_market_data.get("^GSPC", {})
    nasdaq = base_market_data.get("^IXIC", {})
    dji = base_market_data.get("^DJI", {})
    vix = base_market_data.get("^VIX", {})
    dxy = base_market_data.get("USDILS=X", {})

    sp500_price = format_num(sp500.get("price", 0))
    sp500_change =
