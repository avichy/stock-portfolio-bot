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
import pytz
import requests
from bs4 import BeautifulSoup
from groq import Groq

AI_CACHE_FILE = "ai_cache.json"
PORTFOLIO_FILE = "portfolio.json"
TEMPLATE_FILE = "index.template.html"
OUTPUT_FILE = "index.html"

GITHUB_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")


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


def filter_hallucinations(text, headlines_list):
    if not text or not isinstance(text, str):
        return ""

    headline_keywords = set()
    for h in headlines_list:
        title = h.get('title', '') if isinstance(h, dict) else str(h)
        words = [w.strip(".,!?()[]{}<>:-") for w in title.split() if len(w.strip(".,!?()[]{}<>:-")) > 3]
        headline_keywords.update(words)

    sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    valid_sentences = []

    for sentence in sentences:
        if any(k in sentence for k in ['לסיכום', 'מומלץ', 'תנודתיות', 'שוק', 'מגמה', 'מסחר', 'מדד', 'ישראל', 'תל אביב', 'בנק ישראל']):
            valid_sentences.append(sentence)
            continue

        sentence_words = set(w.strip(".,!?()[]{}<>:-") for w in sentence.split() if len(w.strip(".,!?()[]{}<>:-")) > 3)
        intersection = sentence_words.intersection(headline_keywords)
        
        if len(headline_keywords) == 0 or len(intersection) > 0 or "מקור:" in sentence:
            valid_sentences.append(sentence)
        else:
            print(f"🛡️ Hallucination Filter: Omitted unverified sentence -> '{sentence[:40]}...'")

    return " ".join(valid_sentences)


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


def force_source_on_newline(text):
    if not isinstance(text, str):
        return str(text)

    text = re.sub(r"(^|<br>)\s*;\s*", r"\1", text)
    text = re.sub(r"(^|<br>)\s*,\s*", r"\1", text)
    text = re.sub(
        r"<br>\s*(\(מקור\s*:[^)]+\))", r" \1", text, flags=re.IGNORECASE
    )
    text = re.sub(
        r"(\(מקור\s*:[^)]+\))(?!\s*<br\s*/?>)",
        r"\1<br>",
        text,
        flags=re.IGNORECASE,
    )

    return text


def format_text_with_conclusion(text, prefix_num=None):
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

    source_match = re.search(r"(\(מקור\s*:[^)]+\))", text, re.IGNORECASE)
    source_str = source_match.group(1) if source_match else ""
    if source_str:
        text = text.replace(source_str, "").strip()

    cleaned = (
        text.replace("{", "")
        .replace("}", "")
        .replace("[", "")
        .replace("]", "")
        .replace('"', "")
        .replace("'", "")
    )

    cleaned = re.sub(
        r"^(?:ניהול\s*סיכונים|המלצות\s*פעולה|סיכונים|ניתוח\s+הסבר[^\n:]+|קָטָלִיסט[^\n:]*|השפעות[^\n:]*|סיכום הכתבה:?)\s*[:\-]?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"מה\s*זה\s*אומר\s*[:\-]*", "", cleaned, flags=re.IGNORECASE
    ).strip()

    explanation = cleaned
    conclusion = ""

    if "לסיכום" in cleaned:
        parts = re.split(r"לסיכום\s*[:\-]*", cleaned, flags=re.IGNORECASE)
        explanation = parts[0].strip()
        if len(parts) > 1:
            conclusion = parts[1].strip()
            conclusion = re.sub(
                r"לסיכום\s*[:\-]*", "", conclusion, flags=re.IGNORECASE
            ).strip()

    explanation = re.sub(r'\s*\n+\s*', ' ', explanation).strip()
    conclusion = re.sub(r'\s*\n+\s*', ' ', conclusion).strip()
    
    explanation = re.sub(r'\s*\(?מקור:[^\)]+\)?', '', explanation)
    explanation = re.sub(r'מקור:\s*.*?(?=<|$)', '', explanation)
    conclusion = re.sub(r'\s*\(?מקור:[^\)]+\)?', '', conclusion)
    conclusion = re.sub(r'מקור:\s*.*?(?=<|$)', '', conclusion)

    explanation = re.sub(r"(^|<br>)\s*;\s*", r"\1", explanation)
    conclusion = re.sub(r"(^|<br>)\s*;\s*", r"\1", conclusion)

    sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", explanation) if s.strip()
    ]

    if not conclusion:
        if len(sentences) > 1:
            conclusion = sentences[-1]
            explanation = " ".join(sentences[:-1])
        else:
            conclusion = ""

    explanation = re.sub(
        r"לסיכום\s*[:\-]*", "", explanation, flags=re.IGNORECASE
    ).strip()
    conclusion = re.sub(
        r"^(|בנוסף|כמו כן|לפיכך|על כן|לכן)\s*[,:\-]*\s*", "", conclusion
    ).strip()

    conclusion = re.sub(r"\(מקור\s*:[^)]+\)", "", conclusion).strip()

    explanation = re.sub(r'\s+(\d+\.\s+)', r'<br>\1', explanation)
    conclusion = re.sub(r'\s+(\d+\.\s+)', r'<br>\1', conclusion)

    if prefix_num is not None:
        explanation = re.sub(r"^\d+[\.\)]\s*", "", explanation).strip()
        if not explanation:
            explanation = text.strip()
        explanation = f"{prefix_num}. {explanation}"

    if source_str:
        explanation = explanation.strip() + " " + source_str

    if conclusion:
        formatted_content = f"{explanation}<br><strong>לסיכום:</strong><br>{conclusion}"
    else:
        formatted_content = explanation

    formatted_content = format_numbers_in_text(formatted_content)
    formatted_content = force_source_on_newline(formatted_content)

    return (
        f'<span class="leading-relaxed text-sm text-gray-200 block'
        f' mt-1 mb-4">{formatted_content}</span>'
    )


