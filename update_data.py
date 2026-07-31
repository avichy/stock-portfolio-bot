from datetime import datetime
import json
import os
import subprocess
import traceback
import pytz
import requests
import yfinance as yf


def format_num(val, decimals=2):
    """מפרמט מספר עם פסיקים לאלפים ומספר ספרות אחרי הנקודה"""
    try:
        num = float(val)
        if decimals == 0:
            return f"{num:,.0f}"
        return f"{num:,.{decimals}f}"
    except (ValueError, TypeError):
        return str(val)


# הגדרת אזור זמן של ישראל
israel_tz = pytz.timezone("Asia/Jerusalem")
now_il = datetime.now(israel_tz)

current_date = now_il.date()
current_hour = now_il.hour
current_minute = now_il.minute
current_total_minutes = current_hour * 60 + current_minute

trigger_event = (
    os.environ.get("GITHUB_EVENT_NAME")
    or os.environ.get("TRIGGER_EVENT")
    or "schedule"
)

days_map = {
    0: "שני",
    1: "שלישי",
    2: "רביעי",
    3: "חמישי",
    4: "שישי",
    5: "שבת",
    6: "ראשון",
}
day_name = days_map[now_il.weekday()]

print(
    f"Current Israel Time: {now_il.strftime('%Y-%m-%d %H:%M')} - Day:"
    f" {day_name} - Event: {trigger_event}"
)

# רשימת כל הסימולים במערכת
all_strategy_tickers = [
    "NVDA",
    "AMD",
    "MU",
    "GOOG",
    "AMZN",
    "META",
    "MA",
    "WMT",
    "TTWO",
    "WDC",
    "TQQQ",
    "INTC",
    "IREN",
    "CIFR",
    "IBIT",
    "SIMO",
    "SNDK",
    "NFLX",
    "GTEC",
]

tickers_to_fetch = all_strategy_tickers + [
    "GC=F",
    "CL=F",
    "BTC-USD",
    "USDILS=X",
    "^GSPC",
    "^IXIC",
    "^DJI",
    "^VIX",
]


def fetch_all_data():
    """מושך נתוני מחיר ושינוי יומי מ-yfinance"""
    market_data = {}
    for ticker in tickers_to_fetch:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if not hist.empty:
                current_price = round(hist["Close"].iloc[-1], 2)
                prev_close = (
                    hist["Close"].iloc[-2] if len(hist) > 1 else current_price
                )
                change = round(
                    ((current_price - prev_close) / prev_close) * 100, 2
                )
                market_data[ticker] = {
                    "price": current_price,
                    "change": change,
                }
            else:
                market_data[ticker] = {"price": 0.0, "change": 0.0}
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            market_data[ticker] = {"price": 0.0, "change": 0.0}
    return market_data


# נתוני קנייה ומחיר יעד של התיק בסעיף 5
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
    "TQQQ": {"shares": 28, "buy": 56.53, "target": 75.0},
}


def generate_ai_insights(market_data):
    """פונה ל-Gemini API עם מנגנון גיבוי ומייצר את כל הטקסטים הדינמיים למערכת"""
    api_keys = [
        os.environ.get("GEMINI_API_KEY_1") or os.environ.get("GEMINI_API_KEY"),
        os.environ.get("GEMINI_API_KEY_2"),
    ]
    valid_keys = [k for k in api_keys if k]

    if not valid_keys:
        print("No GEMINI_API_KEY found. Skipping AI generation.")
        return {}

    prompt = (
        "אתה אנליסט בכיר בשוק ההון. ניתוח נתוני השוק החיים כרגע:\n"
        + json.dumps(market_data, ensure_ascii=False)
        + "\n\n"
        "**כללים קשיחים לחובה:**\n"
        "1. דרישת דיוק אנליטי ומספרי של לפחות 95%: עליך להקפיד על דיוק מקצועי גבוה ביותר, להסתמך אך ורק על נתוני הבסיס המסופקים מבלי להמציא או לשערך עובדות, ולוודא תאימות מוחלטת לנתוני השוק.\n"
        "2. פורמט מספרים: כל מספר מעל 1,000 חייב להיכתב תמיד עם פסיק מפריד אלפים (לדוגמה: 7,413.18 ולא 7413.18).\n\n"
        "החזר אובייקט JSON תקף בלבד (ללא טקסט עוטף או Markdown נוסף מעבר ל-JSON) הכולל את כל המפתחות הבאים בעברית מקצועית המותאמת למצב הנוכחי:\n"
        "- US_MARKET_MACRO_NEWS\n"
        "- IL_MARKET_MACRO_NEWS\n"
        "- SECTOR_CHIPS_DESC\n"
        "- SECTOR_CLOUD_DESC\n"
        "- SECTOR_CRYPTO_DESC\n"
        "- CATALYST_EARNINGS\n"
        "- CATALYST_MONETARY\n"
        "- CATALYST_HARDWARE\n"
        "- COMMUNITY_SENTIMENT\n"
        "- ANALYST_POINT_1\n"
        "- ANALYST_POINT_2\n"
        "- RISK_MANAGEMENT_TEXT\n"
        "- ACTION_RECOMMENDATIONS_TEXT\n\n"
        + f"וכמו כן, עבור כל אחד מהסימולים הבאים ({', '.join(all_strategy_tickers)}), הוסף מפתחות ניתוח וחדשות:\n"
        "1. [TICKER]_RATIONALE\n"
        "2. [TICKER]_SWING_TEXT\n"
        "3. [TICKER]_NEWS_TITLE\n"
        "4. [TICKER]_NEWS_CONTENT\n"
        "5. [TICKER]_NEWS_IMPACT\n"
        "6. [TICKER]_NEWS_LINK\n"
        "7. [TICKER]_PORT_NOTE"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"},
    }

    for i, api_key in enumerate(valid_keys, 1):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
            res = requests.post(url, json=payload, timeout=40)
            res_data = res.json()

            if "candidates" in res_data:
                text_response = (
                    res_data["candidates"][0]["content"]["parts"][0]["text"]
                )

                text_response = text_response.strip()
                if text_response.startswith("```json"):
                    text_response = text_response[7:]
                if text_response.startswith("```"):
                    text_response = text_response[3:]
                if text_response.endswith("```"):
                    text_response = text_response[:-3]
                text_response = text_response.strip()

                print(
                    f"Successfully generated full dynamic AI insights using API Key #{i}"
                )
                return json.loads(text_response)

            error_code = res_data.get("error", {}).get("code")
            if error_code == 429:
                print(
                    f"API Key #{i} exceeded quota (429). Switching to next key..."
                )
                continue
            else:
                print(f"API Key #{i} Error Response: {res_data}")
                continue

        except Exception as e:
            print(f"Error calling Gemini API with key #{i}: {e}")
            continue

    print("All API keys failed or exceeded quota.")
    return {}


