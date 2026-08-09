import base64
from datetime import datetime
import json
import os
import subprocess
import time
import traceback
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import pytz
import requests
import yfinance as yf
from groq import Groq

AI_CACHE_FILE = "ai_cache.json"
PORTFOLIO_FILE = "portfolio.json"
TEMPLATE_FILE = "index.template.html"
OUTPUT_FILE = "index.html"

GITHUB_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")

def get_all_groq_keys():
    keys_env = ["GROQ_API_KEY", "GROQ_API_KEY_1", "GROQ_API_KEY_2", "GROQ_API_KEY_3", "GROQ_API_KEY_4", "GROQ_API_KEY_5"]
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
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                file_data = response.json()
                content = base64.b64decode(file_data["content"]).decode("utf-8")
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
        return f"<span style='color: {color}; font-weight: bold;'>{sign}{num:.2f}%</span>"
    except (ValueError, TypeError):
        return str(val)

def get_stock_logo_url(ticker):
    clean_ticker = str(ticker).strip().upper()
    return f"https://assets.parqet.com/logos/symbol/{clean_ticker}"

def fetch_investing_news():
    url = "https://www.investing.com/rss/news.rss"
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            news_items = []
            for item in root.findall('.//item'):
                title = item.find('title')
                link = item.find('link')
                if title is not None and title.text:
                    item_title = title.text
                    item_link = link.text if link is not None and link.text else "https://www.investing.com/news/latest-news"
                    news_items.append({"title": item_title, "link": item_link})
            print(f"Successfully fetched {len(news_items)} headlines with links from Investing.com RSS.")
            return news_items[:20]
    except Exception as e:
        print(f"Warning: Error fetching Investing RSS: {e}")
        return []

LT_STOCKS_META = [
    {"ticker": "MSFT", "name": "Microsoft Corporation", "desc": "ענן Azure, תוכנה, פתרונות AI וטכנולוגיה עסקית גלובלית.", "news": "התרחבות עקבית בשירותי ענן ובינה מלאכותית ארגונית, יציבות פיננסית גבוהה."},
    {"ticker": "JPM", "name": "JPMorgan Chase & Co.", "desc": "בנקאות מסחרית והשקעות מובילה בארה\"ב ובעולם (סקטור הפיננסים).", "news": "תוצאות חזקות וניהול סיכונים קפדני תחת סביבת ריבית משתנה, עוגן חזק בתיק."},
    {"ticker": "JNJ", "name": "Johnson & Johnson", "desc": "פיתוח תרופות, ציוד רפואי ומוצרי בריאות הצרכן (סקטור הבריאות).", "news": "חסינות עסקית גבוהה מול מחזוריות השוק, חלוקת דיבידנדים יציבה ואמינה."},
    {"ticker": "XOM", "name": "Exxon Mobil Corporation", "desc": "חיפוש, הפקה ואנרגיה קונבנציונלית ומתקדמת (סקטור האנרגיה).", "news": "תזרים מזומנים חזק ויעילות תפעולית גבוהה התומכת בתשואות אטרקטיביות למשקיעים."},
    {"ticker": "WMT", "name": "Walmart Inc.", "desc": "רשת הקמעונאות והמרכולים הגדולה בעולם (סקטור צרכנות בסיסית).", "news": "ביקושים יציבים בכל תנאי מאקרו וצמיחה מרשימה בפעילות המסחר האלקטרוני."},
    {"ticker": "AMZN", "name": "Amazon.com, Inc.", "desc": "מסחר אלקטרוני גלובלי ושירותי ענן מובילים (AWS).", "news": "שיפור מתמיד בשולי הרווח התפעולי של AWS והתייעלות לוגיסטית רחבת היקף."},
    {"ticker": "UNH", "name": "UnitedHealth Group", "desc": "שירותי ביטוח בריאות וניהול רפואי מתקדם.", "news": "צמיחה עקבית במספר המבוטחים וביקוש קשיח לשירותי בריאות וניהול סיכונים רפואיים."},
    {"ticker": "PG", "name": "Procter & Gamble", "desc": "ייצור ושיווק מוצרי צריכה ביתיים ואישיים מובילים.", "news": "כוח תמחור חזק אל מול אינפלציה ומותגים גלובליים חזקים המבטיחים יציבות."},
    {"ticker": "CVX", "name": "Chevron Corporation", "desc": "אנרגיה, נפט וגז טבעי בפעילות גלובלית רחבה.", "news": "מאזן פיננסי איתן ופרויקטי הפקה חדשים המחזקים את יכולות החלוקה למשקיעים."},
    {"ticker": "BRK-B", "name": "Berkshire Hathaway", "desc": "חברת אחזקות רב-תחומית המנוהלת בהשקעות ערך קלאסיות.", "news": "נזילות עצומה ופורטפוליו מבוזר של עסקים ראשיים המעניקים ביטחון למשקיע ארוך טווח."}
]