def format_news_description(text):
    if isinstance(text, list):
        text = " ".join(str(item) for item in text)
    elif not isinstance(text, str):
        text = str(text)

    cleaned = text.strip()
    cleaned = (
        cleaned.replace("{", "")
        .replace("}", "")
        .replace("[", "")
        .replace("]", "")
        .replace('"', "")
        .replace("'", "")
    )

    cleaned = re.sub(
        r"^(?:סיכום הכתבה:?|לסיכום:?)\s*[:\-]?\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    ).strip()

    cleaned = re.sub(r'\s*\n+\s*', ' ', cleaned).strip()
    cleaned = re.sub(r'\s*\(?מקור:[^\)]+\)?', '', cleaned)
    cleaned = re.sub(r'מקור:\s*.*?(?=<|$)', '', cleaned)

    cleaned = format_numbers_in_text(cleaned)
    cleaned = force_source_on_newline(cleaned)

    return cleaned


def format_phase1_text(text):
    return format_text_with_conclusion(text)


def format_analyst_text(text):
    if not text or not str(text).strip() or str(text).strip() in ["''", '""']:
        text = "אין נתונים עדכניים זמינים כרגע מסקירת האנליסטים. לסיכום: מומלץ להמתין לעדכונים נוספים בשווקים."
    if "לסיכום" not in str(text):
        text = str(text).strip() + " לסיכום: מומלץ לעקוב אחר התפתחות המגמות בשווקים."
    return format_text_with_conclusion(text, prefix_num=None)


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
                        {
                            "title": title.text.strip(),
                            "link": link.text.strip(),
                            "source": "Investing.com",
                        }
                    )
            return news_items[:15]
    except Exception as e:
        print(f"Warning: Error fetching Hebrew Investing RSS: {e}")
        return []