# מעדכן תמיד בכל הרצה
should_update = True

if should_update:
    try:
        market_data = fetch_all_data()
        ai_insights = generate_ai_insights(market_data)

        date_str = now_il.strftime("%d.%m.%Y")
        time_str = now_il.strftime("%H:%M")

        sp500 = market_data.get("^GSPC", {})
        nasdaq = market_data.get("^IXIC", {})
        dji = market_data.get("^DJI", {})
        vix = market_data.get("^VIX", {})
        dxy = market_data.get("USDILS=X", {})

        sp500_price = format_num(sp500.get("price", 0))
        sp500_change = f"{sp500.get('change', 0)}%"

        nasdaq_price = format_num(nasdaq.get("price", 0))
        nasdaq_change = f"{nasdaq.get('change', 0)}%"

        dji_price = format_num(dji.get("price", 0))
        dji_change = f"{dji.get('change', 0)}%"

        vix_price = format_num(vix.get("price", 0))
        vix_change = f"{vix.get('change', 0)}%"

        dxy_price = format_num(dxy.get("price", 0))
        dxy_change = f"{dxy.get('change', 0)}%"

        usd_ils_price = format_num(
            market_data.get("USDILS=X", {}).get("price", 3.65)
        )
        usd_ils_change = f"{market_data.get('USDILS=X', {}).get('change', 0)}%"

        oil_price = format_num(market_data.get("CL=F", {}).get("price", 75.0))
        oil_change = f"{market_data.get('CL=F', {}).get('change', 0)}%"

        gold_price = format_num(
            market_data.get("GC=F", {}).get("price", 2350.0)
        )
        gold_change = f"{market_data.get('GC=F', {}).get('change', 0)}%"

        btc_price = f"${format_num(market_data.get('BTC-USD', {}).get('price', 65000.0))}"
        btc_change = f"{market_data.get('BTC-USD', {}).get('change', 0)}%"

        replacements = {
            "LAST_UPDATED": f"{date_str} | {time_str}",
            "DAY_NAME": day_name,
            "SNP_500_LEVEL": sp500_price,
            "SP500_PRICE": sp500_price,
            "SP500_LEVEL": sp500_price,
            "SNP_500_CHANGE": sp500_change,
            "SP500_CHANGE": sp500_change,
            "SP500_PCT": sp500_change,
            "NASDAQ_LEVEL": nasdaq_price,
            "NASDAQ_PRICE": nasdaq_price,
            "NASDAQ_CHANGE": nasdaq_change,
            "NASDAQ_PCT": nasdaq_change,
            "DJI_LEVEL": dji_price,
            "DJI_PRICE": dji_price,
            "DJI_CHANGE": dji_change,
            "DJI_PCT": dji_change,
            "DOW_PRICE": dji_price,
            "DOW_PCT": dji_change,
            "VIX_LEVEL": vix_price,
            "VIX_PRICE": vix_price,
            "VIX_CHANGE": vix_change,
            "VIX_PCT": vix_change,
            "DXY_LEVEL": dxy_price,
            "DXY_PRICE": dxy_price,
            "DXY_CHANGE": dxy_change,
            "DXY