SW_STOCKS_META = [
    {"ticker": "TSLA", "name": "Tesla, Inc.", "desc": "רכבים חשמליים, אנרגיה מתחדשת ופתרונות אוטונומיה (סקטור צרכנות מחזורית).", "news": "תנודתיות גבוהה המייצרת הזדמנויות מסחר יומי וסווינג עם מומנטום חזק."},
    {"ticker": "AMD", "name": "Advanced Micro Devices", "desc": "פיתוח מעבדים, שבבים וכרטיסים גרפיים לשוק הטכנולוגיה.", "news": "תנועות מחיר חדות סביב השקות מוצרים ודו\"חות רבעוניים בסקטור השבבים."},
    {"ticker": "COIN", "name": "Coinbase Global, Inc.", "desc": "פלטפורמת מסחר מובילה בנכסים דיגיטליים וקריפטו (פיננסים/אלטרנטיבי).", "news": "קורלציה ישירה לתנודתיות בשוק הקריפטו, מעולה למסחר סווינג תנודתי קצר."},
    {"ticker": "OXY", "name": "Occidental Petroleum", "desc": "חברת אנרגיה וחיפושי נפט וגז עם עניין מוסדי רב.", "news": "מעקב צמוד אחר מחירי הסחורות והאנרגיה המייצרים מהלכים מהירים במסחר."},
    {"ticker": "PLTR", "name": "Palantir Technologies", "desc": "תוכנות אנליטיקה ובינה מלאכותית למגזר העסקי והביטחוני.", "news": "נפחי מסחר גבוהים מאוד ומומנטום חיובי המושך סוחרים לטווח הקצר והבינוני."},
    {"ticker": "NVO", "name": "Novo Nordisk A/S", "desc": "תרופות חדשניות לטיפול בסוכרת וניהול משקל (סקטור הבריאות).", "news": "ביקושים אדירים למוצרי הדגל של החברה, יוצר תנודות מחיר מעניינות למסחר."},
    {"ticker": "PYPL", "name": "PayPal Holdings, Inc.", "desc": "שירותי תשלומים דיגיטליים ופינטק גלובליים.", "news": "התאוששות מבנית ושינויים באסטרטגיית הצמיחה המייצרים הזדמנויות סווינג."},
    {"ticker": "BA", "name": "The Boeing Company", "desc": "תעופה, ביטחון וייצור מטוסים מסחריים וצבאיים (סקטור התעשייה).", "news": "רגישות גבוהה לחדשות תפעוליות ורגולטוריות המייצרות פערים ותנועות חדות."},
    {"ticker": "NEM", "name": "Newmont Corporation", "desc": "חברת כריית הזהב הגדולה בעולם (סקטור חומרי גלם וגידור).", "news": "תנועה מנוגדת לרוב לשוק המניות, משמשת ככלי מסחר מצוין סביב מחירי הזהב."},
    {"ticker": "TQQQ", "name": "ProShares UltraPro QQQ", "desc": "תעודת סל ממונפת פי 3 על מדד הנאסד\"ק.", "news": "כלי מסחר יומי מובהק המבוסס על תנודתיות גבוהה ומינוף לטווח קצר."}
]