def fetch_bizportal_news():
    url = "https://www.bizportal.co.il/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"Failed to fetch Bizportal, status code: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        news_items = []
        seen_titles = set()
        
        for a_tag in soup.find_all('a', href=True):
            text = a_tag.get_text(strip=True)
            href = a_tag['href']
            if len(text) > 25 and text not in seen_titles:
                if not any(w in text for w in ["התחבר", "הירשם", "פרסם אצלנו", "תנאי שימוש", "צור קשר", "חיפוש", "מערכת", "שירות לקוחות", "תפריט"]):
                    if href.startswith('/'):
                        link = f"https://www.bizportal.co.il{href}"
                    elif not href.startswith('http'):
                        link = f"https://www.bizportal.co.il/{href}"
                    else:
                        link = href
                        
                    seen_titles.add(text)
                    news_items.append({
                        "title": text,
                        "link": link,
                        "source": "Bizportal"
                    })
        return news_items[:15]
    except Exception as e:
        print(f"Warning: Error fetching Bizportal: {e}")
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
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "desc": "פיתוח מכשירים ניידים, שירותים דיגיטליים וטכנולוגיה צרכנית.",
        "news": "תנועות מחיר חסונות וביקושים יציבים למוצרי הדגל סביב השקות ואקוסיסטם.",
        "why_invest": "מומנטום מסחר חזק ובסיס נרחב המייצרים תנועות סווינג צפויות ואמינות.",
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
                "XLK": {
                    "price": 220.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 220.0,
                },
                "XLF": {
                    "price": 45.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 45.0,
                },
                "XLV": {
                    "price": 140.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 140.0,
                },
                "XLY": {
                    "price": 180.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 180.0,
                },
                "XLP": {
                    "price": 80.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 80.0,
                },
                "XLE": {
                    "price": 90.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 90.0,
                },
                "XLI": {
                    "price": 130.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 130.0,
                },
                "XLB": {
                    "price": 90.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 90.0,
                },
                "XLC": {
                    "price": 95.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 95.0,
                },
                "XLU": {
                    "price": 75.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 75.0,
                },
                "XLRE": {
                    "price": 40.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 40.0,
                },
            }
            market_data[ticker] = defaults.get(
                ticker,
                {
                    "price": 100.0,
                    "change": 0.0,
                    "target": 0.0,
                    "pre_market": 100.0,
                },
            )
    return market_data


