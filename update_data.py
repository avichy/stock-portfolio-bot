import base64
from datetime import datetime
import json
import os
import re
import subprocess
import time
import traceback
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import pytz
import requests
from groq import Groq

AI_CACHE_FILE = "ai_cache.json"
PORTFOLIO_FILE = "portfolio.json"
TEMPLATE_FILE = "index.template.html"
OUTPUT_FILE = "index.html"

GITHUB_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")

# רשימת המודלים המעודכנת והפעילה בלבד ב-Groq
SAFE_MODEL_HIERARCHY = [
    "llama-3.3-70b-versatile",
]


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
        return (
            f'<span dir="ltr" style="color: {color}; font-weight: bold; display:'
            f' inline-block;">{sign}{num:.2f}%</span>'
        )
    except (ValueError, TypeError):
        return str(val)


def format_numbers_in_text(text):
    def replace_num(match):
        num_str = match.group(0)
        try:
            if "." in num_str:
                parts = num_str.split(".")
                integer_part = int(parts[0])
                return f"{integer_part:,}.{parts[1]}"
            else:
                return f"{int(num_str):,}"
        except Exception:
            return num_str

    return re.sub(
        r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d{4,}(?:\.\d+)?\b",
        replace_num,
        text,
    )


def format_ai_text(text):
    if isinstance(text, list):
        text = " ".join(str(item) for item in text)
    elif not isinstance(text, str):
        text = str(text)

    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed_list = json.loads(text)
            if isinstance(parsed_list, list):
                text = " ".join(str(item) for item in parsed_list)
        except Exception:
            pass

    # הסרת קידומות מיותרות, מילות מפתח באנגלית וביטויים משובשים בצורה חלקה
    text = re.sub(
        r"^[\s\n]*(?:analysis|strategy|recommendations|המלצה|המלצות|ניתוח\s+ה?-?[^\n:]*|קָטָלִיסט[^\n:]*|השפעות[^\n:]*|סיכום הכתבה:?)\s*[:\-]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b(?:analysis|strategy|recommendations)\b\s*[:\-]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"^(?:🇺🇸|🇮🇱|US|IL)\s*(?:השפעות על השוק[^:]*)?[:\-]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    cleaned = (
        text.replace("{", "")
        .replace("}", "")
        .replace("[", "")
        .replace("]", "")
        .replace('"', "")
        .replace("'", "")
    )

    cleaned = re.sub(
        r"\s*(?:מה\s*זה\s*אומר|לסיכום)\s*:?\s*[\?\-\*\s]*(?:זה\s*אומר\s*(?:ש)?\s*)?",
        r"<br><strong>לסיכום:</strong><br>",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = format_numbers_in_text(cleaned)
    return f'<div class="leading-relaxed text-sm text-gray-300">{cleaned}</div>'


def format_analyst_points_clean(text1, text2):
    def clean_t(t):
        if isinstance(t, list):
            t = " ".join(str(item) for item in t)
        elif not isinstance(t, str):
            t = str(t)
        t = t.strip()
        t = re.sub(
            r"^[\s\n]*(?:analysis|strategy|recommendations|המלצה|המלצות|נקודת המנתח\s*\d*|אנליסט\s*\d*|ניתוח)[^\n:]*[:\-]?\s*",
            "",
            t,
            flags=re.IGNORECASE,
        )
        t = re.sub(
            r"\b(?:analysis|strategy|recommendations)\b\s*[:\-]?\s*",
            "",
            t,
            flags=re.IGNORECASE,
        )
        cleaned = (
            t.replace("{", "")
            .replace("}", "")
            .replace("[", "")
            .replace("]", "")
            .replace('"', "")
            .replace("'", "")
        )
        return format_numbers_in_text(cleaned)

    c1 = clean_t(text1)
    c2 = clean_t(text2)

    html1 = f'<div class="mb-3 text-xs text-gray-300 leading-relaxed">{c1}</div>'
    html2 = f'<div class="mb-3 text-xs text-gray-300 leading-relaxed">{c2}</div>'
    return html1, html2


def get_stock_logo_url(ticker):
    clean_ticker = str(ticker).strip().upper()
    parqet_ticker = clean_ticker.replace("-", ".")
    return f"https://assets.parqet.com/logos/symbol/{parqet_ticker}"


def fetch_investing_news():
    url = "https://il.investing.com/rss/news.rss"
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            news_items = []
            for item in root.findall(".//item"):
                title = item.find("title")
                link = item.find("link")
                if (
                    title is not None
                    and title.text
                    and link is not None
                    and link.text
                ):
                    news_items.append(
                        {"title": title.text.strip(), "link": link.text.strip()}
                    )
            return news_items[:15]
    except Exception as e:
        print(f"Warning: Error fetching Hebrew Investing RSS: {e}")
        return []


LT_STOCKS_META = [
    {
        "ticker": "MSFT",
        "name": "Microsoft Corporation",
        "desc": "ענן Azure, תוכנה, פתרונות AI וטכנולוגיה עסקית גלובלית.",
        "news": "התרחבות עקבית בשירותי ענן ובינה מלאכותית ארגונית, יציבות פיננסית גבוהה.",
        "why_invest": "מובילה גלובלית עם תזרים מזומנים אדיר וביקושים קשיחים לשירותי ענן ובינה מלאכותית.",
    },
    {
        "ticker": "JPM",
        "name": "JPMorgan Chase & Co.",
        "desc": "בנקאות מסחרית והשקעות מובילה בארה\"ב ובעולם (סקטור הפיננסים).",
        "news": "תוצאות חזקות וניהול סיכונים קפדני תחת סביבת ריבית משתנה, עוגן חזק בתיק.",
        "why_invest": "ניהול פיננסי מעולה ומאזן חסון המייצרים תשואות עקביות בכל מצב שוק.",
    },
    {
        "ticker": "JNJ",
        "name": "Johnson & Johnson",
        "desc": "פיתוח תרופות, ציוד רפואי ומוצרי בריאות הצרכן (סקטור הבריאות).",
        "news": "חסינות עסקית גבוהה מול מחזוריות השוק, חלוקת דיבידנדים יציבה ואמינה.",
        "why_invest": "חברה דפנסיבית מובהקת עם פורטפוליו רפואי רחב והיסטוריית דיבידנדים מרשימה.",
    },
    {
        "ticker": "XOM",
        "name": "Exxon Mobil Corporation",
        "desc": "חיפוש, הפקה ואנרגיה קונבנציונלית ומתקדמת (סקטור האנרגיה).",
        "news": "תזרים מזומנים חזק ויעילות תפעולית גבוהה התומכת בתשואות אטרקטיביות למשקיעים.",
        "why_invest": "יעילות תפעולית גבוהה ותגמול נדיב למשקיעים באמצעות דיבידנדים ורכישות עצמיות.",
    },
    {
        "ticker": "WMT",
        "name": "Walmart Inc.",
        "desc": "רשת הקמעונאות והמרכולים הגדולה בעולם (סקטור צרכנות בסיסית).",
        "news": "ביקושים יציבים בכל תנאי מאקרו וצמיחה מרשימה בפעילות המסחר האלקטרוני.",
        "why_invest": "חסינות אינפלציונית מוכחת ונוכחות אלקטרונית מתרחב המבטיחים צמיחה יציבה.",
    },
    {
        "ticker": "AMZN",
        "name": "Amazon.com, Inc.",
        "desc": "מסחר אלקטרוני גלובלי ושירותי ענן מובילים (AWS).",
        "news": "שיפור מתמיד בשולי הרווח התפעולי של AWS והתייעלות לוגיסטית רחבת היקף.",
        "why_invest": "שליטה מוחלטת בענן ובמסחר המקוון עם צמיחה מואצת בשולי הרווח.",
    },
    {
        "ticker": "UNH",
        "name": "UnitedHealth Group",
        "desc": "שירותי ביטוח בריאות וניהול רפואי מתקדם.",
        "news": "צמיחה עקבית במספר המבוטחים וביקוש קשיח לשירותי בריאות וניהול סיכונים רפואיים.",
        "why_invest": "מודל עסקי עמיד המבוסס על ביקושים קשיחים במגזר הבריאות הצומח.",
    },
    {
        "ticker": "PG",
        "name": "Procter & Gamble",
        "desc": "ייצור ושיווק מוצרי צריכה ביתיים ואישיים מובילים.",
        "news": "כוח תמחור חזק אל מול אינפלציה ומותגים גלובליים חזקים המבטיחים יציבות.",
        "why_invest": "מותגים מובילים המאפשרים שמירה על רווחיות גבוהה גם בתקופות אינפלציוניות.",
    },
    {
        "ticker": "CVX",
        "name": "Chevron Corporation",
        "desc": "אנרגיה, נפט וגז טבעי בפעילות גלובלית רחבה.",
        "news": "מאזן פיננסי איתן ופרויקטי הפקה חדשים המחזקים את יכולות החלוקה למשקיעים.",
        "why_invest": "משמעת פיננסית קפדנית ותשואת דיבידנד גבוהה המגנים על תיק ההשקעות.",
    },
    {
        "ticker": "BRK-B",
        "name": "Berkshire Hathaway",
        "desc": "חברת אחזקות רב-תחומית המנוהלת בהשקעות ערך קלאסיות.",
        "news": "נזילות עצומה ופורטפוליו מבוזר של עסקים ראשיים המעניקים ביטחון למשקיע ארוך טווח.",
        "why_invest": "ניהול מופתי וביזור עמוק בכלכלה האמריקאית המקנים הגנה מעולה לירידות.",
    },
]

SW_STOCKS_META = [
    {
        "ticker": "TSLA",
        "name": "Tesla, Inc.",
        "desc": "רכבים חשמליים, אנרגיה מתחדשת ופתרונות אוטונומיה (סקטור צרכנות מחזורית).",
        "news": "תנודתיות גבוהה המייצרת הזדמנויות מסחר יומי וסווינג עם מומנטום חזק.",
        "why_invest": "תנועות מחיר חדות המייצרות פוטנציאל רווח מהיר לסוחרים יומיים וסווינג.",
    },
    {
        "ticker": "AMD",
        "name": "Advanced Micro Devices",
        "desc": "פיתוח מעבדים, שבבים וכרטיסים גרפיים לשוק הטכנולוגיה.",
        "news": "תנועות מחיר חדות סביב השקות מוצרים ודו\"חות רבעוניים בסקטור השבבים.",
        "why_invest": "חשיפה ישירה לשוק השבבים וה-AI המייצרת מומנטום מסחר אטרקטיבי.",
    },
    {
        "ticker": "COIN",
        "name": "Coinbase Global, Inc.",
        "desc": "פלטפורמת מסחר מובילה בנכסים דיגיטליים וקריפטו (פיננסים/אלטרנטיבי).",
        "news": "קורלציה ישירה לתנודתיות בשוק הקריפטו, מעולה למסחר סווינג תנודתי קצר.",
        "why_invest": "תנודתיות גבוהה המונעת מנכסים דיגיטליים ומייצרת הזדמנויות רווח מהירות.",
    },
    {
        "ticker": "OXY",
        "name": "Occidental Petroleum",
        "desc": "חברת אנרגיה וחיפושי נפט וגז עם עניין מוסדי רב.",
        "news": "מעקב צמוד אחר מחירי הסחורות והאנרגיה המייצרים מהלכים מהירים במסחר.",
        "why_invest": "גיבוי מוסדי חזק ורגישות למחירי האנרגיה היוצרים מהלכי מסחר ברורים.",
    },
    {
        "ticker": "PLTR",
        "name": "Palantir Technologies",
        "desc": "תוכנות אנליטיקה ובינה מלאכותית למגזר העסקי והביטחוני.",
        "news": "נפחי מסחר גבוהים מאוד ומומנטום חיובי המושך סוחרים לטווח הקצר והבינוני.",
        "why_invest": "מומנטום טכנולוגי אדיר וביקושים מוסדיים חזקים למערכות ה-AI שלה.",
    },
    {
        "ticker": "NVO",
        "name": "Novo Nordisk A/S",
        "desc": "תרופות חדשניות לטיפול בסוכרת וניהול משקל (סקטור הבריאות).",
        "news": "ביקושים אדירים למוצרי הדגל של החברה, יוצר תנודות מחיר מעניינות למסחר.",
        "why_invest": "מובילות בלעדית בתרופות הרזיה וביקושים גלובליים עצומים המרימים את המניה.",
    },
    {
        "ticker": "PYPL",
        "name": "PayPal Holdings, Inc.",
        "desc": "שירותי תשלומים דיגיטליים ופינטק גלובליים.",
        "news": "התאוששות מבנית ושינויים באסטרטגיית הצמיחה המייצרים הזדמנויות סווינג.",
        "why_invest": "תמחור אטרקטיבי ומהלכי טิร์ן-אראונד טכניים התומכים במומנטום עולה.",
    },
    {
        "ticker": "BA",
        "name": "The Boeing Company",
        "desc": "תעופה, ביטחון וייצור מטוסים מסחריים וצבאיים (סקטור התעשייה).",
        "news": "רגישות גבוהה לחדשות תפעוליות ורגולטוריות המייצרות פערים ותנועות חדות.",
        "why_invest": "פוטנציאל התאוששות חזק מאירועים תפעוליים המייצר הזדמנויות סווינג רווחיות.",
    },
    {
        "ticker": "NEM",
        "name": "Newmont Corporation",
        "desc": "חברת כריית הזהב הגדולה בעולם (סקטור חומרי גלם וגידור).",
        "news": "תנועה מנוגדת לרוב לשוק המניות, משמשת ככלי מסחר מצוין סביב מחירי הזהב.",
        "why_invest": "כלי גידור מעולה לשוק המניות המציע תנועות מחיר מהירות סביב הזהב.",
    },
    {
        "ticker": "TQQQ",
        "name": "ProShares UltraPro QQQ",
        "desc": "תעודת סל ממונפת פי 3 על מדד הנאסד\"ק.",
        "news": "כלי מסחר יומי מובהק המבוסס על תנודתיות גבוהה ומינוף לטווח קצר.",
        "why_invest": "מינוף גבוה המאפשר מיצוי מקסימלי של מגמות עולות בנאסד\"ק במסחר קצר.",
    },
]


def fetch_yahoo_direct(ticker):
    clean_ticker = str(ticker).strip().upper()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
            " like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    chart_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(clean_ticker)}?interval=1d&range=5d"
    current_price = 0.0
    prev_close = 0.0
    try:
        resp = requests.get(chart_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            res_json = resp.json()
            result = res_json["chart"]["result"][0]
            meta = result["meta"]
            current_price = meta.get("regularMarketPrice") or meta.get(
                "chartPreviousClose"
            )
            prev_close = meta.get("previousClose") or meta.get(
                "chartPreviousClose"
            )

            q = result["indicators"]["quote"][0]
            closes = [c for c in q.get("closes", []) if c is not None]
            if not current_price and closes:
                current_price = closes[-1]
            if not prev_close and len(closes) > 1:
                prev_close = closes[-2]
            elif not prev_close:
                prev_close = current_price
    except Exception as e:
        print(f"Direct Yahoo chart fetch error for {clean_ticker}: {e}")

    if current_price and prev_close and prev_close > 0:
        change = ((current_price - prev_close) / prev_close) * 100
    else:
        change = 0.0

    target_mean = 0.0
    summary_url = f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/{urllib.parse.quote(clean_ticker)}?modules=financialData"
    try:
        resp_sum = requests.get(summary_url, headers=headers, timeout=10)
        if resp_sum.status_code == 200:
            sum_json = resp_sum.json()
            fin_result = (
                sum_json.get("quoteSummary", {}).get("result", [{}])[0]
            )
            financial_data = fin_result.get("financialData", {})
            target_obj = financial_data.get("targetMeanPrice", {})
            if isinstance(target_obj, dict):
                target_mean = target_obj.get("raw", 0.0)
    except Exception as e:
        print(f"Yahoo quoteSummary target fetch error for {clean_ticker}: {e}")

    if current_price and current_price > 0:
        return {
            "price": round(float(current_price), 2),
            "change": round(float(change), 2),
            "target": float(target_mean) if target_mean else 0.0,
            "pre_market": round(float(current_price), 2),
        }

    return None


def fetch_market_data(tickers):
    market_data = {}
    for ticker in tickers:
        data = fetch_yahoo_direct(ticker)
        if data and data["price"] > 0:
            market_data[ticker] = data
        else:
            defaults = {
                "USDILS=X": {
                    "price": 3.65,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 3.65,
                },
                "^GSPC": {
                    "price": 5500.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 5500.0,
                },
                "^NDX": {
                    "price": 19500.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 19500.0,
                },
                "^DJI": {
                    "price": 41000.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 41000.0,
                },
                "^VIX": {
                    "price": 15.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 15.0,
                },
                "DX-Y.NYB": {
                    "price": 103.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 103.0,
                },
                "CL=F": {
                    "price": 75.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 75.0,
                },
                "GC=F": {
                    "price": 2400.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 2400.0,
                },
                "BTC-USD": {
                    "price": 60000.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 60000.0,
                },
                "XLK": {"price": 220.0, "change": 0.0, "target": 0.0, "pre_market": 220.0},
                "XLF": {"price": 45.0, "change": 0.0, "target": 0.0, "pre_market": 45.0},
                "XLV": {"price": 140.0, "change": 0.0, "target": 0.0, "pre_market": 140.0},
                "XLY": {"price": 180.0, "change": 0.0, "target": 0.0, "pre_market": 180.0},
                "XLP": {"price": 80.0, "change": 0.0, "target": 0.0, "pre_market": 80.0},
                "XLE": {"price": 90.0, "change": 0.0, "target": 0.0, "pre_market": 90.0},
                "XLI": {"price": 130.0, "change": 0.0, "target": 0.0, "pre_market": 130.0},
                "XLB": {"price": 90.0, "change": 0.0, "target": 0.0, "pre_market": 90.0},
                "XLC": {"price": 95.0, "change": 0.0, "target": 0.0, "pre_market": 95.0},
                "XLU": {"price": 75.0, "change": 0.0, "target": 0.0, "pre_market": 75.0},
                "XLRE": {"price": 40.0, "change": 0.0, "target": 0.0, "pre_market": 40.0},
            }
            market_data[ticker] = defaults.get(
                ticker, {"price": 100.0, "change": 0.0, "target": 0.0, "pre_market": 100.0}
            )
    return market_data


def fetch_ai_insights_split(
    market_data, portfolio_stocks, date_str, day_name, investing_headlines
):
    api_keys = get_all_groq_keys()
    if not api_keys:
        print("❌ ERROR: No Groq API keys found! Using cached/defaults.")
        cached = load_ai_cache()
        return cached if cached else {}

    market_summary = {
        t: f"Price: {d.get('price')}, Change: {d.get('change')}%"
        for t, d in market_data.items()
    }

    headlines_formatted = (
        "\n".join([
            f"- Title: {h['title']} | Link: {h['link']}"
            for h in investing_headlines
        ])
        if investing_headlines
        else "No headlines available."
    )

    combined_result = load_ai_cache()
    if not isinstance(combined_result, dict):
        combined_result = {}

    # ==========================================
    # PART 1: Macro, Indices, Geopolitics & Deep News
    # ==========================================
    print("🔄 Starting Groq AI Part 1 (Macro, Indices & News)...")
    part1_success = False
    for key_name, api_key in api_keys:
        if part1_success:
            break
        try:
            client = Groq(
                api_key=api_key, base_url="https://groq-proxy.avichy65.workers.dev"
            )
            print(f"🤖 Connecting to Groq AI Part 1 using {key_name}...")

            for model_name in SAFE_MODEL_HIERARCHY:
                try:
                    print(f"🎯 Trying model: {model_name} (Part 1)...")
                    prompt1 = f"""
You are an expert Chief Market Strategist who explains financial and geopolitical markets clearly, deeply, and professionally. Output a valid JSON object ONLY.

🚨 STRICT GUIDELINES & FORMATTING:
1. LANGUAGE & ACCURACY: Write in completely standard, fluent, and professional Hebrew financial terminology ONLY. Never use bizarre translation errors, slang, or unrelated words (such as translating financial terms incorrectly like "צנון"). At least 95% accurate.
2. CLEAN TEXT: Do NOT include internal artifact prefixes like "analysis:", "strategy:", "recommendations:", or "המלצה:" at the beginning of any text field. Start the analysis directly with the content.
3. UNIFORM "לסיכום:" FORMAT: For EVERY single analysis field below (indices, USD/ILS, oil, gold, btc, and news), you MUST include a new line with exact text: "לסיכום:" followed directly by the practical implication (start directly with the conclusion without repeating phrases like "זה אומר ש...").
4. DEPTH: Provide comprehensive, professional analysis in clear Hebrew. Avoid generic clichés.
5. NO INTRODUCTORY LABELS: Start writing immediately without labels like "ניתוח ה-...".

Today is {day_name}, Date: {date_str}.

Headlines from Investing.com:
{headlines_formatted}

Current Market Data:
{json.dumps(market_summary, ensure_ascii=False)}

Return a valid JSON object with exactly these keys:
1. SP500_ANALYSIS (Must include \n\nלסיכום:\n)
2. NASDAQ_ANALYSIS (Must include \n\nלסיכום:\n)
3. DOW_ANALYSIS (Must include \n\nלסיכום:\n)
4. VIX_ANALYSIS (Must include \n\nלסיכום:\n)
5. DXY_ANALYSIS (Must include \n\nלסיכום:\n)
6. USD_ILS_EXPLANATION (Must include \n\nלסיכום:\n)
7. OIL_EXPLANATION (Must include \n\nלסיכום:\n)
8. GOLD_EXPLANATION (Must include \n\nלסיכום:\n)
9. BTC_EXPLANATION (Must include \n\nלסיכום:\n)
10. US_MARKET_NEWS (Comprehensive, deep analysis of US market news)
11. IL_MARKET_NEWS (Comprehensive, deep analysis of Israeli market news and Shekel)
12. COMMUNITY_SENTIMENT
13. ANALYST_POINT_1
14. ANALYST_POINT_2
"""

                    response1 = client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "user", "content": prompt1}],
                        response_format={"type": "json_object"},
                        max_tokens=4096,
                    )
                    raw_text1 = response1.choices[0].message.content.strip()
                    parsed1 = json.loads(raw_text1)
                    combined_result.update(parsed1)
                    print(
                        f"✅ Successfully parsed Part 1 JSON using model: {model_name}"
                        f" and key: {key_name}"
                    )
                    part1_success = True
                    break
                except Exception as model_err:
                    print(f"⚠️ Model {model_name} failed: {model_err}")
                    if "429" in str(model_err) or "rate_limit_exceeded" in str(model_err):
                        print("⏳ Rate limit hit. Waiting 30 seconds...")
                        time.sleep(30)
                    else:
                        time.sleep(2)
        except Exception as e:
            print(f"⚠️ Part 1 key attempt failed with {key_name}: {e}")

    # ==========================================
    # PART 2: Stocks, Catalysts, Risk Management & Action
    # ==========================================
    print("🔄 Starting Groq AI Part 2 (Stocks, Catalysts & Strategy)...")
    part2_success = False
    for key_name, api_key in api_keys:
        if part2_success:
            break
        try:
            client = Groq(
                api_key=api_key, base_url="https://groq-proxy.avichy65.workers.dev"
            )
            print(f"🤖 Connecting to Groq AI Part 2 using {key_name}...")

            for model_name in SAFE_MODEL_HIERARCHY:
                try:
                    print(f"🎯 Trying model: {model_name} (Part 2)...")
                    prompt2 = f"""
You are an expert Chief Market Strategist. Output a valid JSON object ONLY.

🚨 STRICT GUIDELINES & FORMATTING:
1. LANGUAGE & ACCURACY: Write in completely standard, fluent, and professional Hebrew financial terminology ONLY. At least 95% accurate.
2. CLEAN TEXT: Do NOT include internal artifact prefixes like "analysis:", "strategy:", "recommendations:", or "המלצה:" at the beginning of any text field. Start the analysis directly with the content.
3. UNIFORM "לסיכום:" FORMAT: For Catalysts, Risk Management, and Action Recommendations, every point MUST include a new line with exact text: "לסיכום:" followed directly by the practical implication.
4. DEPTH & ADVANCED INSIGHTS: Avoid obvious, generic statements. Provide advanced, sharp professional insights for risk management and action recommendations.
5. `market_news`: Array of at least 10 items. EVERY description MUST start with "סיכום הכתבה: " followed by a deep summary and conclude with a new line "לסיכום:".
6. `long_term_stocks`: EXACTLY 10 corporate stocks. Each object: ticker, name, desc, news, why_invest.
7. `swing_stocks`: EXACTLY 10 corporate stocks. Each object: ticker, name, desc, news, why_invest.

Today is {day_name}, Date: {date_str}.

Headlines from Investing.com:
{headlines_formatted}

Current Market Data:
{json.dumps(market_summary, ensure_ascii=False)}

Return a valid JSON object with exactly these 8 keys:
1. long_term_stocks
2. swing_stocks
3. market_news
4. CATALYST_EARNINGS (Deep analysis of earnings reports. Must include \n\nלסיכום:\n)
5. CATALYST_MONETARY (Deep analysis of monetary policy/Fed. Must include \n\nלסיכום:\n)
6. CATALYST_HARDWARE (Deep analysis of hardware/infrastructure investments. Must include \n\nלסיכום:\n)
7. RISK_MANAGEMENT_TEXT (Advanced, non-obvious professional risk management strategy. Must include \n\nלסיכום:\n)
8. ACTION_RECOMMENDATIONS_TEXT (Advanced, specific tactical recommendations for investors. Must include \n\nלסיכום:\n)
"""

                    response2 = client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "user", "content": prompt2}],
                        response_format={"type": "json_object"},
                        max_tokens=4096,
                    )
                    raw_text2 = response2.choices[0].message.content.strip()
                    parsed2 = json.loads(raw_text2)
                    combined_result.update(parsed2)
                    print(
                        f"✅ Successfully parsed Part 2 JSON using model: {model_name}"
                        f" and key: {key_name}"
                    )
                    part2_success = True
                    break
                except Exception as model_err:
                    print(f"⚠️ Model {model_name} failed: {model_err}")
                    if "429" in str(model_err) or "rate_limit_exceeded" in str(model_err):
                        print("⏳ Rate limit hit. Waiting 30 seconds...")
                        time.sleep(30)
                    else:
                        time.sleep(2)
        except Exception as e:
            print(f"⚠️ Part 2 key attempt failed with {key_name}: {e}")

    combined_result["ai_updated_at"] = f"{date_str} | {time.strftime('%H:%M')}"
    return combined_result


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
    "REAL_ESTATE": "XLRE",
}

