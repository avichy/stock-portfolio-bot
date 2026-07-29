from datetime import datetime
import json
import os
import pytz
import yfinance as yf
import requests

def format_num(val, decimals=2):
    try:
        num = float(val)
        if decimals == 0:
            return f"{num:,.0f}"
        return f"{num:,.{decimals}f}"
    except (ValueError, TypeError):
        return str(val)

israel_tz = pytz.timezone("Asia/Jerusalem")
now_il = datetime.now(israel_tz)

current_date = now_il.date()
current_hour = now_il.hour
current_minute = now_il.minute
current_total_minutes = current_hour * 60 + current_minute

trigger_event = os.environ.get("GITHUB_EVENT_NAME") or os.environ.get("TRIGGER_EVENT") or "schedule"

print(f"Current Israel Time: {now_il.strftime('%Y-%m-%d %H:%M')} - Event: {trigger_event}")

all_strategy_tickers = [
    "NVDA", "AMD", "MU", "GOOG", "AMZN", "META", "MA", "WMT", "TTWO", "WDC", 
    "TQQQ", "INTC", "IREN", "CIFR", "IBIT", "SIMO", "SNDK", "NFLX", "GTEC"
]

tickers_to_fetch = all_strategy_tickers + ["GC=F", "CL=F", "BTC-USD", "USDILS=X", "^GSPC", "^IXIC", "^DJI", "^VIX"]

def fetch_all_data():
    market_data = {}
    print("Fetching market data from yfinance...")
    for ticker in tickers_to_fetch:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if not hist.empty:
                current_price = round(hist["Close"].iloc[-1], 2)
                prev_close = hist["Close"].iloc[-2] if len(hist) > 1 else current_price
                change = round(((current_price - prev_close) / prev_close) * 100, 2)
                market_data[ticker] = {"price": current_price, "change": change}
            else:
                market_data[ticker] = {"price": 0.0, "change": 0.0}
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            market_data[ticker] = {"price": 0.0, "change": 0.0}
    print("Market data fetch completed.")
    return market_data

portfolio_buys = {
    "NVDA": {"shares": 3, "buy": 184.90, "target": 220.0},
    "AMD": {"shares": 20, "buy": 211.34, "target": 250.0},
    "MU": {"shares": 6, "buy": 316.32, "target": 350.0},
    "SNDK": {"shares": 4, "buy": 630.26, "target": 700.0},
    "WDC": {"shares": 6, "buy": 223.23, "target": 260.0},
    "INTC": {"shares": 20, "buy": 43.05, "target": 55.0},
    "SIMO": {"shares": 30, "buy": 131.32, "target": 160.0},
    "IREN": {"shares": 54, "buy": 52.75, "target": 70.0},
    "CIFR": {"shares": 28, "buy": 17.50, "target": 25.0},
    "META": {"shares": 2, "buy": 661.00, "target": 750.0},
    "AMZN": {"shares": 6, "buy": 229.29, "target": 270.0},
    "GOOG": {"shares": 4, "buy": 317.95, "target": 360.0},
    "TTWO": {"shares": 5, "buy": 235.50, "target": 280.0},
    "WMT": {"shares": 16, "buy": 119.45, "target": 140.0},
    "NFLX": {"shares": 14, "buy": 94.03, "target": 120.0},
    "MA": {"shares": 4, "buy": 503.99, "target": 580.0},
    "IBIT": {"shares": 14, "buy": 60.48, "target": 75.0},
    "GTEC": {"shares": 260, "buy": 1.27, "target": 2.0},
    "TQQQ": {"shares": 28, "buy": 56.53, "target": 75.0}
}