def fetch_ai_insights_split(
    market_data,
    portfolio_stocks,
    date_str,
    day_name,
    investing_headlines,
    bizportal_headlines,
    now_il_str,
):
    api_keys = get_all_groq_keys()
    if not api_keys:
        print("❌ ERROR: No Groq API keys found! Using cached/defaults.")
        cached = load_ai_cache()
        return cached if cached else {}

    safe_investing_headlines = investing_headlines[:8] if investing_headlines else []
    safe_bizportal_headlines = bizportal_headlines[:8] if bizportal_headlines else []

    market_summary = {
        t: f"Price: {d.get('price')}, Change: {d.get('change')}%"
        for t, d in market_data.items()
    }

    inv_formatted = (
        "\n".join(
            [f"- Title: {h['title']} | Source: {h.get('source', 'Investing.com')} | Link: {h['link']}" for h in safe_investing_headlines]
        )
        if safe_investing_headlines
        else "No US headlines."
    )
    biz_formatted = (
        "\n".join(
            [f"- Title: {h['title']} | Source: {h.get('source', 'Bizportal')} | Link: {h['link']}" for h in safe_bizportal_headlines]
        )
        if safe_bizportal_headlines
        else "No Israeli headlines."
    )
    
    all_safe_headlines = safe_investing_headlines + safe_bizportal_headlines

    combined_result = load_ai_cache()
    if not isinstance(combined_result, dict):
        combined_result = {}

    # --- PART 1: Indices & Macro Explanations ---
    print("🔄 Starting Groq AI Part 1 (Indices & Macro Explanations)...")
    for key_name, api_key in api_keys:
        try:
            client = Groq(
                api_key=api_key,
                base_url="https://groq-proxy.avichy65.workers.dev",
            )
            print(f"🤖 Connecting to Groq AI Part 1 using {key_name}...")

            prompt1 = f"""
You are an expert Chief Market Strategist. Output a valid JSON object ONLY.

🚨 STRICT ZERO-HALLUCINATION & SOURCE SEPARATION GUIDELINES:
1. LANGUAGE: Hebrew ONLY (עברית מלאה בלבד). No English text in the analysis.
2. NO FABRICATION: Do not invent data.
3. MANDATORY CONCRETE CONCLUSION (חובה סיכום חד וקונקרטי): 
   - Every single analysis field MUST include a clear explanation followed explicitly by the word "לסיכום:" and a specific concluding sentence at the end.
   - **ABSOLUTELY FORBIDDEN**: Do NOT write generic filler conclusions.
4. SOURCE FORMATTING: Sources must appear **ONLY** in the main explanation body on the same line followed by `<br>`, **NEVER** inside or after the "לסיכום:" section.

Today is {day_name}, Date: {date_str}.

Current Market Data:
{json.dumps(market_summary, ensure_ascii=False)}

Return a valid JSON object with exactly these 9 keys:
1. SP500_ANALYSIS
2. NASDAQ_ANALYSIS
3. DOW_ANALYSIS
4. VIX_ANALYSIS
5. DXY_ANALYSIS
6. USD_ILS_EXPLANATION
7. OIL_EXPLANATION
8. GOLD_EXPLANATION
9. BTC_EXPLANATION
"""

            response1 = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[{"role": "user", "content": prompt1}],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=4000,
            )

            raw_text1 = response1.choices[0].message.content.strip()
            parsed1 = json.loads(raw_text1)
            combined_result.update(parsed1)
            print("Successfully parsed Part 1 JSON using key:", key_name)
            break
        except Exception as e:
            print(f"⚠️ Part 1 attempt failed with {key_name}: {e}")
            if "429" in str(e) or "rate_limit_exceeded" in str(e) or "413" in str(e):
                print(f"⏳ Rate limit / Size limit hit. Waiting 60 seconds...")
                time.sleep(60)
            else:
                time.sleep(5)

    time.sleep(3)

    # --- PART 2: News, Sentiment & Analyst Points ---
    print("🔄 Starting Groq AI Part 2 (News, Sentiment & Analyst Points)...")
    for key_name, api_key in api_keys:
        try:
            client = Groq(
                api_key=api_key,
                base_url="https://groq-proxy.avichy65.workers.dev",
            )
            print(f"🤖 Connecting to Groq AI Part 2 using {key_name}...")

            prompt2 = f"""
You are an expert Chief Market Strategist. Output a valid JSON object ONLY.

🚨 STRICT ZERO-HALLUCINATION & SOURCE SEPARATION GUIDELINES:
1. LANGUAGE: Hebrew ONLY (עברית מלאה בלבד). No English text in the analysis.
2. NO FABRICATION: Do not invent news.
3. MANDATORY CONCRETE CONCLUSION (חובה סיכום חד וקונקרטי): 
   - Every single analysis field MUST include a clear explanation followed explicitly by the word "לסיכום:" and a specific concluding sentence at the end.
4. STRICT SOURCE SEPARATION & PRIORITIZATION (CRITICAL):
   - **US_MARKET_NEWS**: MUST use **ONLY** the US / Global Headlines from Investing.com provided below. Focus strictly on Wall Street, US indices, US macro, and global trade. Must explicitly mention Investing.com as the source. **NEVER leave this empty.**
   - **IL_MARKET_NEWS**: MUST use **ONLY** the Israeli Market Headlines from Bizportal provided below. **PRIORITY 1**: You MUST prioritize and highlight **geopolitical events, security/military developments, macroeconomic shifts (inflation, Bank of Israel interest rate, currency), and major local business/energy news**. Focus on how these geopolitical/macro events impact the Israeli economy and TASE. Must explicitly mention Bizportal as the source. **NEVER** put Investing.com headlines or American stocks here.
5. CROSS-IMPACT MECHANISM (חוק השפעה צולבת): Do not discard local, regional, or geopolitical events if they carry a clear economic transmission mechanism affecting global energy, inflation, or US/global markets. Explicitly analyze their broader financial transmission where applicable.
6. SOURCE FORMATTING: Sources must appear **ONLY** in the main explanation body on the same line followed by `<br>`, **NEVER** inside or after the "לסיכום:" section.

Today is {day_name}, Date: {date_str}.

--- US / Global Headlines (Investing.com) ---
{inv_formatted}

--- Israeli Market Headlines (Bizportal - Prioritize Geopolitical & Macro) ---
{biz_formatted}

Return a valid JSON object with exactly these 5 keys:
1. US_MARKET_NEWS
2. IL_MARKET_NEWS
3. COMMUNITY_SENTIMENT
4. ANALYST_POINT_1
5. ANALYST_POINT_2
"""

            response2 = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[{"role": "user", "content": prompt2}],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=4000,
            )

            raw_text2 = response2.choices[0].message.content.strip()
            parsed2 = json.loads(raw_text2)
            
            for k, v in parsed2.items():
                if isinstance(v, str):
                    if k in ["US_MARKET_NEWS", "IL_MARKET_NEWS"]:
                        filtered_v = filter_hallucinations(v, all_safe_headlines)
                    else:
                        filtered_v = v
                    parsed2[k] = filtered_v

            combined_result.update(parsed2)
            print("Successfully parsed Part 2 JSON using key:", key_name)
            break
        except Exception as e:
            print(f"⚠️ Part 2 attempt failed with {key_name}: {e}")
            if "429" in str(e) or "rate_limit_exceeded" in str(e) or "413" in str(e):
                print(f"⏳ Rate limit / Size limit hit. Waiting 60 seconds...")
                time.sleep(60)
            else:
                time.sleep(5)

    time.sleep(3)

    # --- PART 3: Stocks, Catalysts & Strategy ---
    print("🔄 Starting Groq AI Part 3 (Stocks, Catalysts & Strategy)...")
    for key_name, api_key in api_keys:
        try:
            client = Groq(
                api_key=api_key,
                base_url="https://groq-proxy.avichy65.workers.dev",
            )
            print(f"🤖 Connecting to Groq AI Part 3 using {key_name}...")

            prompt3 = f"""
You are an expert Chief Market Strategist. Output a valid JSON object ONLY.

🚨 STRICT ZERO-HALLUCINATION GUIDELINES:
1. LANGUAGE: Hebrew ONLY (עברית מלאה בלבד). Absolutely NO English text.
2. ZERO-HALLUCINATION ON NEWS & STOCKS: Do not invent catalysts or corporate news.
3. STOCK FORMAT (`long_term_stocks`, `swing_stocks`): MUST be a JSON array of objects with `ticker`, `name`, `desc`, `news`, `why_invest`.
4. PROFESSIONAL CATALYSTS (`CATALYST_EARNINGS`, `CATALYST_MONETARY`, `CATALYST_HARDWARE`): Write professional analytical paragraphs ending with a sharp, non-generic "לסיכום:".
5. `market_news`: Array of items. Each item MUST be an object containing: `news_title`, `news_link`, and `news_desc`.

Today is {day_name}, Date: {date_str}.

--- US / Global Headlines (Investing.com) ---
{inv_formatted}

--- Israeli Market Headlines (Bizportal) ---
{biz_formatted}

Current Market Data:
{json.dumps(market_summary, ensure_ascii=False)}

Return a valid JSON object with exactly these 8 keys:
1. long_term_stocks
2. swing_stocks
3. market_news
4. CATALYST_EARNINGS
5. CATALYST_MONETARY
6. CATALYST_HARDWARE
7. RISK_MANAGEMENT_TEXT
8. ACTION_RECOMMENDATIONS_TEXT
"""

            response3 = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=[{"role": "user", "content": prompt3}],
                response_format={"type": "json_object"},
                temperature=0.0,
                max_tokens=4000,
            )

            raw_text3 = response3.choices[0].message.content.strip()
            parsed3 = json.loads(raw_text3)
            
            for k, v in parsed3.items():
                if isinstance(v, str):
                    pass
                elif isinstance(v, list) and k == 'market_news':
                    for item in v:
                        if isinstance(item, dict) and 'news_desc' in item:
                            item['news_desc'] = filter_hallucinations(item['news_desc'], all_safe_headlines)

            combined_result.update(parsed3)
            print("Successfully parsed Part 3 JSON using key:", key_name)
            break
        except Exception as e:
            print(f"⚠️ Part 3 attempt failed with {key_name}: {e}")
            if "429" in str(e) or "rate_limit_exceeded" in str(e) or "413" in str(e):
                print(f"⏳ Rate limit / Size limit hit. Waiting 60 seconds...")
                time.sleep(60)
            else:
                time.sleep(5)

    combined_result["ai_updated_at"] = now_il_str
    return combined_result


