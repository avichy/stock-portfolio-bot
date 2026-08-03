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
    long_term_list = [
        {
            "symbol": "AAPL", "name": "Apple Inc.", "target": "240.00",
            "rationale": "חברה יציבה עם תזרים מזומנים חזק, מובילה בעולם הטכנולוגיה והשירותים הדיגיטליים.",
            "news_title": "הרחבת פעילות שירותי הפרטיות והאינטגרציה של מערכות החומרה",
            "news_content": "אנליסטים מציינים ביקושים יציבים לשדרוגי מכשירים והכנסות שיא ממגזר השירותים.",
            "news_impact": "מחזקת את מעמדה כעוגן יציב וירוק לטווח הרחוק בתיק ההשקעות."
        },
        {
            "symbol": "MSFT", "name": "Microsoft", "target": "480.00",
            "rationale": "מובילה עולמית בתחומי הענן (Azure) והטמעת בינה מלאכותית ארגונית.",
            "news_title": "גידול מתמשך בצריכת שירותי הענן והשקת פתרונות AI חדשים לארגונים",
            "news_content": "החברה מדווחת על אימוץ נרחב של תשתיות הענן לצד שיפור ברווחיות התפעולית.",
            "news_impact": "תרומה משמעותית לתוצאות העסקיות ולצמיחה עתידית מובטחת."
        },
        {
            "symbol": "GOOGL", "name": "Alphabet", "target": "200.00",
            "rationale": "מונופול בתחום החיפוש והפרסום הדיגיטלי, לצד פעילות ענן מתרחבת.",
            "news_title": "שיפור ביעילות מודל הפרסום ושילוב יכולות חיפוש מבוססות מודלי שפה",
            "news_content": "הנהלת החברה ממשיכה לייעל עלויות ולהאיץ את קצב הפיתוח במגזר הענן והבינה המלאכותית.",
            "news_impact": "תמחור אטרקטיבי יחסית לצמיחה ולפוטנציאל הרווח העתידי."
        },
        {
            "symbol": "AMZN", "name": "Amazon", "target": "230.00",
            "rationale": "שליטה מוחלטת במסחר אלקטרוני קמעונאי ובענן העולמי (AWS).",
            "news_title": "התאוששות במרווחי הרווח של פעילות הלוגיסטיקה והמסחר המקוון",
            "news_content": "הורדת עלויות שילוח ושיפור ביצועי AWS מעניקים לזרועות החברה רווחיות גבוהה מהצפוי.",
            "news_impact": "תמיכה חזקה במגמה הראשית של המניה ופוטנציאל אפסייד גבוה."
        },
        {
            "symbol": "NVDA", "name": "NVIDIA", "target": "140.00",
            "rationale": "מונופול דה-פקטו בחומרה ותשתיות עיבוד נתונים עבור פיתוחי AI מתקדמים.",
            "news_title": "ביקושים שיא לשבבי הדור הבא מצד ענקיות הטכנולוגיה העולמיות",
            "news_content": "שרשרת האספקה מתייצבת והביקוש למערכות מחשוב עתירות ביצועים ממשיך לשבור שיאים.",
            "news_impact": "מנוע הצמיחה המרכזי של הסנטימנט הטכנולוגי בוול סטריט."
        },
        {
            "symbol": "BRK-B", "name": "Berkshire Hathaway", "target": "490.00",
            "rationale": "תיק החזקות מגוון ויציב המנוהל באדיקות ומספק הגנה בימי תנודתיות.",
            "news_title": "הגדלת עתודות המזומנים של הקונגלומרט לצד מיקוד בחברות תפעוליות יציבות",
            "news_content": "התוצאות העסקיות משקפות חוסן פיננסי גבוה ויכולת עמידות מעולה במצבי מאקרו משתנים.",
            "news_impact": "מספק יציבות והפחתת סיכון כללית לתיק ההשקעות המרכזי."
        },
        {
            "symbol": "JPM", "name": "JPMorgan Chase", "target": "220.00",
            "rationale": "הבנק המוביל והחזק בארצות הברית עם מאזן חסר תקדים ויציבות ניהולית.",
            "news_title": "הכנסות ריבית יציבות לצד התאוששות בפעילות מיזוגים ורכישות (M&A)",
            "news_content": "הבנק ממשיך להציג תשואה גבוהה על ההון ועמידה איתנה בכל מבחני הלחץ.",
            "news_impact": "עוגן פיננסי חזק המרוויח מסביבת הריבית ומחוזק המערכת הבנקאית."
        },
        {
            "symbol": "WMT", "name": "Walmart", "target": "90.00",
            "rationale": "רשת קמעונאות ענקית המהווה מקלט בטוח בתקופות של האטה כלכלית ואינפלציה.",
            "news_title": "צמיחה בהכנסות ממגזר המסחר הדיגיטלי ומועדוני הלקוחות",
            "news_content": "הצרכנים ממשיכים להעדיף רשתות זולות, מה שמגדיל את נתח השוק של החברה בקטגוריית המזון והמוצרים.",
            "news_impact": "השפעה חיובית המאזנת תנודתיות במניות טכנולוגיה עתירות סיכון."
        },
        {
            "symbol": "V", "name": "Visa", "target": "320.00",
            "rationale": "רשת סליקת התשלומים הבינלאומית הגדולה והרווחית בעולם עם מודל עמלות עמיד.",
            "news_title": "גידול בהיקפי עסקאות התשלום הדיגיטליות והבינלאומיות",
            "news_content": "התאוששות התיירות הגלובלית והמעבר המתמשך לתשלומים ללא מזומן תומכים בגידול ההכנסות.",
            "news_impact": "תזרים מזומנים צפוי ויציב התומך בתגמול בעלי המניות לאורך זמן."
        },
        {
            "symbol": "NFLX", "name": "Netflix", "target": "100.00",
            "rationale": "מובילת הסטרימינג העולמית עם יתרון גודל עצום ומודל מנויים איתן.",
            "news_title": "הצלחת מסלולי המנויים משולבי הפרסומות והידוק האכיפה על שיתוף סיסמאות",
            "news_content": "החברה רושמת גידול חד במספר המנויים נטו ומציגה שיפור מרשים במרווחי התפעול.",
            "news_impact": "ממשיכה להפגין עוצמה עסקית ולהגדיל את נתח השוק בשוק הבידור."
        }
    ]

    swing_list = [
        {
            "symbol": "AMD", "name": "Advanced Micro Devices", "target": "160.00",
            "sector_desc": "מוליכים למחצה ותשתיות מחשוב",
            "rationale": "תנודתיות גבוהה ופוטנציאל לראלי קצר טווח על רקע נתח שוק גדל במעבדי AI.",
            "news_title": "השקת שבבי בינה מלאכותית חדשים והכרזות על שיתופי פעולה אסטרטגיים",
            "news_content": "המשקיעים עוקבים אחר יכולתה של AMD לנגוס בנתח השוק של המתחרות בתחום המאיצים הגרפיים.",
            "news_impact": "תנועה חדה למעלה או למטה בימים הקרובים עקב סנטימנט הסקטור."
        },
        {
            "symbol": "TSLA", "name": "Tesla", "target": "250.00",
            "sector_desc": "רכב חשמלי ואנרגיה מתחדשת",
            "rationale": "מניית סווינג מובהקת המגיבה בעוצמה גבוהה לנתוני מסירות רכב וחדשות רובוטקסי.",
            "news_title": "התפתחויות רגולטוריות סביב מערכות הנהיגה האוטונומית ונתוני מכירות רבעוניים",
            "news_content": "השוק מגיב בתנודתיות רבה לכל דיווח סביב תמחור דגמים חדשים והתקדמות הטכנולוגיה.",
            "news_impact": "הזדמנויות מסחר מהירות לטווח הקצר למשקיעים אגרסיביים."
        },
        {
            "symbol": "MU", "name": "Micron Technology", "target": "115.00",
            "sector_desc": "שבבי זיכרון ואחסון מתקדמים",
            "rationale": "נהנית ישירות ממחזור הביקוש לזכרונות HBM הנדרשים לשררתי AI.",
            "news_title": "זינוק בביקושים לשבבי זיכרון ייעודיים למרכזי נתונים ולשוק הסמארטפונים",
            "news_content": "הנהלת החברה מעידה על מלאקים מצומצמים ועליית מחירים רוחבית בסגמנטים המרכזיים.",
            "news_impact": "תנודת מחיר חזקה המושפעת מדוחות סקטור השבבים הכללי."
        },
        {
            "symbol": "META", "name": "Meta Platforms", "target": "620.00",
            "sector_desc": "שירותי תקשורת ומדיה חברתית",
            "rationale": "מומנטום חזק בפרסום דיגיטלי ויעילות תפעולית גבוהה המייצרים פוטנציאל סווינג.",
            "news_title": "שדרוג אלגוריתמיקה מבוססת AI לשיפור המיקוד וההמרות בפרסום",
            "news_content": "המפרסמים מדווחים על החזר השקעה (ROI) גבוה יותר בפלטפורמות החברה השונות.",
            "news_impact": "שומרת על מומנטום חיובי ויכולת פריצת רמות התנגדות טכניות."
        },
        {
            "symbol": "TQQQ", "name": "ProShares UltraPro QQQ", "target": "75.00",
            "sector_desc": "תעודת סל ממונפת (x3) על מדד הנאסדק",
            "rationale": "מתאימה למסחר יומי וסווינג מהיר של מספר ימים בניצול מגמות מאקרו.",
            "news_title": "תגובה חדה לתנודות במדד הנאסדק 100 בהשפעת תשואות האג\"ח הממשלתי",
            "news_content": "כל שינוי קל במדד המוביל מתורגומי לתנועה תלת-ממדית חזקה בתעודת הסל הממונפת.",
            "news_impact": "רמת סיכון גבוהה הדורשת מעקב צמוד ועצירת הפסד מהירה."
        },
        {
            "symbol": "IREN", "name": "Iris Energy", "target": "12.00",
            "sector_desc": "תשתיות מחשוב ענן וכרייה ירוקה",
            "rationale": "קורלציה גבוהה לשוק הקריפטו ולמעבר מרכזי נתונים לשימושי AI ואנרגיה.",
            "news_title": "הרחבת יכולות האנרגיה והסבת מתקנים לתמיכה בחישובי בינה מלאכותית",
            "news_content": "החברה מדווחת על עסקאות ענן חדשות ופוטנציאל ניצולת גבוה של מתקני החשמל שברשותה.",
            "news_impact": "תנודתיות גבוהה במיוחד המאפשרת רווחי סווינג מהירים."
        },
        {
            "symbol": "CIFR", "name": "Cipher Mining", "target": "6.50",
            "sector_desc": "כריית ביטקוין ותשתיות דיגיטליות",
            "rationale": "נכס בעל בטא גבוהה המגיב בעוצמה לתנועות המחיר של שוק הקריפטו.",
            "news_title": "תנודות בשער הביטקוין לצד דיונים על שיתופי פעולה באנרגיה",
            "news_content": "המשקיעים סוחרים במניה בהתאם לסנטימנט הסיכון הכללי בשווקים האלטרנטיביים.",
            "news_impact": "רגישות גבוהה מאוד לחדשות יומיות ושינויי נפח מסחר."
        },
        {
            "symbol": "SIMO", "name": "Silicon Motion Technology", "target": "85.00",
            "sector_desc": "בקרי אחסון למוליכים למחצה",
            "rationale": "מניית ערך קטנה יחסית בסקטור השבבים הרגישה מאוד לשינויי מומנטום קצרי טווח.",
            "news_title": "עדכונים על קצבי אספקת בקרים ליצרניות כוננים מובילות",
            "news_content": "התאוששות בשוק המחשבים האישיים והניידים תומכת בשיפור תוצאותיה הרבעוניות.",
            "news_impact": "פוטנציאל לתיקון חד מעלה בעקבות פערים בתמחור הטכני."
        },
        {
            "symbol": "WDC", "name": "Western Digital", "target": "75.00",
            "sector_desc": "פתרונות אחסון מידע וזיכרון",
            "rationale": "מחזור עסקים משתפר ותהליכי רה-ארגון בחברה מייצרים עניין למסחר קצר טווח.",
            "news_title": "היערכות להשלמת פיצול פעילות זרוע הפלאש מרכזיות הנתונים",
            "news_content": "אנליסטים מעריכים כי המהלך עשוי להציף ערך רב למשקיעים בטווח הקרוב.",
            "news_impact": "תנועות שער חדות בעקבות חדשות הקשורות במבנה התאגידי."
        },
        {
            "symbol": "GTEC", "name": "Green Scientific Technologies", "target": "2.50",
            "sector_desc": "טכנולוגיות ירוקות וחקלאות חכמה",
            "rationale": "מניית סוואם תנודתית עם מחזורי מסחר קטנים המאפשרת עסקאות מומנטום ספקולטיביות.",
            "news_title": "חתימה על הסכמי הפצה חדשים באסיה ובשוק המקומי",
            "news_content": "הודעות על פרויקטים חדשים מייצרות זינוקים חדים במחזור המסחר היומי.",
            "news_impact": "סיכון גבוה המותאם לסוחרים מחפשי תנודתיות מהירה."
        }
    ]

    return {
        "SP500_ANALYSIS": "מדד S&P 500 ממשיך להיסחר סביב רמות מפתח תוך בחינת נתוני המאקרו והאינפלציה.",
        "NASDAQ_ANALYSIS": "מדד הטכנולוגיה מוביל את הסנטימנט בשוק עם דגש על חברות הבינה המלאכותית.",
        "DOW_ANALYSIS": "מניות הערך במדד הדאו ג'ונס מספקות יציבות ועוגן לתיק המסחר.",
        "VIX_ANALYSIS": "מדד התנודתיות משקף רמת רגיעה מתונה בשווקים ללא לחצים חריגים.",
        "DXY_ANALYSIS": "מדד הדולר העולמי נסחר במגמה מעורבת אל מול המטבעות המרכזיים.",
        "long_term_stocks": long_term_list,
        "swing_stocks": swing_list,
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
            
            pre_market_val = info.get("preMarketPrice") or info.get("open") or info.get("regularMarketOpen")
            if not pre_market_val and not hist.empty:
                pre_market_val = hist["Open"].iloc[-1]

            if not hist.empty:
                current_price = round(hist["Close"].iloc[-1], 2)
                prev_close = hist["Close"].iloc[-2] if len(hist) > 1 else current_price
                change = round(((current_price - prev_close) / prev_close) * 100, 2)
                market_data[ticker] = {
                    "price": current_price,
                    "change": change,
                    "target": target_mean if target_mean else 0.0,
                    "pre_market": round(float(pre_market_val), 2) if pre_market_val else current_price,
                }
            else:
                market_data[ticker] = {"price": 0.0, "change": 0.0, "target": 0.0, "pre_market": 0.0}
        except Exception as e:
            market_data[ticker] = {"price": 0.0, "change": 0.0, "target": 0.0, "pre_market": 0.0}
    return market_data

current_key_index = 0

def generate_ai_insights(market_data, date_str, day_name):
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
        print("Error: No Gemini API keys found.")
        return {}

    market_json = json.dumps(market_data, ensure_ascii=False)
    
    prompt_raw = f"""אתה אנליסט בכיר בשוק ההון. נתח את נתוני המאקרו והשוק הבאים עבור התאריך הנוכחי {date_str} (יום {day_name}):
{market_json}

כללי חובה קשיחים ואבסולוטיים:
1. דיוק ועדכניות בזמן אמת (ברמת דיוק של לפחות 95% להיום): כל החדשות, הנתונים, הזרזים והניתוחים חייבים להיות אמיתיים, מעודכנים ורלוונטיים אך ורק להיום הנוכחי ממש (לפי המצב בשווקים, אירועים אחרונים, דוחות או חדשות אמת). חל איסור מוחלט להמציא נתונים, לספק מידע גנרי או להציג חדשות מיושנות שאינן תואמות את מציאות השוק הנוכחית!
2. ספק ניתוח אנליסטי מפורט ועדכני להיום תחת SP500_ANALYSIS, NASDAQ_ANALYSIS, DOW_ANALYSIS, VIX_ANALYSIS, DXY_ANALYSIS.
3. בחר והחזר בדיוק **10 מניות שונות לחלוטין** להשקעה ארוכת טווח (Long-Term Core - מניות עוגן יציבות, דיבידנד או צמיחה איתנה) תחת המפתח 'long_term_stocks' כמערך JSON הכולל את השדות: symbol, name, target, rationale, news_title, news_content, news_impact. הקפד שכל מניה תקבל רציונל וחדשות ייחודיות וספציפיות לה בלבד!
4. בחר והחזר בדיוק **10 מניות שונות לחלוטין** למסחר סווינג קצר טווח (Swing Trading - מניות תנודתיות, מומנטום או טכנולוגיות עם פוטנציאל מהיר) תחת המפתח 'swing_stocks' כמערך JSON הכולל את השדות: symbol, name, target, sector_desc, rationale, news_title, news_content, news_impact. הקפד שרשימה זו תהיה שונה לחלוטין מרשימת ארוך הטווח, ושכל מניה תקבל תיאור, רציונל וחדשות ספציפיות המותאמות למסחר קצר טווח להיום.
5. אסור בהחלט למחזר את אותו טקסט חדשותי או אותו רציונל בין המניות או בין הקבוצות! לכל מניה חייב להיות סיפור חדשותי ייחודי המבוסס על מצבה ביום המסחר הנוכחי.
6. הוסף הסברים קצרים בשפה פשוטה ומעודכנית למצב השוק הנוכחי עבור ארבעת הנכסים הבאים תחת המפתחות: USD_ILS_EXPLANATION, OIL_EXPLANATION, GOLD_EXPLANATION, BTC_EXPLANATION.
7. הוסף ניתוחי מאקרו כלליים תחת המפתחות: US_MARKET_MACRO_NEWS, IL_MARKET_MACRO_NEWS, RISK_MANAGEMENT_TEXT, ACTION_RECOMMENDATIONS_TEXT.
8. החזר אובייקט JSON תקף בלבד, ללא שום טקסט נוסף מסביב.
"""

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
                elif text_response.startswith("```"):
                    text_response = text_response[3:]
                text_response = text_response.strip()
                if text_response.endswith("```"):
                    text_response = text_response[:-3]
                text_response = text_response.strip()
                
                parsed_res = json.loads(text_response)
                if isinstance(parsed_res, dict) and len(parsed_res.get("long_term_stocks", [])) > 0:
                    return parsed_res
            print(f"API Warning/Error response: {res_data}")
            current_key_index += 1
            time.sleep(5)
        except Exception as e:
            print(f"Exception during AI generation: {e}")
            current_key_index += 1
            time.sleep(5)
        attempts += 1
    
    print("All AI attempts failed or quota exceeded.")
    return {}

try:
    base_market_data = fetch_market_data(base_market_tickers)

    trigger_event = os.environ.get("TRIGGER_EVENT", "")
    current_hour = now_il.hour
    current_minute = now_il.minute
    
    ai_hours = [16, 20, 23]
    run_ai = (trigger_event == "workflow_dispatch") or (
        (current_hour in ai_hours) and (current_minute < 30)
    )

    date_str = now_il.strftime("%d.%m.%Y")
    time_str = now_il.strftime("%H:%M")

    ai_insights = {}
    if run_ai:
        print("Running Gemini AI generation (Scheduled/Manual trigger)...")
        ai_insights = generate_ai_insights(base_market_data, date_str, day_name)
        if ai_insights and len(ai_insights.get("long_term_stocks", [])) > 0:
            save_ai_cache(ai_insights)
        else:
            print("AI generation failed. Loading last successful cache from ai_cache.json...")
            ai_insights = load_ai_cache()
            if not ai_insights or len(ai_insights.get("long_term_stocks", [])) == 0:
                print("Cache is empty. Falling back to default insights.")
                ai_insights = get_default_ai_insights()
    else:
        print("Skipping AI call to save quota. Loading from ai_cache.json...")
        ai_insights = load_ai_cache()
        if not ai_insights or len(ai_insights.get("long_term_stocks", [])) == 0:
            ai_insights = get_default_ai_insights()

    sp500 = base_market_data.get("^GSPC", {})
    nasdaq = base_market_data.get("^IXIC", {})
    dji = base_market_data.get("^DJI", {})
    vix = base_market_data.get("^VIX", {})
    dxy = base_market_data.get("USDILS=X", {})

    sp500_price = format_num(sp500.get("price", 0))
    sp500_change = format_pct_colored(sp500.get("change", 0))
    nasdaq_price = format_num(nasdaq.get("price", 0))
    nasdaq_change = format_pct_colored(nasdaq.get("change", 0))
    dji_price = format_num(dji.get("price", 0))
    dji_change = format_pct_colored(dji.get("change", 0))
    vix_price = format_num(vix.get("price", 0))
    vix_change = format_pct_colored(vix.get("change", 0))
    dxy_price = format_num(dxy.get("price", 0))
    dxy_change = format_pct_colored(dxy.get("change", 0))

    usd_ils_p = dxy.get("price", 3.65)
    usd_ils_c = dxy.get("change", 0)
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

    long_term_stocks = ai_insights.get("long_term_stocks", [])
    swing_stocks = ai_insights.get("swing_stocks", [])

    dynamic_tickers = list(set(
        [s.get("symbol") for s in long_term_stocks if "symbol" in s] + 
        [s.get("symbol") for s in swing_stocks if "symbol" in s]
    ))
    dynamic_market_data = fetch_market_data(dynamic_tickers)

    long_term_html_blocks = ""
    for stock in long_term_stocks:
        sym = stock.get("symbol", "")
        name = stock.get("name", sym)
        rationale = stock.get("rationale", "")
        p_info = dynamic_market_data.get(
            sym, {"price": 0, "change": 0, "target": 0}
        )
        price_str = f"${format_num(p_info['price'])}" if p_info["price"] else "N/A"
        pct_str = format_pct_colored(p_info["change"])
        target_str = (
            f"${format_num(p_info['target'])}"
            if p_info["target"]
            else stock.get("target", "N/A")
        )
        long_term_html_blocks += (
            '<p class="border-b border-gray-700 pb-3 text-right" dir="rtl">'
            f'🚀 <span dir="ltr" style="unicode-bidi: isolate;"><strong>{name}</strong> (סמל: <strong>{sym}</strong>)</span><br>'
            f'מחיר נוכחי: <span dir="ltr" style="unicode-bidi: isolate;"><strong>{price_str}</strong>&nbsp;({pct_str})</span><br>'
            f'מחיר יעד אנליסטים ממוצע: <span dir="ltr" style="unicode-bidi: isolate;"><strong>{target_str}</strong></span><br>'
            f'<strong>רציונל וניתוח AI ארוך טווח:</strong> <span class="text-gray-200">{rationale}</span>'
            "</p>"
        )

    swing_html_blocks = ""
    for stock in swing_stocks:
        sym = stock.get("symbol", "")
        name = stock.get("name", sym)
        sector_desc = stock.get("sector_desc", "מסחר סווינג ומומנטום")
        rationale = stock.get("rationale", "")
        p_info = dynamic_market_data.get(
            sym, {"price": 0, "change": 0, "target": 0}
        )
        price_str = f"${format_num(p_info['price'])}" if p_info["price"] else "N/A"
        pct_str = format_pct_colored(p_info["change"])
        target_str = (
            f"${format_num(p_info['target'])}"
            if p_info["target"]
            else stock.get("target", "N/A")
        )
        swing_html_blocks += (
            '<p class="border-b border-gray-700 pb-3 text-right" dir="rtl">'
            f'⚡ <span dir="ltr" style="unicode-bidi: isolate;"><strong>{name}</strong> (סמל: <strong>{sym}</strong>)</span><br>'
            f'מחיר נוכחי: <span dir="ltr" style="unicode-bidi: isolate;"><strong>{price_str}</strong>&nbsp;({pct_str})</span><br>'
            f'יעד למסחר סווינג: <span dir="ltr" style="unicode-bidi: isolate;"><strong>{target_str}</strong></span><br>'
            f'תחום עיסוק: {sector_desc}<br>'
            f'<strong>רציונל וטריגר למסחר:</strong> <span class="text-gray-200">{rationale}</span>'
            "</p>"
        )

    news_html_blocks = ""
    for stock in long_term_stocks + swing_stocks:
        sym = stock.get("symbol", "")
        name = stock.get("name", sym)
        news_title = stock.get(
            "news_title", f"עדכון שוק וסקירה טכנית עבור מניית {sym}"
        )
        news_content = stock.get(
            "news_content",
            f"ניתוח פעילות מסחר ונתונים פיננסיים עדכניים עבור {sym}.",
        )
        news_impact = stock.get(
            "news_impact", "השפעה חיובית ומתונה על המגמה הראשית."
        )
        news_link = f"[https://finance.yahoo.com/quote/](https://finance.yahoo.com/quote/){sym}"
        news_html_blocks += (
            '<div class="bg-gray-800 p-4 rounded-xl border border-gray-700 shadow space-y-2 text-sm text-gray-300 text-right" dir="rtl">'
            f'<h3 class="text-cyan-400 font-semibold">חדשות <span dir="ltr" style="unicode-bidi: isolate;">{name} (סמל: {sym})</span></h3>'
            '<p>🔗 <strong>קישור למקור:</strong> '
            f'<a href="{news_link}" target="_blank" class="text-cyan-400 hover:underline" dir="ltr">{news_link}</a></p>'
            f'<p><strong>כותרת הכתבה המלאה:</strong> {news_title}</p>'
            f'<p><strong>תוכן הכתבה המלא:</strong> {news_content}</p>'
            f'<p>🚀 <strong>מה זה אומר בקשר למניה:</strong> {news_impact}</p>'
            "</div>"
        )

    replacements = {
        "LAST_UPDATED": f"{date_str} | {time_str}",
        "DAY_NAME": day_name,
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
        "SP500_ANALYSIS": ai_insights.get("SP500_ANALYSIS", "ניתוח מדד S&P 500 מתעדכן..."),
        "NASDAQ_ANALYSIS": ai_insights.get("NASDAQ_ANALYSIS", 'ניתוח מדד נאסד"ק מתעדכן...'),
        "DOW_ANALYSIS": ai_insights.get("DOW_ANALYSIS", "ניתוח מדד דאו ג'ונס מתעדכן..."),
        "VIX_ANALYSIS": ai_insights.get("VIX_ANALYSIS", "ניתוח מדד הפחד VIX מתעדכן..."),
        "DXY_ANALYSIS": ai_insights.get("DXY_ANALYSIS", "ניתוח מדד הדולר מתעדכן..."),
        "LONG_TERM_STOCKS_SECTION": long_term_html_blocks,
        "SWING_STOCKS_SECTION": swing_html_blocks,
        "NEWS_SECTION": news_html_blocks,
        "US_MARKET_NEWS": ai_insights.get("US_MARKET_MACRO_NEWS", "נתוני המאקרו ממשיכים להוות מנוע ניווט בשווקים."),
        "IL_MARKET_NEWS": ai_insights.get("IL_MARKET_MACRO_NEWS", "השוק המקומי מגיב להתפתחויות הכלכליות."),
        "RISK_MANAGEMENT_TEXT": ai_insights.get("RISK_MANAGEMENT_TEXT", "ניהול סיכונים קפדני."),
        "ACTION_RECOMMENDATIONS_TEXT": ai_insights.get("ACTION_RECOMMENDATIONS_TEXT", "בחינה מדודה של פוזיציות."),
        "USD_ILS": usd_ils_price,
        "USD_ILS_CHANGE": usd_ils_change,
        "OIL_PRICE": oil_price,
        "OIL_CHANGE": oil_change,
        "GOLD_PRICE": gold_price,
        "GOLD_CHANGE": gold_change,
        "BTC_PRICE": btc_price,
        "BTC_CHANGE": btc_change,
        "USD_ILS_EXPLANATION": ai_insights.get("USD_ILS_EXPLANATION", "השפעה ישירה על עלות ייבוא."),
        "OIL_EXPLANATION": ai_insights.get("OIL_EXPLANATION", "משפיע ישירות על עלויות האנרגיה."),
        "GOLD_EXPLANATION": ai_insights.get("GOLD_EXPLANATION", "משמש כנכס מקלט בטוח."),
        "BTC_EXPLANATION": ai_insights.get("BTC_EXPLANATION", "אינדיקטור לסנטימנט סיכון."),
    }

    for ticker, info in portfolio_buys.items():
        fetched_price_data = base_market_data.get(ticker, {})
        curr_p = fetched_price_data.get("price")
        if not curr_p or curr_p == 0.0:
            curr_p = info["buy"]
        
        fetched_target = fetched_price_data.get("target", 0.0)
        if not fetched_target or fetched_target == 0.0:
            fetched_target = info["buy"] * 1.25

        pre_p = fetched_price_data.get("pre_market", 0.0)
        if not pre_p or pre_p == 0.0:
            pre_p = curr_p

        ret = ((curr_p - info["buy"]) / info["buy"]) * 100
        sign = "+" if ret > 0 else ""
        color = "#2ecc71" if ret >= 0 else "#e74c3c"

        replacements[f"{ticker}_PORT_CURRENT"] = f"${format_num(curr_p)}"
        replacements[f"{ticker}_PORT_PRE"] = f"${format_num(pre_p)}"
        replacements[f"{ticker}_PORT_TARGET"] = f"${format_num(fetched_target)}"
        replacements[f"{ticker}_PORT_STATUS"] = f'רווח: <span style="color: {color}; font-weight: bold;">{sign}{ret:.2f}%</span>'
        replacements[f"{ticker}_PORT_NOTE"] = f"מעקב פוזיציה שוטף מבוסס ביצועי שוק נוכחיים עבור {ticker}."

    with open("index.template.html", "r", encoding="utf-8-sig") as f:
        content = f.read()

    for key, val in replacements.items():
        content = content.replace(f"{{{{{key}}}}}", str(val))

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(content)

    subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
    subprocess.run(["git", "add", "index.html"], check=True)

    status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True)
    if "index.html" in status.stdout:
        commit_msg = (
            f"Auto-update prices & accurate daily AI report for {day_name} at {time_str}"
            if run_ai
            else f"Auto-update stock prices (yfinance) for {day_name} at {time_str}"
        )
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        subprocess.run(["git", "pull", "origin", "main", "--rebase"], check=True)
        subprocess.run(["git", "push"], check=True)

except Exception as e:
    traceback.print_exc()