def fetch_ai_insights_from_groq(market_data, portfolio_stocks, date_str, day_name, investing_headlines):
    api_keys = get_all_groq_keys()
    if not api_keys:
        print("❌ ERROR: No Groq API keys found! Using cached/defaults.")
        cached = load_ai_cache()
        return cached if cached else {}

    max_rounds = 2  # מגביל ל-2 סבבים מלאים על כל המפתחות
    for attempt_round in range(1, max_rounds + 1):
        print(f"🔄 Starting Groq AI request round {attempt_round}/{max_rounds}...")
        for key_name, api_key in api_keys:
            try:
                client = Groq(api_key=api_key)
                print(f"🤖 Connecting to Groq AI using {key_name} for {day_name}, {date_str}...")
                
                market_summary = {t: f"Price: {d.get('price')}, Change: {d.get('change')}%" for t, d in market_data.items()}
                portfolio_tickers = list(portfolio_stocks.keys())
                headlines_formatted = "\n".join([f"- כותרת: {h['title']} | קישור: {h['link']}" for h in investing_headlines]) if investing_headlines else "לא התקבלו כותרות כרגע."

                prompt = f"""
You must output valid JSON.
אתה אנליסט שוק הון בכיר וגלובלי. היום הוא {day_name}, בתאריך {date_str}.

להלן כותרות חדשות וקישורים עדכניים מתוך אתר Investing.com:
{headlines_formatted}

על בסיס כותרות אלו ונתוני השוק הנוכחיים הבאים להיום:
{json.dumps(market_summary, ensure_ascii=False)}

ועבור מניות התיק האישי של המשתמש: {portfolio_tickers}

הנחיות קריטיות:
1. עדכניות יומית מוחלטת ליום {date_str}.
2. החזר אובייקט JSON תקין הכולל בדיוק את המפתחות הבאים בעברית מקצועית לשוק ההון:
1. SP500_ANALYSIS
2. NASDAQ_ANALYSIS
3. DOW_ANALYSIS
4. VIX_ANALYSIS
5. DXY_ANALYSIS
6. USD_ILS_EXPLANATION
7. OIL_EXPLANATION
8. GOLD_EXPLANATION
9. BTC_EXPLANATION
10. US_MARKET_NEWS: פסקה מפורטת, רחבה ועשירה של לפחות 3-4 משפטים המנתחת בהרחבה את מצב השוק האמריקאי, נתוני המאקרו, והשפעות הריבית והאינפלציה.
11. IL_MARKET_NEWS: פסקה מפורטת, רחבה ועשירה של לפחות 3-4 משפטים המנתחת בהרחבה את מצב השוק הישראלי, שער החליפין, וההשפעות הגיאופוליטיות והכלכליות המקומיות.
12. CATALYST_EARNINGS
13. CATALYST_MONETARY
14. CATALYST_HARDWARE
15. COMMUNITY_SENTIMENT
16. ANALYST_POINT_1
17. ANALYST_POINT_2
18. RISK_MANAGEMENT_TEXT
19. ACTION_RECOMMENDATIONS_TEXT
20. long_term_stocks: מערך (array) של בדיוק 10 מניות מומלצות להשקעה ארוכת טווח (טיקר, שם, תיאור, חדשות).
21. swing_stocks: מערך (array) של בדיוק 10 מניות מומלצות למסחר סווינג (טיקר, שם, תיאור, חדשות).
22. portfolio_analysis: אובייקט שבו המפתחות חייבים להיות בדיוק הטיקרים של מניות התיק האישי של המשתמש ({portfolio_tickers}). עבור כל טיקר, הספק אובייקט הכולל: rationale, news_link, news_title, news_content, news_impact.
23. market_news: מערך של 5 ידיעות חדשותיות שונות לחלוטין זו מזו מתוך הכותרות שסופקו למעלה. כל פריט חייב לכלול: news_link, news_title, news_content, news_impact.
"""

                response = client.chat.completions.create(
                    model='llama-3.3-70b-versatile',
                    messages=[
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"}
                )
                
                raw_text = response.choices[0].message.content.strip()
                print("--- RAW AI RESPONSE RECEIVED ---")
                print(raw_text[:600] + "..." if len(raw_text) > 600 else raw_text)
                print("--------------------------------")

                parsed_ai_data = json.loads(raw_text)
                parsed_ai_data["ai_updated_at"] = f"{date_str} | {time_str}"
                print("Successfully parsed AI response into JSON using key:", key_name)
                return parsed_ai_data

            except Exception as e:
                print(f"⚠️ Attempt failed with {key_name}: {e}")
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e) or "rate_limit_exceeded" in str(e):
                    print(f"⏳ Rate limit hit on {key_name}. Waiting 65 seconds for minute limit to reset...")
                    time.sleep(65)  # המתנה של מעל דקה כדי לתת למגבלת הדקה להתאפס
                else:
                    print(f"🔄 Connection/Network error. Waiting 5 seconds before trying next key...")
                    time.sleep(5)

    print("⚠️ All AI retries and keys exhausted across all rounds. Falling back to cache.")
    cached = load_ai_cache()
    return cached if cached else {}

