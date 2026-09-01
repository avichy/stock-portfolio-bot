import base64
from datetime import datetime
import json
import os
import re
import time
import traceback
import urllib.parse
import urllib.request
from bs4 import BeautifulSoup
import feedparser
from groq import Groq
import pytz
import requests

# וידוא שספריית yfinance קיימת
try:
    import yfinance as yf
except ImportError:
    os.system("pip install yfinance")
    import yfinance as yf

AI_CACHE_FILE = "ai_cache.json"
PORTFOLIO_FILE = "portfolio.json"
TEMPLATE_FILE = "index.template.html"
OUTPUT_FILE = "index.html"

GITHUB_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")

HEBREW_DAYS = {
    "Monday": "שני",
    "Tuesday": "שלישי",
    "Wednesday": "רביעי",
    "Thursday": "חמישי",
    "Friday": "שישי",
    "Saturday": "שבת",
    "Sunday": "ראשון",
}


def clean_json_response(text):
    """ניקוי תגיות Markdown לקבלת JSON תקין ללא תקלות מחרוזת"""
    if not text:
        return "{}"
    text = text.strip()
    # \x60 מייצג תו backtick למניעת בעיות העתקה
    text = re.sub(r"^\x60\x60\x60(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\x60\x60\x60$", "", text)
    return text.strip()


def get_all_groq_keys():
    keys_env = [
        "GROQ_API_KEY",
        "GROQ_API_KEY_1",
        "GROQ_API_KEY_2",
        "GROQ_API_KEY_3",
        "GROQ_API_KEY_4",
        "GROQ_API_KEY_5",
    ]
    valid_keys = []
    for key_name in keys_env:
        api_key = os.environ.get(key_name)
        if api_key:
            valid_keys.append((key_name, api_key))
    return valid_keys


def fetch_macro_data():
    """שליפת מדדי מאקרו, מטבעות וסחורות מ-yfinance"""
    symbols = {
        "SP500": "^GSPC",
        "NASDAQ": "^IXIC",
        "DOW": "^DJI",
        "VIX": "^VIX",
        "DXY": "DX-Y.NYB",
        "OIL": "CL=F",
        "GOLD": "GC=F",
        "BTC": "BTC-USD",
        "USD_ILS": "ILS=X",
    }

    results = {}
    for key, sym in symbols.items():
        try:
            ticker = yf.Ticker(sym)
            info = ticker.fast_info
            price = info.get("lastPrice") or info.get("regularMarketPrice") or 0.0
            prev_close = info.get("previousClose") or price
            change = price - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0.0

            results[key] = {
                "price": round(price, 2),
                "change": round(change, 2),
                "pct": round(change_pct, 2),
            }
        except Exception as e:
            print(f"Error fetching {key} ({sym}): {e}")
            results[key] = {"price": 0.0, "change": 0.0, "pct": 0.0}
    return results


def fetch_news(query, count=5):
    """שליפת מבזקי חדשות לפי שאילתה מ-Google News RSS"""
    try:
        encoded = urllib.parse.quote_plus(query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=he&gl=IL&ceid=IL:he"
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:count]:
            items.append({
                "title": entry.get("title", ""),
                "link": entry.get("link", "#")
            })
        return items
    except Exception as e:
        print(f"Error fetching news for {query}: {e}")
        return []


def generate_ai_insights(macro_data, us_news, il_news):
    """קריאה ל-Groq לקבלת הסברים קצרים בעברית לכל ה-Placeholders בתבנית"""
    groq_keys = get_all_groq_keys()
    if not groq_keys:
        return None

    prompt = f"""
    אתה אנליסט פיננסי בכיר. החזר תשובה בפורמט JSON בלבד.
    ספק הסברים קצרים בעברית (עד 15 מילים לכל סעיף) על משמעות השינוי:

    הפתחות ה-JSON הנדרשות:
    - SP500_ANALYSIS
    - NASDAQ_ANALYSIS
    - DOW_ANALYSIS
    - VIX_ANALYSIS
    - DXY_ANALYSIS
    - OIL_EXPLANATION
    - USD_ILS_EXPLANATION
    - BTC_EXPLANATION
    - GOLD_EXPLANATION
    - US_MARKET_NEWS
    - IL_MARKET_NEWS

    נתוני שוק:
    {json.dumps(macro_data, ensure_ascii=False)}

    חדשות ארה"ב: {[n['title'] for n in us_news[:3]]}
    חדשות ישראל: {[n['title'] for n in il_news[:3]]}
    """

    for key_name, api_key in groq_keys:
        try:
            client = Groq(api_key=api_key)
            response = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=1000,
            )
            raw_text = clean_json_response(response.choices[0].message.content)
            parsed = json.loads(raw_text)
            print(f"Successfully generated AI insights with {key_name}")
            return parsed
        except Exception as e:
            print(f"Groq API error with key {key_name}: {e}")
    return None


