import base64
from datetime import datetime
import json
import os
import subprocess
import time
import traceback
import urllib.parse
import pytz
import requests
import yfinance as yf

AI_CACHE_FILE = "ai_cache.json"
PORTFOLIO_FILE = "portfolio.json"
TEMPLATE_FILE = "index.template.html"
OUTPUT_FILE = "index.html"

GITHUB_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")

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
            json.dump(data, f, ensure_ascii=False, indent=2)
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

DOMAIN_MAP = {
    "NVDA": "nvidia.com",
    "AMD": "amd.com",
    "MU": "micron.com",
    "SNDK": "sandisk.com",
    "WDC": "westerndigital.com",
    "INTC": "intel.com",
    "SIMO": "siliconmotion.com",
    "IREN": "iren.com",
    "CIFR": "ciphermining.com",
    "META": "meta.com",
    "AMZN": "amazon.com",
    "GOOG": "google.com",
    "GOOGL": "google.com",
    "TTWO": "take2games.com",
    "WMT": "walmart.com",
    "NFLX": "netflix.com",
    "MA": "mastercard.com",
    "IBIT": "ishares.com",
    "GTEC": "gtec.com",
    "TQQQ": "proshares.com",
    "MSFT": "microsoft.com",
    "AAPL": "apple.com",
    "TSLA": "tesla.com",
    "BTC-USD": "bitcoin.org",
    "ETH-USD": "ethereum.org"
}

def get_stock_logo_url(ticker, website=None):
    domain = None
    clean_ticker = str(ticker).strip().upper()
    try:
        if clean_ticker in DOMAIN_MAP:
            domain = DOMAIN_MAP[clean_ticker]
        elif website:
            parsed_url = urllib.parse.urlparse(website)
            netloc = parsed_url.netloc
            if netloc:
                domain = netloc.replace("www.", "")
    except Exception:
        pass
    
    if not domain:
        domain = f"{clean_ticker.lower()}.com"
        
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"

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

def get_default_ai_insights():
    return {
        "SP500_ANALYSIS": "מדד S&P 500 ממשיך להיסחר סביב רמות מפתח תוך בחינת נתוני המאקרו והאינפלציה.",
        "NASDAQ_ANALYSIS": "מדד הטכנולוגיה מוביל את הסנטימנט בשוק עם דגש על חדשנות ובינה מלאכותית.",
        "DOW_ANALYSIS": "מניות הערך במדד הדאו ג'ונס מספקות יציבות ועוגן רחב לתיק המסחר.",
        "VIX_ANALYSIS": "מדד התנודתיות משקף רמת רגיעה מתונה בשווקים ללא לחצים חריגים.",
        "DXY_ANALYSIS": "מדד הדולר העולמי נסחר במגמה מעורבת אל מול המטבעות המרכזיים.",
        "USD_ILS_EXPLANATION": "השפעה ישירה על עלות ייבוא, מוצרים דולריים ותיק ההשקעות המקומי.",
        "OIL_EXPLANATION": "משפיע ישירות על עלויות האנרגיה, התחבורה ושיעורי האינפלציה הגלובליים.",
        "GOLD_EXPLANATION": "משמש כנכס מקלט בטוח וגידור מרכזי מפני אי-יציבות גיאו-פוליטית.",
        "BTC_EXPLANATION": "אינדיקטור מוביל לסנטימנט סיכון ונזילות בנכסים אלטרנטיביים.",
        "US_MARKET_NEWS": "נתוני המאקרו בארה\"ב ממשיכים להוות מנוע ניווט מרכזי עבור הבנק המרכזי והמשקיעים.",
        "IL_MARKET_NEWS": "השוק המקומי מגיב להתפתחויות הביטחוניות והכלכליות באזור.",
        "CATALYST_EARNINGS": "דיווחים רבעוניים מגוונים מכלל סקטורי המשק מובילים את נפחי המסחר.",
        "CATALYST_MONETARY": "הודעות ריבית ומדיניות מוניטרית צפויות להשפיע על תשואות האג\"ח.",
        "CATALYST_HARDWARE": "השקות מוצרים, חדשנות טכנולוגית והתפתחויות רוחביות בכלל הענפים.",
        "COMMUNITY_SENTIMENT": "סנטימנט חיובי זהיר סביב נכסים מובילים והזדמנויות סלקטיביות.",
        "ANALYST_POINT_1": "האנליסטים ממליצים על פיזור סקטוריאלי רחב וניהול סיכונים קפדני.",
        "ANALYST_POINT_2": "דגש על בחינה בררנית של דוחות כספיים וביצועי חברות מובילות בכל ענף.",
        "RISK_MANAGEMENT_TEXT": "ניהול סיכונים קפדני באמצעות פיזור השקעות רוחבי ופקודות הגנה לפוזיציות.",
        "ACTION_RECOMMENDATIONS_TEXT": "בחינה מדודה של פוזיציות קיימות והיערכות להזדמנויות סלקטיביות בכל הסקטורים.",
        "portfolio_analysis": {}
    }

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