israel_tz = pytz.timezone("Asia/Jerusalem")
now_il = datetime.now(israel_tz)
day_name = {
    0: "שני", 1: "שלישי", 2: "רביעי", 3: "חמישי", 4: "שישי", 5: "שבת", 6: "ראשון",
}[now_il.weekday()]

sector_tickers_map = {
    "INFO_TECH": "XLK",
    "FINANCIALS": "XLF",
    "HEALTH": "XLV",
    "CONS_DISC": "XLY",
    "CONS_STAPLES": "XLP",
    "ENERGY": "XLE",
    "INDUSTRIALS": "XLI",
    "MATERIALS": "XLB",
    "COMM": "XLC",
    "UTILITIES": "XLU",
    "REAL_ESTATE": "XLRE"
}

cached_ai_init = load_ai_cache()
init_lt = cached_ai_init.get("long_term_stocks", LT_STOCKS_META)
init_sw = cached_ai_init.get("swing_stocks", SW_STOCKS_META)

base_market_tickers = list(set(
    ["GC=F", "CL=F", "BTC-USD", "USDILS=X", "DX-Y.NYB", "^GSPC", "^NDX", "^DJI", "^VIX"] +
    list(sector_tickers_map.values()) +
    list(portfolio_buys.keys()) +
    [s["ticker"] for s in init_lt if isinstance(s, dict) and "ticker" in s] +
    [s["ticker"] for s in init_sw if isinstance(s, dict) and "ticker" in s]
))

def fetch_market_data(tickers):
    market_data = {}
    for ticker in tickers:
        success = False
        for attempt in range(3):
            try:
                stock = yf.Ticker(ticker)
                hist = stock.history(period="2d")
                info = stock.info or {}
                target_mean = info.get("targetMeanPrice")
                
                pre_market_val = info.get("preMarketPrice") or info.get("open") or info.get("regularMarketOpen")
                if not pre_market_val and not hist.empty:
                    pre_market_val = hist["Open"].iloc[-1]

                if not hist.empty:
                    current_price = round(float(hist["Close"].iloc[-1]), 2)
                    prev_close = float(hist["Close"].iloc[-2]) if len(hist) > 1 else current_price
                    change = round(((current_price - prev_close) / prev_close) * 100, 2) if prev_close else 0.0
                    market_data[ticker] = {
                        "price": current_price,
                        "change": change,
                        "target": float(target_mean) if target_mean else 0.0,
                        "pre_market": round(float(pre_market_val), 2) if pre_market_val else current_price
                    }
                    success = True
                    break
            except Exception:
                time.sleep(1)
        if not success:
            market_data[ticker] = {"price": 0.0, "change": 0.0, "target": 0.0, "pre_market": 0.0}
    return market_data

def build_structured_stocks_html(stocks_meta, market_data):
    html_parts = []
    if not isinstance(stocks_meta, list):
        stocks_meta = LT_STOCKS_META

    for s in stocks_meta:
        if not isinstance(s, dict):
            continue
        ticker = s.get("ticker", "")
        name = s.get("name", ticker)
        desc = s.get("desc", "")
        news = s.get("news", "")

        data = market_data.get(ticker, {})
        price = format_num(data.get("price", 0))
        pre_market = format_num(data.get("pre_market", 0))
        target = format_num(data.get("target", 0))
        change_val = data.get("change", 0.0)

        sign = "+" if change_val > 0 else ""
        color = "#2ecc71" if change_val >= 0 else "#e74c3c"
        change_str = f"<span style='color: {color}; font-weight: bold;'>{sign}{change_val:.2f}%</span>"
        
        logo_url = get_stock_logo_url(ticker)
        clean_symbol_lower = ticker.lower().replace("-", "").replace(".", "")

        card_html = f"""
        <div class="bg-gray-800/80 border border-gray-700/60 rounded-xl p-4 mb-4 shadow-md text-right" dir="rtl">
            <div class="flex items-center gap-3 mb-3">
                <img src="{logo_url}" width="28" height="28" class="rounded-full bg-white p-0.5 object-contain" alt="{ticker}" onerror="this.onerror=null; this.src='https://s3-symbol-logo.tradingview.com/{clean_symbol_lower}.svg';">
                <span class="text-base font-bold text-white">{name} (טיקר: {ticker}):</span>
            </div>
            <div class="text-sm text-gray-300 space-y-1">
                <div><strong>מחיר נוכחי:</strong> ${price}</div>
                <div><strong>מחיר טרום פתיחה:</strong> ${pre_market}</div>
                <div><strong>יעד אנליסטים ממוצע:</strong> ${target}</div>
                <div><strong>רווח יום מסחר אחרון:</strong> {change_str}</div>
                <div><strong>עיסוק החברה:</strong> {desc}</div>
                <div><strong>חדשות ורציונל יומי:</strong> {news}</div>
            </div>
        </div>
        """
        html_parts.append(card_html)
    return "".join(html_parts)