israel_tz = pytz.timezone("Asia/Jerusalem")
now_il = datetime.now(israel_tz)
date_str = now_il.strftime("%d.%m.%Y")
time_str = now_il.strftime("%H:%M")
now_il_str = f"{date_str} | {time_str}"

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

forbidden_stock_tickers = set(sector_tickers_map.values()).union({
    "^GSPC", "^NDX", "^DJI", "^VIX", "DX-Y.NYB", "CL=F", "GC=F", "BTC-USD", "USDILS=X", "SPY", "QQQ"
})

def clean_stocks_list(stocks_list, default_meta):
    if not isinstance(stocks_list, list) or not stocks_list:
        return default_meta
    cleaned = []
    for s in stocks_list:
        if isinstance(s, dict):
            t = str(s.get("ticker") or s.get("symbol") or "").strip().upper()
            if t and t not in forbidden_stock_tickers:
                cleaned.append({
                    "ticker": t,
                    "name": s.get("name") or s.get("company") or t,
                    "desc": s.get("desc") or s.get("description") or f"חברה מובילה ({t}) הפועלת בשוק הגלובלי.",
                    "news": s.get("news") or s.get("rationale") or "עדכון שוטף וניתוח טכני של תנועת המחיר.",
                    "why_invest": s.get("why_invest") or s.get("investment_reason") or "פוטנציאל תשואה חיובי בהתאם לנתונים הפונדמנטליים."
                })
        elif isinstance(s, str):
            t = s.strip().upper()
            if t and t not in forbidden_stock_tickers:
                matched = next((item for item in default_meta if item.get("ticker") == t), None)
                if matched:
                    cleaned.append(matched)
                else:
                    cleaned.append({
                        "ticker": t,
                        "name": t,
                        "desc": f"חברה מובילה ({t}) המרכזת עניין בשווקים.",
                        "news": "מעקב שוטף אחר התפתחות המסחר והמומנטום.",
                        "why_invest": "יחס סיכון-סיכוי אטרקטיבי לטווח המסחר הנוכחי."
                    })
    return cleaned if len(cleaned) >= 3 else default_meta