base_market_tickers = list(set(
    ["GC=F", "CL=F", "BTC-USD", "USDILS=X", "DX-Y.NYB", "^GSPC", "^NDX", "^DJI", "^VIX"] +
    list(sector_tickers_map.values()) +
    list(portfolio_buys.keys()) +
    [s["ticker"] for s in LT_STOCKS_META] +
    [s["ticker"] for s in SW_STOCKS_META]
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
                website = info.get("website")
                
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
                        "pre_market": round(float(pre_market_val), 2) if pre_market_val else current_price,
                        "website": website
                    }
                    success = True
                    break
            except Exception:
                time.sleep(1)
        if not success:
            market_data[ticker] = {"price": 0.0, "change": 0.0, "target": 0.0, "pre_market": 0.0, "website": None}
    return market_data

def build_structured_stocks_html(stocks_meta, market_data):
    html_parts = []
    for s in stocks_meta:
        ticker = s["ticker"]
        name = s["name"]
        desc = s["desc"]
        news = s["news"]

        data = market_data.get(ticker, {})
        price = format_num(data.get("price", 0))
        pre_market = format_num(data.get("pre_market", 0))
        target = format_num(data.get("target", 0))
        change_val = data.get("change", 0.0)
        website = data.get("website")

        sign = "+" if change_val > 0 else ""
        color = "#2ecc71" if change_val >= 0 else "#e74c3c"
        change_str = f"<span style='color: {color}; font-weight: bold;'>{sign}{change_val:.2f}%</span>"
        
        logo_url = get_stock_logo_url(ticker, website)

        card_html = f"""
        <div class="bg-gray-800/80 border border-gray-700/60 rounded-xl p-4 mb-4 shadow-md text-right" dir="rtl">
            <div class="flex items-center gap-3 mb-3">
                <img src="{logo_url}" width="28" height="28" class="rounded-full bg-white p-0.5 object-contain" alt="{ticker}" onerror="this.style.display='none'; this.nextElementSibling.style.display='inline-flex';">
                <span class="inline-flex items-center justify-center w-7 h-7 bg-gray-700 text-white text-xs font-bold rounded-full" style="display: none;">{ticker}</span>
                <span class="text-base font-bold text-white">{name} (טיקר: {ticker}):</span>
            </div>
            <div class="text-sm text-gray-300 space-y-1">
                <div><strong>מחיר נוכחי:</strong> ${price}</div>
                <div><strong>מחיר טרום פתיחה:</strong> ${pre_market}</div>
                <div><strong>יעד אנליסטים ממוצע:</strong> ${target}</div>
                <div><strong>רווח:</strong> {change_str}</div>
                <div><strong>עיסוק החברה:</strong> {desc}</div>
                <div><strong>חדשות ורציונל:</strong> {news}</div>
            </div>
        </div>
        """
        html_parts.append(card_html)
    return "".join(html_parts)

if __name__ == "__main__":
    try:
        print("Fetching market data...")
        base_market_data = fetch_market_data(base_market_tickers)
        date_str = now_il.strftime("%d.%m.%Y")
        time_str = now_il.strftime("%H:%M")

        ai_insights = load_ai_cache()
        if not isinstance(ai_insights, dict) or not ai_insights:
            ai_insights = get_default_ai_insights()

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

        usd_ils_p = usd_ils_data.get("price", 3.65)
        if not usd_ils_p or usd_ils_p <= 3.0:
            usd_ils_p = 3.65
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

        lt_html = build_structured_stocks_html(LT_STOCKS_META, base_market_data)
        sw_html = build_structured_stocks_html(SW_STOCKS_META, base_market_data)

        replacements = {
            "LAST_UPDATED": f"{date_str} | {time_str}",
            "DAY_NAME": day_name,
            "PORTFOLIO_COUNT": format_num(len(portfolio_buys), 0),
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
        }

        for s_key, s_ticker in sector_tickers_map.items():
            s_data = base_market_data.get(s_ticker, {})
            s_change = s_data.get("change", 0.0)
            sign = "+" if s_change > 0 else ""
            color = "#2ecc71" if s_change >= 0 else "#e74c3c"
            
            replacements[f"SECTOR_{s_key}_PCT"] = f"({sign}{s_change:.2f}%)"
            replacements[f"SECTOR_{s_key}_CLASS"] = f"style='color: {color}'"
            replacements[f"SECTOR_{s_key}_PERF"] = s_change

        for ticker, info in portfolio_buys.items():
            if not isinstance(info, dict):
                continue
            try:
                buy_p = float(info.get("buy") or info.get("buyPrice") or 0.0)

                fetched_price_data = base_market_data.get(ticker, {})
                curr_p = fetched_price_data.get("price")
                if not curr_p or curr_p == 0.0:
                    curr_p = float(info.get("currentPrice") or buy_p)
                
                fetched_target = fetched_price_data.get("target", 0.0)
                if not fetched_target or fetched_target == 0.0:
                    fetched_target = buy_p * 1.25 if buy_p > 0 else 100.0

                pre_p = fetched_price_data.get("pre_market", 0.0)
                if not pre_p or pre_p == 0.0:
                    pre_p = curr_p

                ret = ((curr_p - buy_p) / buy_p) * 100 if buy_p > 0 else 0.0
                sign = "+" if ret > 0 else ""
                color = "#2ecc71" if ret >= 0 else "#e74c3c"

                shares_count = info.get("shares", 0)
                company_name = info.get("name") or fetched_price_data.get("name") or ticker
                website = fetched_price_data.get("website")

                p_item = portfolio_analysis_map.get(ticker, {})
                p_rationale = p_item.get("rationale", f"ניתוח טכני ומאקרו עבור {ticker}.")
                p_news_title = p_item.get("news_title", f"עדכון שוק עבור {ticker}")
                p_news_content = p_item.get("news_content", f"סקירת נתונים פיננסיים עבור {ticker}.")
                p_news_impact = p_item.get("news_impact", "השפעה מתונה על ניהול הפוזיציה.")

                full_note_html = (
                    f"<strong>רציונל וניתוח:</strong> {p_rationale}<br>"
                    f"<strong>כותרת חדשותית:</strong> {p_news_title}<br>"
                    f"<strong>תוכן חדשותي:</strong> {p_news_content}<br>"
                    f"<strong>השפעה על הפוזיציה:</strong> {p_news_impact}"
                )

                logo_url = get_stock_logo_url(ticker, website)

                title_with_logo = f"""<span style="display: inline-flex; align-items: center; gap: 8px;">
                    <img src="{logo_url}" width="24" height="24" style="border-radius: 50%; background: white; padding: 1px; object-fit: contain;" alt="{ticker}" onerror="this.style.display='none'; this.nextElementSibling.style.display='inline-flex';">
                    <span style="display: none; align-items: center; justify-content: center; width: 24px; height: 24px; background: #374151; color: white; font-size: 10px; font-weight: bold; border-radius: 50%;">{ticker}</span>
                    {company_name} (טיקר: {ticker})
                </span>"""

                replacements[f"{ticker}_PORT_TITLE"] = title_with_logo
                replacements[f"{ticker}_PORT_SHARES"] = format_num(shares_count, 0)
                replacements[f"{ticker}_PORT_CURRENT"] = f"${format_num(curr_p)}"
                replacements[f"{ticker}_PORT_PRE"] = f"${format_num(pre_p)}"
                replacements[f"{ticker}_PORT_TARGET"] = f"${format_num(fetched_target)}"
                replacements[f"{ticker}_PORT_STATUS"] = f"רווח: <span style='color: {color}; font-weight: bold;'>{sign}{ret:.2f}%</span>"
                replacements[f"{ticker}_PORT_NOTE"] = full_note_html
            except Exception as ex:
                print(f"Error processing portfolio item {ticker}: {ex}")

        for key, val in replacements.items():
            content = content.replace(f"{{{{{key}}}}}", str(val))

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        print("Successfully generated index.html!")

        subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", OUTPUT_FILE, PORTFOLIO_FILE], check=True)

        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True)
        if OUTPUT_FILE in status.stdout or PORTFOLIO_FILE in status.stdout:
            subprocess.run(["git", "commit", "-m", f"Update site and portfolio safely on {day_name}"], check=True)
            subprocess.run(["git", "pull", "origin", "main", "--rebase"], check=True)
            subprocess.run(["git", "push"], check=True)
            print("Successfully pushed changes to GitHub!")

    except Exception as e:
        traceback.print_exc()
        raise