def build_market_news_html(ai_insights):
    market_news_list = ai_insights.get("market_news", [])
    if not isinstance(market_news_list, list) or not market_news_list:
        return '<div class="text-gray-400 text-right" dir="rtl">אין חדשות שוק זמינות כרגע.</div>'

    html_parts = []
    for item in market_news_list:
        if not isinstance(item, dict):
            continue
        p_link = item.get("news_link", "https://www.investing.com")
        p_title = item.get("news_title", "עדכון שוק יומי")
        p_content = item.get("news_content", "סקירת אירועים והשפעות מאקרו-כלכליות על השווקים להיום.")
        p_impact = item.get("news_impact", "השפעה רוחבית על סנטימנט המסחר ומגמת השוק היומית.")

        card_html = f"""
        <div class="bg-gray-800 p-4 rounded-xl border border-gray-700 shadow space-y-2 text-sm text-gray-300 text-right" dir="rtl">
            <h3 class="text-cyan-400 font-semibold">{p_title}</h3>
            <p>🔗 <strong>קישור למקור:</strong> <a href="{p_link}" target="_blank" class="text-cyan-400 hover:underline">{p_link}</a></p>
            <p><strong>כותרת הכתבה המלאה:</strong> {p_title}</p>
            <p><strong>תוכן הכתבה המלא:</strong> {p_content}</p>
            <p>🚀 <strong>מה זה אומר בקשר למניה / לשוק:</strong> {p_impact}</p>
        </div>
        """
        html_parts.append(card_html)
    
    return "".join(html_parts)