def main():
    print("Starting comprehensive update script...")
    israel_tz = pytz.timezone("Asia/Jerusalem")
    now = datetime.now(israel_tz)
    now_str = now.strftime("%d/%m/%Y %H:%M:%S")
    day_name = HEBREW_DAYS.get(now.strftime("%A"), "")

    # 1. שליפת נתונים
    macro = fetch_macro_data()
    us_news = fetch_news("Wall Street stock market S&P 500 Nasdaq Fed")
    il_news = fetch_news("שוק ההון הבורסה בתל אביב דולר שקל")

    # 2. ניתוח AI
    ai_data = generate_ai_insights(macro, us_news, il_news) or {}

    def fmt_pct(val):
        sign = "+" if val > 0 else ""
        return f"{sign}{val}%"

    def fmt_price(val):
        return f"{val:,.2f}" if isinstance(val, (int, float)) else str(val)

    # 3. החלפת Placeholders עבור index.template.html
    replacements = {
        "{{DAY_NAME}}": f"יום {day_name}" if day_name else "",
        "{{LAST_UPDATED}}": now_str,
        "{{AI_LAST_UPDATED}}": now_str,
        # S&P 500
        "{{SP500_PRICE}}": fmt_price(macro["SP500"]["price"]),
        "{{SP500_PCT}}": fmt_pct(macro["SP500"]["pct"]),
        "{{SP500_ANALYSIS}}": ai_data.get("SP500_ANALYSIS", "מסחר יציב במדד S&P 500."),
        # NASDAQ
        "{{NASDAQ_PRICE}}": fmt_price(macro["NASDAQ"]["price"]),
        "{{NASDAQ_PCT}}": fmt_pct(macro["NASDAQ"]["pct"]),
        "{{NASDAQ_ANALYSIS}}": ai_data.get("NASDAQ_ANALYSIS", "תנודתיות במניות הטכנולוגיה."),
        # DOW
        "{{DOW_PRICE}}": fmt_price(macro["DOW"]["price"]),
        "{{DOW_PCT}}": fmt_pct(macro["DOW"]["pct"]),
        "{{DOW_ANALYSIS}}": ai_data.get("DOW_ANALYSIS", "מגמה במניות התעשייה והערך."),
        # VIX
        "{{VIX_PRICE}}": fmt_price(macro["VIX"]["price"]),
        "{{VIX_PCT}}": fmt_pct(macro["VIX"]["pct"]),
        "{{VIX_ANALYSIS}}": ai_data.get("VIX_ANALYSIS", "מדד הפחד משקף את תנודתיות השוק."),
        # DXY
        "{{DXY_PRICE}}": fmt_price(macro["DXY"]["price"]),
        "{{DXY_PCT}}": fmt_pct(macro["DXY"]["pct"]),
        "{{DXY_ANALYSIS}}": ai_data.get("DXY_ANALYSIS", "מדד הדולר מול סל המטבעות העולמי."),
        # OIL
        "{{OIL_PRICE}}": f"${fmt_price(macro['OIL']['price'])}",
        "{{OIL_CHANGE}}": fmt_pct(macro["OIL"]["pct"]),
        "{{OIL_EXPLANATION}}": ai_data.get("OIL_EXPLANATION", "תנודות במחירי הנפט והאנרגיה."),
        # USD / ILS
        "{{USD_ILS}}": f"₪{fmt_price(macro['USD_ILS']['price'])}",
        "{{USD_ILS_CHANGE}}": fmt_pct(macro["USD_ILS"]["pct"]),
        "{{USD_ILS_EXPLANATION}}": ai_data.get("USD_ILS_EXPLANATION", "שער החליפין דולר/שקל."),
        # BTC
        "{{BTC_PRICE}}": f"${fmt_price(macro['BTC']['price'])}",
        "{{BTC_CHANGE}}": fmt_pct(macro["BTC"]["pct"]),
        "{{BTC_EXPLANATION}}": ai_data.get("BTC_EXPLANATION", "מגמת המסחר בשוק הקריפטו."),
        # GOLD
        "{{GOLD_PRICE}}": f"${fmt_price(macro['GOLD']['price'])}",
        "{{GOLD_CHANGE}}": fmt_pct(macro["GOLD"]["pct"]),
        "{{GOLD_EXPLANATION}}": ai_data.get("GOLD_EXPLANATION", "הזהב כנכס מקלט בטוח."),
        # NEWS
        "{{US_MARKET_NEWS}}": ai_data.get("US_MARKET_NEWS", "<br>".join([f"• {item['title']}" for item in us_news[:3]]) if us_news else "אין עדכונים חדשים"),
        "{{IL_MARKET_NEWS}}": ai_data.get("IL_MARKET_NEWS", "<br>".join([f"• {item['title']}" for item in il_news[:3]]) if il_news else "אין עדכונים חדשים"),
    }

    # 4. כתיבת index.html
    if os.path.exists(TEMPLATE_FILE):
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            content = f.read()

        for key, value in replacements.items():
            content = content.replace(key, str(value))

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        print("Successfully generated index.html!")
    else:
        print(f"Error: {TEMPLATE_FILE} was not found.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()