cached_ai_init = load_ai_cache()
init_lt = clean_stocks_list(cached_ai_init.get("long_term_stocks", LT_STOCKS_META), LT_STOCKS_META)
init_sw = clean_stocks_list(cached_ai_init.get("swing_stocks", SW_STOCKS_META), SW_STOCKS_META)

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
            if ticker in forbidden_stock_tickers:
                continue
            name = ticker
            desc = f"חברה מובילה ({ticker}) המרכזת עניין בשווקים."
            news = "מעקב שוטף אחר התפתחות המסחר והמומנטום."
            why_invest = "יחס סיכון-סיכוי אטרקטיבי לטווח המסחר הנוכחי."
        elif isinstance(s, dict):
            ticker = str(
                s.get("ticker") or s.get("symbol") or s.get("name") or ""
            ).strip().upper()
            if not ticker or ticker in forbidden_stock_tickers:
                continue
            name = s.get("name") or s.get("company") or s.get("title") or ticker
            desc = (
                s.get("desc")
                or s.get("description")
                or s.get("reason")
                or f"חברה מובילה ({ticker}) הפועלת בשוק הגלובלי."
            )
            news = (
                s.get("news")
                or s.get("rationale")
                or s.get("update")
                or "עדכון שוטף וניתוח טכני של תנועת המחיר."
            )
            news = re.sub(r"^סיכום הכתבה:\s*", "", news)
            news = force_source_on_newline(news)
            why_invest = (
                s.get("why_invest")
                or s.get("investment_reason")
                or "פוטנציאל תשואה חיובי בהתאם לנתונים הפונדמנטליים."
            )
            why_invest = force_source_on_newline(why_invest)
        else:
            continue

        data = market_data.get(ticker, {})
        price = format_num(data.get("price", 0))
        pre_market = format_num(data.get("pre_market", 0))

        raw_target = data.get("target", 0)
        target_html = ""
        if raw_target and float(raw_target) > 0:
            target_val = f"${format_num(raw_target)}"
            target_html = (
                f"<div><strong>יעד אנליסטים ממוצע:</strong> {target_val}</div>"
            )

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
        <div class="bg-gray-800/80 border border-gray-700/60 rounded-xl p-4 mb-4 shadow-md text-right overflow-hidden" dir="rtl">
            <div class="flex items-center gap-3 mb-3">
                <img src="{logo_url}" width="28" height="28" class="rounded-full bg-white p-0.5 object-contain" alt="{ticker}" onerror="this.onerror=null; this.src='https://s3-symbol-logo.tradingview.com/{clean_symbol_lower}.svg';">
                <span class="text-base font-bold text-white">{name} (טיקר: {ticker}):</span>
            </div>
            <div class="text-sm text-gray-300 space-y-1 break-words">
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
        p_link = (
            item.get("news_link")
            or item.get("link")
            or item.get("url")
            or "https://il.investing.com"
        )
        p_title = (
            item.get("news_title")
            or item.get("title")
            or item.get("headline")
            or "עדכון שוק יומי"
        )
        p_desc = (
            item.get("news_desc")
            or item.get("description")
            or item.get("summary")
            or item.get("desc")
            or ""
        )

        formatted_desc = format_news_description(p_desc)

        card_html = f"""
        <div class="bg-gray-800 p-4 rounded-xl border border-gray-700 shadow space-y-2 text-sm text-gray-300 text-right overflow-hidden" dir="rtl">
            <h3 class="text-cyan-400 font-semibold text-base break-words">{p_title}</h3>
            <p class="mt-2 break-words">🔗 <strong>קישור למקור:</strong> <a href="{p_link}" target="_blank" class="text-cyan-400 hover:underline" style="word-break: break-all;">{p_link}</a></p>
            <p class="mt-2 break-words"><strong>סיכום הכתבה:</strong><br>{formatted_desc}</p>
        </div>
        """
        html_parts.append(card_html)

    return "".join(html_parts)