if __name__ == "__main__":
    try:
        print("Fetching initial market data...")
        base_market_data = fetch_market_data(base_market_tickers)
        date_str = now_il.strftime("%d.%m.%Y")
        time_str = now_il.strftime("%H:%M")

        print(f"🕒 Fetching fresh Investing RSS news & AI insights from Groq with retry loop...")
        investing_headlines = fetch_investing_news()
        ai_insights = fetch_ai_insights_from_groq(base_market_data, portfolio_buys, date_str, day_name, investing_headlines)
        
        if ai_insights and isinstance(ai_insights, dict) and len(ai_insights) > 3:
            save_ai_cache(ai_insights)

        new_lt = ai_insights.get("long_term_stocks", [])
        new_sw = ai_insights.get("swing_stocks", [])
        extra_tickers = []
        for s in new_lt + new_sw:
            if isinstance(s, dict) and "ticker" in s and s["ticker"] not in base_market_data:
                extra_tickers.append(s["ticker"])
        if extra_tickers:
            print(f"Fetching market data for extra AI-selected tickers: {extra_tickers}")
            extra_data = fetch_market_data(extra_tickers)
            base_market_data.update(extra_data)

        sp500 = base_market_data.get("^GSPC", {})
        nasdaq = base_market_data.get("^NDX", {})
        dji = base_market_data.get("^DJI", {})
        vix = base_market_data.get("^VIX", {})
        usd_ils_data = base_market_data.get("USDILS=X", {})
        dxy_data = base_market_data.get("DX-Y.NYB", {})

        sp500_price = format_num(sp500.get("price", 0))
        sp500_change = format_pct_colored(sp500.get("change", 0))
        nasdaq_price = format_num(nasdaq.get("price", 0))
        nasdaq_change = format_pct_colored(nasdaq.get("change", 0))
        dji_price = format_num(dji.get("price", 0))
        dji_change = format_pct_colored(dji.get("change", 0))
        vix_price = format_num(vix.get("price", 0))
        vix_change = format_pct_colored(vix.get("change", 0))
        
        dxy_price = format_num(dxy_data.get("price", 0))
        dxy_change = format_pct_colored(dxy_data.get("change", 0))

        usd_ils_p = usd_ils_data.get("price", 3.00)
        if not usd_ils_p or usd_ils_p <= 1.0:
            usd_ils_p = 3.00
        usd_ils_c = usd_ils_data.get("change", 0)
        usd_ils_price = f"{format_num(usd_ils_p)}₪"
        usd_ils_change = format_pct_colored(usd_ils_c)

        oil_data = base_market_data.get("CL=F", {})
        oil_p = oil_data.get("price", 75.0)
        oil_c = oil_data.get("change", 0)
        oil_price = f"${format_num(oil_p)}"
        oil_change = format_pct_colored(oil_c)

        gold_data = base_market_data.get("GC=F", {})
        gold_p = gold_data.get("price", 2350.0)
        gold_c = gold_data.get("change", 0)
        gold_price = f"${format_num(gold_p)}"
        gold_change = format_pct_colored(gold_c)

        btc_data = base_market_data.get("BTC-USD", {})
        btc_p = btc_data.get("price", 65000.0)
        btc_c = btc_data.get("change", 0)
        btc_price = f"${format_num(btc_p)}"
        btc_change = format_pct_colored(btc_c)

        portfolio_analysis_map = ai_insights.get("portfolio_analysis", {})
        if not isinstance(portfolio_analysis_map, dict):
            portfolio_analysis_map = {}

        if not os.path.exists(TEMPLATE_FILE):
            raise FileNotFoundError(f"Template file '{TEMPLATE_FILE}' not found in directory!")

        with open(TEMPLATE_FILE, "r", encoding="utf-8-sig") as f:
            content = f.read()

        lt_stocks_data = ai_insights.get("long_term_stocks", LT_STOCKS_META)
        sw_stocks_data = ai_insights.get("swing_stocks", SW_STOCKS_META)

        lt_html = build_structured_stocks_html(lt_stocks_data, base_market_data)
        sw_html = build_structured_stocks_html(sw_stocks_data, base_market_data)
        news_html = build_market_news_html(ai_insights)

        portfolio_js_list = []
        for ticker, info in portfolio_buys.items():
            if not isinstance(info, dict):
                continue
            try:
                buy_p = float(info.get("buy") or info.get("buyPrice") or 0.0)
                fetched_price_data = base_market_data.get(ticker, {})
                curr_p = fetched_price_data.get("price") or buy_p
                fetched_target = fetched_price_data.get("target") or (buy_p * 1.20 if buy_p > 0 else 100.0)
                pre_p = fetched_price_data.get("pre_market") or curr_p

                ret = ((curr_p - buy_p) / buy_p) * 100 if buy_p > 0 else 0.0
                sign = "+" if ret > 0 else ""
                color = "#2ecc71" if ret >= 0 else "#e74c3c"

                shares_count = info.get("shares", 0)
                company_name = info.get("name") or fetched_price_data.get("name") or ticker

                p_item = portfolio_analysis_map.get(ticker, {})
                p_rationale = p_item.get("rationale", f"ניתוח יומי מעמיק לפוזיציית {ticker} והתנהלות סביב רמות המחיר.")
                p_news_title = p_item.get("news_title", f"עדכון שוק מרכזי עבור {ticker}")
                p_news_content = p_item.get("news_content", f"סקירת חדשות ואירועים אחרונים המשפיעים ישירות על {ticker}.")
                p_news_impact = p_item.get("news_impact", "השפעה ישירה על ניהול הפוזיציה ותזמון הפעולות בתיק.")

                full_note_html = (
                    f"<div><strong>רציונל וניתוח:</strong> {p_rationale}</div>"
                    f"<div><strong>כותרת חדשותית:</strong> {p_news_title}</div>"
                    f"<div><strong>תוכן חדשותי:</strong> {p_news_content}</div>"
                    f"<div><strong>השפעה על הפוזיציה:</strong> {p_news_impact}</div>"
                )

                portfolio_js_list.append({
                    "name": company_name,
                    "symbol": ticker,
                    "shares": shares_count,
                    "buyPrice": buy_p,
                    "current": f"${format_num(curr_p)}",
                    "pre": f"${format_num(pre_p)}",
                    "target": f"${format_num(fetched_target)}",
                    "status": f"רווח: <span style='color: {color}; font-weight: bold;'>{sign}{ret:.2f}%</span>",
                    "note": full_note_html
                })
            except Exception as ex:
                print(f"Error processing portfolio stock {ticker}: {ex}")

        replacements = {
            "LAST_UPDATED": f"{date_str} | {time_str}",
            "AI_LAST_UPDATED": ai_insights.get("ai_updated_at", f"{date_str} | {time_str}"),
            "DAY_NAME": day_name,
            "PORTFOLIO_COUNT": format_num(len(portfolio_buys), 0),
            "PORTFOLIO_STOCKS_JSON": json.dumps(portfolio_js_list, ensure_ascii=False),
            "SP500_PRICE": sp500_price,
            "SP500_PCT": sp500_change,
            "NASDAQ_PRICE": nasdaq_price,
            "NASDAQ_PCT": nasdaq_change,
            "DOW_PRICE": dji_price,
            "DOW_PCT": dji_change,
            "VIX_PRICE": vix_price,
            "VIX_PCT": vix_change,
            "DXY_PRICE": dxy_price,
            "DXY_PCT": dxy_change,
            "SP500_ANALYSIS": ai_insights.get("SP500_ANALYSIS", ""),
            "NASDAQ_ANALYSIS": ai_insights.get("NASDAQ_ANALYSIS", ""),
            "DOW_ANALYSIS": ai_insights.get("DOW_ANALYSIS", ""),
            "VIX_ANALYSIS": ai_insights.get("VIX_ANALYSIS", ""),
            "DXY_ANALYSIS": ai_insights.get("DXY_ANALYSIS", ""),
            "USD_ILS": usd_ils_price,
            "USD_ILS_CHANGE": usd_ils_change,
            "OIL_PRICE": oil_price,
            "OIL_CHANGE": oil_change,
            "GOLD_PRICE": gold_price,
            "GOLD_CHANGE": gold_change,
            "BTC_PRICE": btc_price,
            "BTC_CHANGE": btc_change,
            "USD_ILS_EXPLANATION": ai_insights.get("USD_ILS_EXPLANATION", ""),
            "OIL_EXPLANATION": ai_insights.get("OIL_EXPLANATION", ""),
            "GOLD_EXPLANATION": ai_insights.get("GOLD_EXPLANATION", ""),
            "BTC_EXPLANATION": ai_insights.get("BTC_EXPLANATION", ""),
            "US_MARKET_NEWS": ai_insights.get("US_MARKET_NEWS", ""),
            "IL_MARKET_NEWS": ai_insights.get("IL_MARKET_NEWS", ""),
            "CATALYST_EARNINGS": ai_insights.get("CATALYST_EARNINGS", ""),
            "CATALYST_MONETARY": ai_insights.get("CATALYST_MONETARY", ""),
            "CATALYST_HARDWARE": ai_insights.get("CATALYST_HARDWARE", ""),
            "COMMUNITY_SENTIMENT": ai_insights.get("COMMUNITY_SENTIMENT", ""),
            "ANALYST_POINT_1": ai_insights.get("ANALYST_POINT_1", ""),
            "ANALYST_POINT_2": ai_insights.get("ANALYST_POINT_2", ""),
            "RISK_MANAGEMENT_TEXT": ai_insights.get("RISK_MANAGEMENT_TEXT", ""),
            "ACTION_RECOMMENDATIONS_TEXT": ai_insights.get("ACTION_RECOMMENDATIONS_TEXT", ""),
            "LONG_TERM_STOCKS_SECTION": lt_html,
            "SWING_STOCKS_SECTION": sw_html,
            "PORTFOLIO_NEWS_SECTION": news_html,
        }

        for s_key, s_ticker in sector_tickers_map.items():
            s_data = base_market_data.get(s_ticker, {})
            s_change = s_data.get("change", 0.0)
            sign = "+" if s_change > 0 else ""
            color = "#2ecc71" if s_change >= 0 else "#e74c3c"
            s_price = format_num(s_data.get("price", 0))
            replacements[f"{s_key}_PRICE"] = f"${s_price}"
            replacements[f"{s_key}_PCT"] = f"<span style='color: {color}; font-weight: bold;'>{sign}{s_change:.2f}%</span>"

        for k, v in replacements.items():
            content = content.replace("{{" + k + "}}", str(v))

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"Successfully generated {OUTPUT_FILE}!")

    except Exception as e:
        print(f"❌ Critical Error in main execution: {e}")
        traceback.print_exc()
        exit(1)
