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
from google import genai

AI_CACHE_FILE = "ai_cache.json"
PORTFOLIO_FILE = "portfolio.json"
TEMPLATE_FILE = "index.template.html"
OUTPUT_FILE = "index.html"

GITHUB_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

# אתחול הלקוח החדש של גוגל
client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

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
        "long_term_stocks": LT_STOCKS_META,
        "swing_stocks": SW_STOCKS_META,
        "portfolio_analysis": {},
        "market_news": [
            {
                "news_link": "https://www.investing.com",
                "news_title": "עדכון שוק יומי - מה מניע את השווקים",
                "news_content": "אירועים גיאו-פוליטיים מרכזיים לצד דוחות כספיים משמעותיים מעצבים את סנטימנט המסחר ומייצרים תנודתיות רוחבית בסקטורים השונים.",
                "news_impact": "השפעה ישירה על מניות הטכנולוגיה, מחירי האנרגיה ותיאבון הסיכון של משקיעים בשוק."
            }
        ]
    }

def fetch_ai_insights_from_gemini(market_data, portfolio_stocks, date_str, day_name):
    if not client:
        print("❌ ERROR: Gemini Client is missing! Using defaults.")
        cached = load_ai_cache()
        return cached if cached else get_default_ai_insights()

    try:
        print(f"🤖 Connecting to Gemini AI to generate daily cross-sector market insights for {day_name}, {date_str}...")
        market_summary = {t: f"Price: {d.get('price')}, Change: {d.get('change')}%" for t, d in market_data.items()}
        portfolio_tickers = list(portfolio_stocks.keys())

        prompt = f"""
אתה אנליסט שוק הון בכיר וגלובלי. היום הוא {day_name}, בתאריך {date_str}.
על בסיס נתוני השוק הנוכחיים הבאים להיום:
{json.dumps(market_summary, ensure_ascii=False)}

ועבור מניות התיק האישי של המשתמש: {portfolio_tickers}

הנחיות קריטיות, נוקשות ומחייבות:
1. עדכניות יומית מוחלטת (95% דיוק ורעננות לזמן אמת של היום הספציפי הזה - {date_str}): כל החדשות, הדיווחים, האירועים הגיאו-פוליטיים, דוחות החברות ומגמות המאקרו חייבים להיות מעודכנים להיום ממש, ברמה היומית הגבוהה ביותר. חל איסור מוחלט למחזר ידיעות ישנות, גנריות או פגי תוקף.
2. כיסוי רוחבי מלא: הניתוחים, החדשות והסקירות חייבים לכסות את כל סקטורי שוק ההון באופן רוחבי ומקיף (כגון פיננסים, בריאות, אנרגיה, טכנולוגיה, צרכנות בסיסית ומחזורית, תעשייה, חומרי גלם ונדל"ן) ולא להתרכז בסקטור אחד בלבד.

אנא החזר אך ורק אובייקט JSON תקין (ללא מעטפות markdown וללא טקסט נוסף סביב) הכולל בדיוק את המפתחות הבאים בעברית מקצועית לשוק ההון:
1. SP500_ANALYSIS
2. NASDAQ_ANALYSIS
3. DOW_ANALYSIS
4. VIX_ANALYSIS
5. DXY_ANALYSIS
6. USD_ILS_EXPLANATION
7. OIL_EXPLANATION
8. GOLD_EXPLANATION
9. BTC_EXPLANATION
10. US_MARKET_NEWS
11. IL_MARKET_NEWS
12. CATALYST_EARNINGS
13. CATALYST_MONETARY
14. CATALYST_HARDWARE
15. COMMUNITY_SENTIMENT
16. ANALYST_POINT_1
17. ANALYST_POINT_2
18. RISK_MANAGEMENT_TEXT
19. ACTION_RECOMMENDATIONS_TEXT
20. long_term_stocks: מערך (array) של בדיוק 10 מניות מומלצות להשקעה ארוכת טווח. כל פריט יהיה אובייקט עם השדות: ticker, name, desc, news.
21. swing_stocks: מערך (array) של בדיוק 10 מניות מומלצות למסחר סווינג. כל פריט יהיה אובייקט עם השדות: ticker, name, desc, news.
22. portfolio_analysis: אובייקט שבו המפתחות הם הטיקרים של מניות התיק האישי, ועבור כל טיקר אובייקט עם השדות: rationale, news_link, news_title, news_content, news_impact.
23. market_news: מערך (array) של 5 עד 7 ידיעות חדשותיות כלליות ומרכזיות על שוק ההון הגלובלי, מלחמות, דוחות ומאקרו בסגנון Investing מעודכניות להיום. כל פריט יהיה אובייקט עם השדות: news_link, news_title, news_content, news_impact.
"""

        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt,
        )
        
        raw_text = response.text.strip()
        print("--- RAW AI RESPONSE RECEIVED ---")
        print(raw_text[:600] + "..." if len(raw_text) > 600 else raw_text)
        print("--------------------------------")

        clean_text = raw_text
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        if clean_text.endswith("