cached_ai_init = load_ai_cache()
init_lt = cached_ai_init.get("long_term_stocks", LT_STOCKS_META)
if not isinstance(init_lt, list) or not init_lt:
    init_lt = LT_STOCKS_META
init_sw = cached_ai_init.get("swing_stocks", SW_STOCKS_META)
if not isinstance(init_sw, list) or not init_sw:
    init_sw = SW_STOCKS_META

base_market_tickers = list(
    set(
        [
            "GC=F",
            "CL=F",
            "BTC-USD",
            "USDILS=X",
            "DX-Y.NYB",
            "^GSPC",
            "^NDX",
            "^DJI",
            "^VIX",
        ]
        + list(sector_tickers_map.values())
        + list(portfolio_buys.keys())
        + [
            s.get("ticker") or s.get("symbol")
            for s in init_lt
            if isinstance(s, dict) and (s.get("ticker") or s.get("symbol"))
        ]
        + [
            s.get("ticker") or s.get("symbol")
            for s in init_sw
            if isinstance(s, dict) and (s.get("ticker") or s.get("symbol"))
        ]
    )
)


def build_structured_stocks_html(stocks_meta, market_data, section_title):
    html_parts = [
        f'<div class="text-lg font-bold text-cyan-400 mb-4 mt-2 text-right"'
        f' dir="rtl">{section_title}</div>'
    ]
    if not isinstance(stocks_meta, list) or not stocks_meta:
        stocks_meta = LT_STOCKS_META

    for s in stocks_meta:
        if isinstance(s, str):
            ticker = s.strip().upper()
            name = ticker
            desc = "מניה מובילה שנבחרה על ידי מערכת ה-AI."
            news = "מעקב יומי וניתוח מומנטום בשוק."
            why_invest = "פוטנציאל תשואה אטרקטיבי וניהול פיננסי יציב."
        elif isinstance(s, dict):
            ticker = str(
                s.get("ticker") or s.get("symbol") or s.get("name") or ""
            ).strip().upper()
            if not ticker:
                continue
            name = s.get("name") or s.get("company") or s.get("title") or ticker
            desc = (
                s.get("desc")
                or s.get("description")
                or s.get("reason")
                or "עיסוק ופעילות גלובלית בשווקים."
            )
            news = (
                s.get("news")
                or s.get("rationale")
                or s.get("update")
                or "עדכון וניתוח יומי."
            )
            news = re.sub(r"^סיכום הכתבה:\s*", "", news)
            why_invest = (
                s.get("why_invest")
                or s.get("investment_reason")
                or "מומנטום חיובי ונתונים פונדמנטליים חזקים המצדיקים כדאיות השקעה."
            )
        else:
            continue

        data = market_data.get(ticker, {})
        price = format_num(data.get("price", 0))
        pre_market = format_num(data.get("pre_market", 0))

        raw_target = data.get("target", 0)
        target_html = ""
        if raw_target and float(raw_target) > 0:
            target_val = f"${format_num(raw_target)}"
            target_html = f"<div><strong>יעד אנליסטים ממוצע:</strong> {target_val}</div>"

        change_val = data.get("change", 0.0)

        sign = "+" if change_val > 0 else ""
        color = "#2ecc71" if change_val >= 0 else "#e74c3c"
        change_str = (
            f'<span dir="ltr" style="color: {color}; font-weight: bold; display:'
            f' inline-block;">{sign}{change_val:.2f}%</span>'
        )

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
                {target_html}
                <div><strong>רווח יום מסחר אחרון:</strong> {change_str}</div>
                <div><strong>עיסוק החברה:</strong> {desc}</div>
                <div><strong>חדשות ורציונל יומי:</strong> {news}</div>
                <div><strong>למה כדאי להשקיע במניה:</strong> {why_invest}</div>
            </div>
        </div>
        """
        html_parts.append(card_html)
    return "".join(html_parts)


def build_market_news_html(market_news_list):
    if not isinstance(market_news_list, list) or not market_news_list:
        return (
            '<div class="text-gray-400 text-right" dir="rtl">אין חדשות שוק זמינות'
            " כרגע.</div>"
        )

    html_parts = []
    for item in market_news_list:
        if not isinstance(item, dict):
            continue
        p_link = item.get("news_link", "https://il.investing.com")
        p_title = item.get("news_title", "עדכון שוק יומי")
        p_desc = item.get("news_desc", "")
        if p_desc and not p_desc.startswith("סיכום הכתבה:"):
            p_desc = f"סיכום הכתבה: {p_desc}"

        desc_block = (
            f'<p class="text-gray-300 mt-2">{p_desc}</p>' if p_desc else ""
        )

        card_html = f"""
        <div class="bg-gray-800 p-4 rounded-xl border border-gray-700 shadow space-y-2 text-sm text-gray-300 text-right" dir="rtl">
            <h3 class="text-cyan-400 font-semibold text-base">כותרת: {p_title}</h3>
            <p class="mt-2">🔗 <strong>קישור למקור (Investing בעברית):</strong> <a href="{p_link}" target="_blank" class="text-cyan-400 hover:underline">{p_link}</a></p>
            {desc_block}
        </div>
        """
        html_parts.append(card_html)

    return "".join(html_parts)


if __name__ == "__main__":
    try:
        print("Fetching initial market data via direct API...")
        base_market_data = fetch_market_data(base_market_tickers)
        date_str = now_il.strftime("%d.%m.%Y")
        time_str = now_il.strftime("%H:%M")

        trigger_event = os.environ.get("TRIGGER_EVENT", "")
        current_hour = now_il.hour
        current_minute = now_il.minute
        is_manual = trigger_event == "workflow_dispatch"

        is_scheduled_ai_time = (
            trigger_event == "repository_dispatch"
            and (
                (current_hour == 10 and 10 <= current_minute <= 15)
                or (current_hour == 16 and 40 <= current_minute <= 45)
                or (current_hour == 23 and 40 <= current_minute <= 45)
            )
        )

        is_ai_time = is_manual or is_scheduled_ai_time
        is_yahoo_only = not is_ai_time

        investing_headlines = fetch_investing_news()

        ai_insights = {}
        if is_yahoo_only:
            ai_insights = load_ai_cache()
        else:
            ai_insights = fetch_ai_insights_split(
                base_market_data,
                portfolio_buys,
                date_str,
                day_name,
                investing_headlines,
            )
            if ai_insights and isinstance(ai_insights, dict) and len(ai_insights) > 3:
                save_ai_cache(ai_insights)

        market_news_data = ai_insights.get("market_news", [])
        if not isinstance(market_news_data, list) or len(market_news_data) < 10:
            market_news_data = []
            for h in investing_headlines[:12]:
                market_news_data.append({
                    "news_link": h["link"],
                    "news_title": h["title"],
                    "news_desc": (
                        f"סיכום הכתבה: הידיעה עוסקת ב-{h['title']} ומנתחת את ההשלכות הרוחביות על הכלכלה הגלובלית.<br><strong>לסיכום:</strong><br>עבור המשקיע הממוצע, מדובר בהתפתחות המחייבת מעקב אחר תנודות המחירים."
                    ),
                })
            ai_insights["market_news"] = market_news_data

        new_lt = ai_insights.get("long_term_stocks", LT_STOCKS_META)
        if not isinstance(new_lt, list) or not new_lt:
            new_lt = LT_STOCKS_META

        new_sw = ai_insights.get("swing_stocks", SW_STOCKS_META)
        if not isinstance(new_sw, list) or not new_sw:
            new_sw = SW_STOCKS_META

        extra_tickers = []
        for s in new_lt + new_sw:
            if isinstance(s, dict):
                t = s.get("ticker") or s.get("symbol")
                if t and t not in base_market_data:
                    extra_tickers.append(t)
        if extra_tickers:
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

        usd_ils_p = usd_ils_data.get("price", 3.65)
        if not usd_ils_p or usd_ils_p <= 1.0:
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
        gold_p = gold_data.get("price", 2400.0)
        gold_c = gold_data.get("change", 0)
        gold_price = f"${format_num(gold_p)}"
        gold_change = format_pct_colored(gold_c)

        btc_data = base_market_data.get("BTC-USD", {})
        btc_p = btc_data.get("price", 60000.0)
        btc_c = btc_data.get("change", 0)
        btc_price = f"${format_num(btc_p)}"
        btc_change = format_pct_colored(btc_c)

        sector_chart_list = []
        for s_name, s_ticker in sector_tickers_map.items():
            s_data = base_market_data.get(s_ticker, {})
            chg = float(s_data.get("change", 0.0))
            price_val = float(s_data.get("price", 100.0))
            sector_chart_list.append(
                {"name": s_name, "change": chg, "price": price_val, "value": price_val}
            )

        with open(TEMPLATE_FILE, "r", encoding="utf-8-sig") as f:
            content = f.read()

        lt_stocks_data = ai_insights.get("long_term_stocks", LT_STOCKS_META)
        if not isinstance(lt_stocks_data, list) or not lt_stocks_data:
            lt_stocks_data = LT_STOCKS_META

        sw_stocks_data = ai_insights.get("swing_stocks", SW_STOCKS_META)
        if not isinstance(sw_stocks_data, list) or not sw_stocks_data:
            sw_stocks_data = SW_STOCKS_META

        lt_html = build_structured_stocks_html(
            lt_stocks_data,
            base_market_data,
            "קבוצה א': מניות להשקעה ארוכת טווח (Long-Term Core)",
        )
        sw_html = build_structured_stocks_html(
            sw_stocks_data,
            base_market_data,
            "קבוצה ב': מניות למסחר סווינג לטווח קצר (Swing Trading)",
        )
        news_html = build_market_news_html(ai_insights.get("market_news", []))

        portfolio_js_list = []
        for ticker, info in portfolio_buys.items():
            if not isinstance(info, dict):
                continue
            try:
                buy_p = float(info.get("buy") or info.get("buyPrice") or 0.0)
                fetched_price_data = base_market_data.get(ticker, {})
                curr_p = fetched_price_data.get("price") or buy_p
                fetched_target = fetched_price_data.get("target") or 0.0
                pre_p = fetched_price_data.get("pre_market") or curr_p

                ret = ((curr_p - buy_p) / buy_p) * 100 if buy_p > 0 else 0.0
                sign = "+" if ret > 0 else ""
                color = "#2ecc71" if ret >= 0 else "#e74c3c"

                shares_count = info.get("shares", 0)
                company_name = (
                    info.get("name") or fetched_price_data.get("name") or ticker
                )

                target_str = f"${format_num(fetched_target)}" if fetched_target > 0 else ""

                portfolio_js_list.append({
                    "name": company_name,
                    "symbol": ticker,
                    "shares": shares_count,
                    "buyPrice": format_num(buy_p),
                    "current": f"${format_num(curr_p)}",
                    "pre": f"${format_num(pre_p)}",
                    "target": target_str,
                    "status": (
                        f"רווח: <span dir='ltr' style='color: {color}; font-weight:"
                        f" bold; display: inline-block;'>{sign}{ret:.2f}%</span>"
                    ),
                    "note": "",
                })
            except Exception as ex:
                print(f"Error processing portfolio stock {ticker}: {ex}")

        formatted_analyst_1, formatted_analyst_2 = format_analyst_points_clean(
            ai_insights.get("ANALYST_POINT_1", ""),
            ai_insights.get("ANALYST_POINT_2", ""),
        )

        replacements = {
            "LAST_UPDATED": f"{date_str} | {time_str}",
            "AI_LAST_UPDATED": ai_insights.get(
                "ai_updated_at", f"{date_str} | {time_str}"
            ),
            "DAY_NAME": day_name,
            "PORTFOLIO_COUNT": format_num(len(portfolio_buys), 0),
            "PORTFOLIO_STOCKS_JSON": json.dumps(
                portfolio_js_list, ensure_ascii=False
            ),
            "SECTORS_CHART_JSON": json.dumps(sector_chart_list, ensure_ascii=False),
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
            "SP500_ANALYSIS": format_ai_text(
                ai_insights.get("SP500_ANALYSIS", "")
            ),
            "NASDAQ_ANALYSIS": format_ai_text(
                ai_insights.get("NASDAQ_ANALYSIS", "")
            ),
            "DOW_ANALYSIS": format_ai_text(ai_insights.get("DOW_ANALYSIS", "")),
            "VIX_ANALYSIS": format_ai_text(ai_insights.get("VIX_ANALYSIS", "")),
            "DXY_ANALYSIS": format_ai_text(ai_insights.get("DXY_ANALYSIS", "")),
            "USD_ILS": usd_ils_price,
            "USD_ILS_CHANGE": usd_ils_change,
            "OIL_PRICE": oil_price,
            "OIL_CHANGE": oil_change,
            "GOLD_PRICE": gold_price,
            "GOLD_CHANGE": gold_change,
            "BTC_PRICE": btc_price,
            "BTC_CHANGE": btc_change,
            "USD_ILS_EXPLANATION": format_ai_text(
                ai_insights.get("USD_ILS_EXPLANATION", "")
            ),
            "OIL_EXPLANATION": format_ai_text(
                ai_insights.get("OIL_EXPLANATION", "")
            ),
            "GOLD_EXPLANATION": format_ai_text(
                ai_insights.get("GOLD_EXPLANATION", "")
            ),
            "BTC_EXPLANATION": format_ai_text(
                ai_insights.get("BTC_EXPLANATION", "")
            ),
            "US_MARKET_NEWS": format_ai_text(ai_insights.get("US_MARKET_NEWS", "")),
            "IL_MARKET_NEWS": format_ai_text(ai_insights.get("IL_MARKET_NEWS", "")),
            "CATALYST_EARNINGS": format_ai_text(
                ai_insights.get("CATALYST_EARNINGS", "")
            ),
            "CATALYST_MONETARY": format_ai_text(
                ai_insights.get("CATALYST_MONETARY", "")
            ),
            "CATALYST_HARDWARE": format_ai_text(
                ai_insights.get("CATALYST_HARDWARE", "")
            ),
            "COMMUNITY_SENTIMENT": format_ai_text(
                ai_insights.get("COMMUNITY_SENTIMENT", "")
            ),
            "ANALYST_POINT_1": formatted_analyst_1,
            "ANALYST_POINT_2": formatted_analyst_2,
            "RISK_MANAGEMENT_TEXT": format_ai_text(
                ai_insights.get("RISK_MANAGEMENT_TEXT", "")
            ),
            "ACTION_RECOMMENDATIONS_TEXT": format_ai_text(
                ai_insights.get("ACTION_RECOMMENDATIONS_TEXT", "")
            ),
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
            replacements[f"SECTOR_{s_key}_PRICE"] = f"${s_price}"
            replacements[f"SECTOR_{s_key}_PCT"] = (
                f'<span dir="ltr" style="color: {color}; font-weight: bold; display:'
                f' inline-block;">{sign}{s_change:.2f}%</span>'
            )

        for k, v in replacements.items():
            content = content.replace("{{" + k + "}}", str(v))

        content = re.sub(r"\{\{[A-Z0-9_]+\}\}", "''", content)

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"Successfully generated {OUTPUT_FILE}!")

    except Exception as e:
        print(f"❌ Critical Error in main execution: {e}")
        traceback.print_exc()
        exit(1)