if __name__ == "__main__":
    try:
        print("Fetching initial market data via direct API...")
        base_market_data = fetch_market_data(base_market_tickers)

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
        bizportal_headlines = fetch_bizportal_news()

        try:
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
                    bizportal_headlines,
                    now_il_str,
                )
                if (
                    ai_insights
                    and isinstance(ai_insights, dict)
                    and len(ai_insights) > 3
                ):
                    save_ai_cache(ai_insights)
        except Exception as e:
            print(f"Error handling AI insights: {e}")
            ai_insights = {}

        # 🛡️ Python-side Robust Fallback & Enforcement
        us_news_text = ai_insights.get("US_MARKET_NEWS", "")
        if not us_news_text or len(us_news_text.strip()) < 10 or "Investing.com" not in us_news_text:
            if investing_headlines:
                us_lines = [f"• {h['title']} (מקור: Investing.com)" for h in investing_headlines[:3]]
                us_news_text = "<br>".join(us_lines) + "<br>לסיכום: השווקים הבינלאומיים מתמקדים בנתוני המאקרו והמומנטום בוול סטריט."
            else:
                us_news_text = "אין עדכונים חדשותיים חדשים מ-Investing.com כרגע. (מקור: Investing.com)<br>לסיכום: השווקים בארה\"ב נסחרים בדריכות בהמתנה להודעות פד."

        il_news_text = ai_insights.get("IL_MARKET_NEWS", "")
        if not il_news_text or len(il_news_text.strip()) < 10 or "Investing.com" in il_news_text:
            if bizportal_headlines:
                il_lines = [f"• {h['title']} (מקור: Bizportal)" for h in bizportal_headlines[:3]]
                il_news_text = "<br>".join(il_lines) + "<br>לסיכום: השוק המקומי מושפע ישירות מהתפתחויות גיאופוליטיות ומדדי המאקרו."
            else:
                il_news_text = "אין עדכונים חדשותיים חדשים מ-Bizportal כרגע. (מקור: Bizportal)<br>לסיכום: הבורסה בתל אביב מתנהלת בהתאם למצב הביטחוני והכלכלי."

        ai_insights["US_MARKET_NEWS"] = us_news_text
        ai_insights["IL_MARKET_NEWS"] = il_news_text

        market_news_data = ai_insights.get("market_news", [])
        combined_all_headlines = investing_headlines[:4] + bizportal_headlines[:4]

        if not isinstance(market_news_data, list):
            market_news_data = []

        filled_news_data = []
        for idx, h in enumerate(combined_all_headlines[:8]):
            src_name = h.get('source', 'Investing.com')
            desc = (
                f"הידיעה עוסקת ב-{h['title']} ומנתחת את ההשלכות הרוחביות"
                f" על השווקים. (מקור: {src_name})"
            )
            if idx < len(market_news_data) and isinstance(
                market_news_data[idx], dict
            ):
                ai_item = market_news_data[idx]
                if ai_item.get("news_desc"):
                    desc = ai_item.get("news_desc")
            filled_news_data.append(
                {"news_link": h["link"], "news_title": h["title"], "news_desc": desc}
            )

        if filled_news_data:
            market_news_data = filled_news_data
        ai_insights["market_news"] = market_news_data

        new_lt = clean_stocks_list(ai_insights.get("long_term_stocks", LT_STOCKS_META), LT_STOCKS_META)
        new_sw = clean_stocks_list(ai_insights.get("swing_stocks", SW_STOCKS_META), SW_STOCKS_META)

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
                {
                    "name": s_name,
                    "change": chg,
                    "price": price_val,
                    "value": price_val,
                }
            )

        with open(TEMPLATE_FILE, "r", encoding="utf-8-sig") as f:
            content = f.read()

        lt_stocks_data = new_lt
        sw_stocks_data = new_sw

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

                ret = (
                    ((curr_p - buy_p) / buy_p) * 100 if buy_p > 0 else 0.0
                )
                sign = "+" if ret > 0 else ""
                color = "#2ecc71" if ret >= 0 else "#e74c3c"

                shares_count = info.get("shares", 0)
                company_name = (
                    info.get("name") or fetched_price_data.get("name") or ticker
                )

                target_str = f"${format_num(fetched_target)}" if fetched_target > 0 else ""

                portfolio_js_list.append(
                    {
                        "name": company_name,
                        "symbol": ticker,
                        "shares": shares_count,
                        "buyPrice": format_num(buy_p),
                        "current": f"${format_num(curr_p)}",
                        "pre": f"${format_num(pre_p)}",
                        "target": target_str,
                        "status": (
                            f"רווח: <span dir='ltr' style='color: {color};"
                            f" font-weight: bold; display: inline-block;'>{sign}{ret:.2f}%</span>"
                        ),
                        "note": "",
                    }
                )
            except Exception as ex:
                print(f"Error processing portfolio stock {ticker}: {ex}")

        formatted_analyst_1 = format_analyst_text(
            ai_insights.get("ANALYST_POINT_1", "")
        )
        formatted_analyst_2 = format_analyst_text(
            ai_insights.get("ANALYST_POINT_2", "")
        )

        replacements = {
            "LAST_UPDATED": now_il_str,
            "AI_LAST_UPDATED": ai_insights.get("ai_updated_at", now_il_str),
            "DAY_NAME": day_name,
            "PORTFOLIO_COUNT": format_num(len(portfolio_buys), 0),
            "PORTFOLIO_STOCKS_JSON": json.dumps(
                portfolio_js_list, ensure_ascii=False
            ),
            "SECTORS_CHART_JSON": json.dumps(
                sector_chart_list, ensure_ascii=False
            ),
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
            "SP500_ANALYSIS": format_phase1_text(
                ai_insights.get("SP500_ANALYSIS", "")
            ),
            "NASDAQ_ANALYSIS": format_phase1_text(
                ai_insights.get("NASDAQ_ANALYSIS", "")
            ),
            "DOW_ANALYSIS": format_phase1_text(
                ai_insights.get("DOW_ANALYSIS", "")
            ),
            "VIX_ANALYSIS": format_phase1_text(
                ai_insights.get("VIX_ANALYSIS", "")
            ),
            "DXY_ANALYSIS": format_phase1_text(
                ai_insights.get("DXY_ANALYSIS", "")
            ),
            "USD_ILS": usd_ils_price,
            "USD_ILS_CHANGE": usd_ils_change,
            "OIL_PRICE": oil_price,
            "OIL_CHANGE": oil_change,
            "GOLD_PRICE": gold_price,
            "GOLD_CHANGE": gold_change,
            "BTC_PRICE": btc_price,
            "BTC_CHANGE": btc_change,
            "USD_ILS_EXPLANATION": format_phase1_text(
                ai_insights.get("USD_ILS_EXPLANATION", "")
            ),
            "OIL_EXPLANATION": format_phase1_text(
                ai_insights.get("OIL_EXPLANATION", "")
            ),
            "GOLD_EXPLANATION": format_phase1_text(
                ai_insights.get("GOLD_EXPLANATION", "")
            ),
            "BTC_EXPLANATION": format_phase1_text(
                ai_insights.get("BTC_EXPLANATION", "")
            ),
            "US_MARKET_README": format_phase1_text(
                ai_insights.get("US_MARKET_NEWS", "")
            ),
            "IL_MARKET_NEWS": format_phase1_text(
                ai_insights.get("IL_MARKET_NEWS", "")
            ),
            "CATALYST_EARNINGS": format_phase1_text(
                ai_insights.get("CATALYST_EARNINGS", "")
            ),
            "CATALYST_MONETARY": format_phase1_text(
                ai_insights.get("CATALYST_MONETARY", "")
            ),
            "CATALYST_HARDWARE": format_phase1_text(
                ai_insights.get("CATALYST_HARDWARE", "")
            ),
            "COMMUNITY_SENTIMENT": format_phase1_text(
                ai_insights.get("COMMUNITY_SENTIMENT", "")
            ),
            "ANALYST_POINT_1": formatted_analyst_1,
            "ANALYST_POINT_2": formatted_analyst_2,
            "RISK_MANAGEMENT_TEXT": format_phase1_text(
                ai_insights.get("RISK_MANAGEMENT_TEXT", "")
            ),
            "ACTION_RECOMMENDATIONS_TEXT": format_phase1_text(
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
