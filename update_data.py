import base64
from datetime import datetime
import json
import os
import re
import time
import traceback
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import feedparser
from groq import Groq
import pytz
import requests

# וידוא שספריית yfinance קיימת (מותקנת אוטומטית במידת הצורך ב-GitHub Actions)
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


def clean_json_response(text):
    """ניקוי תגיות Markdown מתגובת AI לקבלת מחרוזת JSON תקינה"""
    if not text:
        return "{}"
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
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


def load_ai_cache():
    if os.path.exists(AI_CACHE_FILE):
        try:
            with open(AI_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Error loading AI cache: {e}")
    return {}


def save_ai_cache(data):
    try:
        with open(AI_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        print("Successfully saved AI cache.")
    except Exception as e:
        print(f"Warning: Error saving AI cache: {e}")


def load_portfolio_buys():
    if GITHUB_TOKEN and GITHUB_REPO:
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{PORTFOLIO_FILE}"
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                file_data = response.json()
                raw_content = file_data.get("content", "").replace("\n", "").strip()
                missing_padding = len(raw_content) % 4
                if missing_padding:
                    raw_content += "=" * (4 - missing_padding)
                content = base64.b64decode(raw_content.encode("utf-8")).decode("utf-8")
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    return parsed
        except Exception as e:
            print(f"Warning: Error loading from GitHub API: {e}")

    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                parsed = json.load(f)
                if isinstance(parsed, dict):
                    return parsed
        except Exception as e:
            print(f"Warning: Error loading local portfolio.json: {e}")
    return {}


portfolio_buys = load_portfolio_buys()


def fetch_us_market_news():
    """שליפת חדשות שוק אמריקאי מ-Google News RSS עם קישורים ומבנה מסודר"""
    try:
        query = "Wall Street stock market S&P 500 Nasdaq economy breaking news Fed"
        encoded_query = urllib.parse.quote_plus(query)
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"

        feed = feedparser.parse(url)
        news_items = []

        for entry in feed.entries[:10]:
            title = entry.get("title", "")
            summary = entry.get("summary", "")
            link = entry.get("link", "https://news.google.com")
            if title:
                news_items.append({
                    "title": title,
                    "summary": summary,
                    "link": link,
                    "source": "Google News RSS",
                })

        return news_items
    except Exception as e:
        print(f"Error fetching US news: {e}")
        return []


def get_filtered_us_news(headlines):
    """סינון חכם לחדשות ארה"ב - מתן עדיפות למאקרו, פד, גיאופוליטיקה ואירועי שוק"""
    keywords = ["fed", "rate", "s&p", "nasdaq", "dow", "inflation", "stock", "market", "economy", "tech", "earnings"]
    filtered = []
    for item in headlines:
        title = item.get("title", "").lower()
        if any(kw in title for kw in keywords):
            filtered.append(item)
    return filtered if filtered else headlines[:5]


def fetch_stock_prices(symbols):
    """שליפת נתוני מניות עדכניים מ-yfinance"""
    data = {}
    if not symbols:
        return data

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.fast_info
            price = info.get("lastPrice") or info.get("regularMarketPrice") or 0.0
            prev_close = info.get("previousClose") or price
            change = price - prev_close
            change_percent = (change / prev_close * 100) if prev_close else 0.0

            data[symbol] = {
                "symbol": symbol,
                "price": round(price, 2),
                "change": round(change, 2),
                "change_percent": round(change_percent, 2),
                "currency": "USD"
            }
        except Exception as e:
            print(f"Error fetching stock data for {symbol}: {e}")
            data[symbol] = {
                "symbol": symbol,
                "price": 0.0,
                "change": 0.0,
                "change_percent": 0.0,
                "currency": "USD"
            }
    return data


def generate_ai_analysis(news_items, stocks_data):
    """יצירת ניתוח AI באמצעות מפתחות Groq הזמינים ומודל gpt-oss-120b"""
    groq_keys = get_all_groq_keys()
    if not groq_keys:
        print("No Groq API keys found. Skipping AI analysis.")
        return "ניתוח AI אינו זמין כרגע (לא הוגדרו מפתחות API)."

    prompt = f"""
    אתה אנליסט פיננסי בכיר. נתח בקצרה בעברית את תמונת המצב הנוכחית בשוק על בסיס הנתונים הבאים:
    מניות עיקריות: {json.dumps(stocks_data, ensure_ascii=False)}
    חדשות אחרונות: {json.dumps([n['title'] for n in news_items[:5]], ensure_ascii=False)}

    ספק סיכום ממוקד (עד 3 פסקאות קצרות) על מגמת השוק, אירועים מרכזיים והשפעתם.
    """

    for key_name, api_key in groq_keys:
        try:
            client = Groq(api_key=api_key)
            response = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
                max_tokens=600,
            )
            analysis = response.choices[0].message.content
            print(f"Successfully generated AI summary using {key_name}")
            return analysis
        except Exception as e:
            print(f"Failed using key {key_name}: {e}")

    return "לא ניתן היה ליצור ניתוח AI בעת זו."


def render_html(stocks_data, news_items, ai_summary, last_updated):
    """יצירת קובץ index.html מתוך התבנית index.template.html"""
    template_content = ""
    
    if os.path.exists(TEMPLATE_FILE):
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            template_content = f.read()
    else:
        print(f"Warning: {TEMPLATE_FILE} not found. Generating basic fallback HTML.")
        template_content = """<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>תיק השקעות ועדכוני שוק</title>
    <style>
        body { font-family: system-ui, sans-serif; margin: 20px; background: #f4f6f8; color: #333; }
        .card { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .positive { color: green; } .negative { color: red; }
    </style>
</head>
<body>
    <h1>לוח בקרה - שוק ההון</h1>
    <p>עדכון אחרון: {{LAST_UPDATED}}</p>
    <div class="card">
        <h2>ניתוח בינה מלאכותית</h2>
        <div>{{AI_SUMMARY}}</div>
    </div>
    <div class="card">
        <h2>מניות</h2>
        <pre>{{STOCKS_DATA}}</pre>
    </div>
    <div class="card">
        <h2>חדשות</h2>
        <pre>{{NEWS_DATA}}</pre>
    </div>
</body>
</html>"""

    output_html = template_content.replace("{{LAST_UPDATED}}", last_updated)
    output_html = output_html.replace("{{AI_SUMMARY}}", ai_summary.replace("\n", "<br>"))
    output_html = output_html.replace("{{STOCKS_DATA}}", json.dumps(stocks_data, ensure_ascii=False, indent=2))
    output_html = output_html.replace("{{NEWS_DATA}}", json.dumps(news_items, ensure_ascii=False, indent=2))
    output_html = output_html.replace("{{PORTFOLIO_JSON}}", json.dumps(portfolio_buys, ensure_ascii=False, indent=2))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(output_html)

    print(f"Successfully generated {OUTPUT_FILE}")


def main():
    print("Starting update process...")
    israel_tz = pytz.timezone("Asia/Jerusalem")
    now_str = datetime.now(israel_tz).strftime("%d/%m/%Y %H:%M:%S")

    # 1. הגדרת רשימת מניות לשליפה
    default_symbols = ["AMD", "MU", "WDC", "NVDA", "BE", "TQQQ", "INTC", "WMT"]
    portfolio_symbols = list(portfolio_buys.keys()) if portfolio_buys else []
    all_symbols = list(set(default_symbols + portfolio_symbols))

    # 2. שליפת נתוני מניות וחדשות
    stocks_data = fetch_stock_prices(all_symbols)
    raw_news = fetch_us_market_news()
    filtered_news = get_filtered_us_news(raw_news)

    # 3. ניהול AI Cache וניתוח
    ai_cache = load_ai_cache()
    ai_summary = generate_ai_analysis(filtered_news, stocks_data)
    ai_cache["last_summary"] = ai_summary
    ai_cache["last_updated"] = now_str
    save_ai_cache(ai_cache)

    # 4. יצירת קובץ ה-index.html הסופי
    render_html(stocks_data, filtered_news, ai_summary, now_str)
    print("Update process completed successfully.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Fatal Error in main execution: {e}")
        traceback.print_exc()