def generate_ai_insights(market_data):
    api_keys = [
        os.environ.get("GEMINI_API_KEY_1") or os.environ.get("GEMINI_API_KEY"),
        os.environ.get("GEMINI_API_KEY_2")
    ]
    valid_keys = [k for k in api_keys if k]
    if not valid_keys:
        print("No GEMINI_API_KEY found. Skipping AI generation.")
        return {}

    prompt = f"""אתה אנליסט בכיר בשוק ההון. ניתוח נתוני השוק החיים כרגע:
{json.dumps(market_data, ensure_ascii=False)}

החזר אובייקט JSON תקף בלבד הכולל את המפתחות הבאים בעברית מקצועית:
- US_MARKET_MACRO_NEWS
- IL_MARKET_MACRO_NEWS
- SECTOR_CHIPS_DESC
- SECTOR_CLOUD_DESC
- SECTOR_CRYPTO_DESC
- SECTOR_CHIP_PERF
- SECTOR_CLOUD_PERF
- SECTOR_CRYPTO_PERF
- CATALYST_EARNINGS
- CATALYST_MONETARY
- CATALYST_HARDWARE
- COMMUNITY_SENTIMENT
- ANALYST_POINT_1
- ANALYST_POINT_2
- RISK_MANAGEMENT_TEXT
- ACTION_RECOMMENDATIONS_TEXT

וכמו כן, עבור כל סמל ({', '.join(all_strategy_tickers)}), הוסף מפתחות:
- [TICKER]_RATIONALE
- [TICKER]_SWING_TEXT
- [TICKER]_NEWS_TITLE
- [TICKER]_NEWS_CONTENT
- [TICKER]_NEWS_IMPACT
- [TICKER]_NEWS_LINK
- [TICKER]_PORT_NOTE"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"}
    }

    for api_key in valid_keys:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            res = requests.post(url, json=payload, timeout=40)
            res_data = res.json()
            if "candidates" in res_data:
                text_response = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text_response.startswith("```json"): text_response = text_response[7:]
                if text_response.startswith("```"): text_response = text_response[3:]
                if text_response.endswith("```"): text_response = text_response[:-3]
                return json.loads(text_response.strip())
        except Exception as e:
            print(f"Error calling Gemini API: {e}")
            continue
    return {}

is_within_auto_hours = 630 <= current_total_minutes <= 1415
should_update = (trigger_event == "workflow_dispatch") or is_within_auto_hours

if should_update:
    market_data = fetch_all_data()
    ai_insights = generate_ai_insights(market_data)

    date_str = now_il.strftime("%d.%m.%Y")
    time_str = now_il.strftime("%H:%M")
    full_date_str = f"{date_str} בשעה {time_str}"

    sp500 = market_data.get("^GSPC", {})
    nasdaq = market_data.get("^IXIC", {})
    dji = market_data.get("^DJI", {})
    vix = market_data.get("^VIX", {})
    dxy = market_data.get("USDILS=X", {})

    sp500_price = format_num(sp500.get("price", 0))
    sp500_change = f"{sp500.get('change', 0):+.2f}%"
    nasdaq_price = format_num(nasdaq.get("price", 0))
    nasdaq_change = f"{nasdaq.get('change', 0):+.2f}%"
    dji_price = format_num(dji.get("price", 0))
    dji_change = f"{dji.get('change', 0):+.2f}%"
    vix_price = format_num(vix.get("price", 0))
    vix_change = f"{vix.get('change', 0):+.2f}%"
    dxy_price = format_num(dxy.get("price", 0))
    dxy_change = f"{dxy.get('change', 0):+.2f}%"
    usd_ils_rate = format_num(dxy.get("price", 3.08))

    oil_data = market_data.get("CL=F", {})
    oil_price = format_num(oil_data.get("price", 75.0))
    
    gold_data = market_data.get("GC=F", {})
    gold_price = format_num(gold_data.get("price", 2350.0))
    
    btc_data = market_data.get("BTC-USD", {})
    btc_price_val = format_num(btc_data.get("price", 65000.0))

    template_path = "template.html"
    html_path = "index.html"
    source_path = template_path if os.path.exists(template_path) else html_path

    if os.path.exists(source_path):
        with open(source_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        html_content = html_content.replace("{{LAST_UPDATED}}", full_date_str)
        html_content = html_content.replace("{{SP500_PRICE}}", sp500_price)
        html_content = html_content.replace("{{SP500_PCT}}", sp500_change)
        html_content = html_content.replace("{{NASDAQ_PRICE}}", nasdaq_price)
        html_content = html_content.replace("{{NASDAQ_PCT}}", nasdaq_change)
        html_content = html_content.replace("{{DOW_PRICE}}", dji_price)
        html_content = html_content.replace("{{DOW_PCT}}", dji_change)
        html_content = html_content.replace("{{VIX_PRICE}}", vix_price)
        html_content = html_content.replace("{{VIX_PCT}}", vix_change)
        html_content = html_content.replace("{{DXY_PRICE}}", dxy_price)
        html_content = html_content.replace("{{DXY_PCT}}", dxy_change)
        html_content = html_content.replace("{{USD_ILS_RATE}}", usd_ils_rate)
        html_content = html_content.replace("{{OIL_PRICE}}", oil_price)
        html_content = html_content.replace("{{GOLD_PRICE}}", gold_price)
        html_content = html_content.replace("{{BTC_PRICE}}", btc_price_val)

        html_content = html_content.replace("{{US_MARKET_NEWS}}", str(ai_insights.get("US_MARKET_MACRO_NEWS", "נתוני המאקרו ממשיכים להוות מנוע ניווט בשווקים.")))
        html_content = html_content.replace("{{IL_MARKET_NEWS}}", str(ai_insights.get("IL_MARKET_MACRO_NEWS", "השוק המקומי מגיב להתפתחויות הכלכליות.")))
        html_content = html_content.replace("{{SECTOR_CHIPS_DESC}}", str(ai_insights.get("SECTOR_CHIPS_DESC", "")))
        html_content = html_content.replace("{{SECTOR_CLOUD_DESC}}", str(ai_insights.get("SECTOR_CLOUD_DESC", "")))
        html_content = html_content.replace("{{SECTOR_CRYPTO_DESC}}", str(ai_insights.get("SECTOR_CRYPTO_DESC", "")))
        html_content = html_content.replace("{{SECTOR_CHIP_PERF}}", str(ai_insights.get("SECTOR_CHIP_PERF", "2.5")))
        html_content = html_content.replace("{{SECTOR_CLOUD_PERF}}", str(ai_insights.get("SECTOR_CLOUD_PERF", "1.5")))
        html_content = html_content.replace("{{SECTOR_CRYPTO_PERF}}", str(ai_insights.get("SECTOR_CRYPTO_PERF", "3.0")))

        html_content = html_content.replace("{{CATALYST_EARNINGS}}", str(ai_insights.get("CATALYST_EARNINGS", "")))
        html_content = html_content.replace("{{CATALYST_MONETARY}}", str(ai_insights.get("CATALYST_MONETARY", "")))
        html_content = html_content.replace("{{CATALYST_HARDWARE}}", str(ai_insights.get("CATALYST_HARDWARE", "")))
        html_content = html_content.replace("{{COMMUNITY_SENTIMENT}}", str(ai_insights.get("COMMUNITY_SENTIMENT", "")))
        html_content = html_content.replace("{{ANALYST_POINT_1}}", str(ai_insights.get("ANALYST_POINT_1", "")))
        html_content = html_content.replace("{{ANALYST_POINT_2}}", str(ai_insights.get("ANALYST_POINT_2", "")))
        html_content = html_content.replace("{{RISK_MANAGEMENT_TEXT}}", str(ai_insights.get("RISK_MANAGEMENT_TEXT", "")))
        html_content = html_content.replace("{{ACTION_RECOMMENDATIONS_TEXT}}", str(ai_insights.get("ACTION_RECOMMENDATIONS_TEXT", "")))

        for ticker in all_strategy_tickers:
            t_data = market_data.get(ticker, {})
            t_price = format_num(t_data.get("price", 0))
            t_change = f"{t_data.get('change', 0):+.2f}%"

            html_content = html_content.replace(f"{{{{{ticker}_LONG_PRICE}}}}", t_price)
            html_content = html_content.replace(f"{{{{{ticker}_LONG_PRE}}}}", t_price)
            html_content = html_content.replace(f"{{{{{ticker}_LONG_PCT}}}}", t_change)
            html_content = html_content.replace(f"{{{{{ticker}_LONG_TARGET}}}}", str(portfolio_buys.get(ticker, {}).get("target", 0)))
            html_content = html_content.replace(f"{{{{{ticker}_LONG_RATIONALE}}}}", str(ai_insights.get(f"{ticker}_RATIONALE", "מעקב שוטף אחר ביצועי החברה.")))

            html_content = html_content.replace(f"{{{{{ticker}_SWING_PRICE}}}}", t_price)
            html_content = html_content.replace(f"{{{{{ticker}_SWING_PRE}}}}", t_price)
            html_content = html_content.replace(f"{{{{{ticker}_SWING_PCT}}}}", t_change)
            html_content = html_content.replace(f"{{{{{ticker}_SWING_TARGET}}}}", str(portfolio_buys.get(ticker, {}).get("target", 0)))
            html_content = html_content.replace(f"{{{{{ticker}_SWING_TEXT}}}}", str(ai_insights.get(f"{ticker}_SWING_TEXT", "תנועת מחיר במעקב.")))
            html_content = html_content.replace(f"{{{{{ticker}_SWING_TEXT_2}}}}", str(ai_insights.get(f"{ticker}_SWING_TEXT", "תנועת מחיר במעקב.")))

            html_content = html_content.replace(f"{{{{{ticker}_PORT_CURRENT}}}}", f"${t_price}")
            html_content = html_content.replace(f"{{{{{ticker}_PORT_PRE}}}}", f"${t_price}")
            html_content = html_content.replace(f"{{{{{ticker}_PORT_TARGET}}}}", f"${portfolio_buys.get(ticker, {}).get('target', 0)}")
            html_content = html_content.replace(f"{{{{{ticker}_PORT_STATUS}}}}", "במעקב פעיל")
            html_content = html_content.replace(f"{{{{{ticker}_PORT_NOTE}}}}", str(ai_insights.get(f"{ticker}_PORT_NOTE", "פוזיציה מנוהלת בהתאם לאסטרטגיה.")))

            html_content = html_content.replace(f"{{{{{ticker}_NEWS_LINK}}}}", str(ai_insights.get(f"{ticker}_NEWS_LINK", "לא זמין כרגע")))
            html_content = html_content.replace(f"{{{{{ticker}_NEWS_TITLE}}}}", str(ai_insights.get(f"{ticker}_NEWS_TITLE", f"עדכון שוק עבור {ticker}")))
            html_content = html_content.replace(f"{{{{{ticker}_NEWS_CONTENT}}}}", str(ai_insights.get(f"{ticker}_NEWS_CONTENT", "אין חדשות דרמטיות כרגע.")))
            html_content = html_content.replace(f"{{{{{ticker}_NEWS_IMPACT}}}}", str(ai_insights.get(f"{ticker}_NEWS_IMPACT", "השפעה נייטרלית על המגמה.")))

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        print("index.html updated successfully from template with matching placeholders.")
    else:
        print("Template file not found!")
else:
    print("Skipping update based on schedule hours.")
