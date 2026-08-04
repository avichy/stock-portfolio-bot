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

def get_default_ai_insights():
    long_term_list = [
        {
            "symbol": "AAPL", "name": "Apple Inc.", "target": "240.00",
            "rationale": "מעבר ממוקד לשירותי מנויים דיגיטליים מתקדמים לצד יציבות תזרימית חסרת תקדים בשוק הסמארטפונים.",
            "news_title": "השקת עדכוני אבטחה ופלטפורמת בינה עסקית חדשה למפתחי צד שלישי",
            "news_content": "החברה מרחיבה את מעטפת השירותים המקוונים שלה כדי לפצות על האטה במכירות חומרה נקודתיות.",
            "news_impact": "מבסס את רווחיות החברה ומחזק את אמון המשקיעים לטווח הארוך."
        },
        {
            "symbol": "MSFT", "name": "Microsoft", "target": "480.00",
            "rationale": "הטמעה עמוקה של סוכני AI אוטונומיים במערכות הענן של ארגונים גלובליים מובילים.",
            "news_title": "גידול בהכנסות שירותי הענן העסקיים וחתימה על עסקאות ענק ממשלתיות",
            "news_content": "הביקוש לתשתיות מחשוב ענן ייעודיות לחישובי ענק ממשיך לדחוף כלפי מעלה את שולי הרווח.",
            "news_impact": "מנוע צמיחה יציב המייצר ערך אמיתי לבעלי המניות."
        },
        {
            "symbol": "GOOGL", "name": "Alphabet", "target": "200.00",
            "rationale": "דומיננטיות מוחלטת בשזירת מודלי שפה מתקדמים במנועי חיפוש ובפלטפורמות ענן ארגוניות.",
            "news_title": "אופטימיזציה של מבנה ההוצאות התפעוליות וגידול חד בהכנסות הפרסום הדיגיטלי",
            "news_content": "הנהלת החברה מציגה שיפור ניכר ביעילות המרכזים והאלגוריתמים המשרתים מיליוני משתמשים.",
            "news_impact": "תמחור אטרקטיבי המגלם פוטנציאל אפסייד גבוה ביחס לסיכון."
        },
        {
            "symbol": "AMZN", "name": "Amazon", "target": "230.00",
            "rationale": "סינרגיה מושלמת בין פעילות המסחר המקוון הלוגיסטית לבין זרוע שירותי הענן AWS.",
            "news_title": "התייעלות במערך השילוח הבין-יבשתי ועלייה בשיעורי הרווחיות של AWS",
            "news_content": "שימוש מוגבר באוטומציה מתקדמת במרכזי הלוגיסטיקה מוזיל משמעותית את עלויות התפעול.",
            "news_impact": "מחזק את המגמה הראשית ומעניק רוח גבית לתוצאות הרבעוניות."
        },
        {
            "symbol": "NVDA", "name": "NVIDIA", "target": "140.00",
            "rationale": "הובלה בלתי מעורערת באספקת מעבדי קצה וארכיטקטורות חומרה למרכזי נתונים עתירי AI.",
            "news_title": "חשיפת השבבים החדשים והרחבת חוזי האספקה ארוכי הטווח עם ענקיות הענן",
            "news_content": "הביקוש העולמי למערכות עיבוד נתונים משולבות ממשיך לעלות על תחזיות האנליסטים המוקדמות.",
            "news_impact": "המשך ביסוס המונופול הטכנולוגי בשוק המעבדים הגלובלי."
        },
        {
            "symbol": "BRK-B", "name": "Berkshire Hathaway", "target": "490.00",
            "rationale": "פורטפוליו עסקי מבוזר המגן על המשקיעים מפני זעזועי מאקרו ותנודתיות בשווקים.",
            "news_title": "מימוש נבון של אחזקות נזילות והגדלת עתודות המזומנים של הקונגלומרט",
            "news_content": "החברות הבנות מציגות יציבות פיננסית גבוהה גם בסביבת ריבית מאתגרת.",
            "news_impact": "מספק עוגן בטוח המאזן את התיק הכולל."
        },
        {
            "symbol": "JPM", "name": "JPMorgan Chase", "target": "220.00",
            "rationale": "מאזן חזק וניהול סיכונים קפדני המציבים את הבנק בראש המערכת הפיננסית העולמית.",
            "news_title": "התאוששות בפעילות הנפקות החוב והמיזוגים לצד גידול בהכנסות ריבית נטו",
            "news_content": "הבנק עומד בכל מבחני הלחץ הרגולטוריים בהצלחה יתרה ומחלק תשואה יציבה.",
            "news_impact": "חיזוק הסנטימנט החיובי בסקטור הפיננסי."
        },
        {
            "symbol": "WMT", "name": "Walmart", "target": "90.00",
            "rationale": "רשת קמעונאות גלובלית המושכת אליה צרכנים המחפשים ערך מוסף בתקופות אינפלציוניות.",
            "news_title": "צמיחה מואצת בפעילות המסחר הדיגיטלי ובשירותי המנויים של הרשת",
            "news_content": "שיפור שרשרת האספקה הקמעונאית מאפשר שמירה על מרווחי רווח יציבים.",
            "news_impact": "משמש כמגן יעיל מפני תנודות חדות בשווקים."
        },
        {
            "symbol": "V", "name": "Visa", "target": "320.00",
            "rationale": "מודל עסקי עמיד המבוסס על עמלות סליקה גלובליות במעבר לתשלומים אלקטרוניים.",
            "news_title": "עלייה בהיקפי עסקאות המסחר הבינלאומיות והתשלומים הניידים",
            "news_content": "התיירות העולמית המתאוששת תומכת בגידול עקבי בנפחי הסליקה היומיים.",
            "news_impact": "תזרים מזומנים צפוי ויציב התומך בתגמול מתמשך לבעלי המניות."
        },
        {
            "symbol": "NFLX", "name": "Netflix", "target": "100.00",
            "rationale": "שליטה בשוק הסטרימינג העולמי הודות לאסטרטגיית תוכן מדויקת ומוניטין חזק.",
            "news_title": "הצלחת מסלולי הצפייה המוזלים בשילוב פרסומות ואכיפת מדיניות המנויים",
            "news_content": "החברה רושמת תוספת מנויים נקייה גבוהה מהציפיות ושיפור במרווח התפעולי.",
            "news_impact": "חיזוק מעמדה התחרותי בתעשיית הבידור הדיגיטלי."
        }
    ]

    swing_list = [
        {
            "symbol": "AMD", "name": "Advanced Micro Devices", "target": "160.00",
            "sector_desc": "מוליכים למחצה ותשתיות מחשוב",
            "rationale": "פוטנציאל למומנטום קצר טווח בעקבות נתח שוק הולך וגדל במאיצי AI מתקדמים.",
            "news_title": "חתימה על עסקאות אספקה חדשות למרכזי נתונים מתקדמים באסיה ובארה\"ב",
            "news_content": "המשקיעים בוחנים את יכולתה של החברה לתרגם את השקת השבבים להכנסות מיידיות.",
            "news_impact": "תנודתיות גבוהה המאפשרת הזדמנויות מסחר מהירות."
        },
        {
            "symbol": "TSLA", "name": "Tesla", "target": "250.00",
            "sector_desc": "רכב חשמלי ואנרגיה מתחדשת",
            "rationale": "נכס תנודתי המגיב בעוצמה גבוהה לדיווחים רגולטוריים ונתוני מכירות רבעוניים.",
            "news_title": "עדכונים סביב פיתוח מערכות נהיגה אוטונומית ופתרונות אחסון אנרגיה",
            "news_content": "השוק מגיב באגרסיביות לכל ידיעה חדשה הנוגעת למדיניות המחירים ותחרות הרכבים.",
            "news_impact": "תנועות שער חדות המצריכות ניהול סיכונים הדוק למסחר קצר טווח."
        },
        {
            "symbol": "MU", "name": "Micron Technology", "target": "115.00",
            "sector_desc": "שבבי זיכרון ואחסון מתקדמים",
            "rationale": "חשיפה ישירה למחזור הביקושים הגבוה לשבבי HBM המוטמעים בשררתי AI.",
            "news_title": "דיווחים על הידוק מלאים ועליית מחירים בקווי הייצור של רכיבי הזיכרון",
            "news_content": "הביקוש המוגבר מצד יצרניות החומרה תומך בשיפור תוצאותיה העסקיות.",
            "news_impact": "תגובה מהירה לרוח הגביה של סקטור השבבים בוול סטריט."
        },
        {
            "symbol": "META", "name": "Meta Platforms", "target": "620.00",
            "sector_desc": "שירותי תקשורת ומדיה חברתית",
            "rationale": "מומנטום חיובי המונע משיפור אלגוריתמיקה מבוססת AI למיקוד פרסומות מדויק.",
            "news_title": "שדרוג כלים למפרסמים המציגים החזר השקעה (ROI) גבוה משמעותית",
            "news_content": "מותגים וגופים מסחריים מגדילים את תקציבי הפרסום הפונים לפלטפורמות החברה.",
            "news_impact": "תמיכה בפריצת רמות התנגדות טכניות במסחר הסווינג."
        },
        {
            "symbol": "TQQQ", "name": "ProShares UltraPro QQQ", "target": "75.00",
            "sector_desc": "תעודת סל ממונפת (x3) על מדד הנאסדק",
            "rationale": "כלי מסחר אגרסיבי המיועד לניצול מגמות מאקרו יומיות של מדד הטכנולוגיה.",
            "news_title": "תגובה חדה לתנודות בתשואות אג\"ח ממשלת ארצות הברית והסנטימנט הטכנולוגי",
            "news_content": "כל תנועה קטנה במדד המוביל מתורגמת לתנודתיות משולשת בנכס הבסיס.",
            "news_impact": "רמת סיכון גבוהה המחייבת יציאה מהירה מפוזיציות הפוכות."
        },
        {
            "symbol": "IREN", "name": "Iris Energy", "target": "12.00",
            "sector_desc": "תשתיות מחשוב ענן וכרייה ירוקה",
            "rationale": "מתאפיינת בקורלציה גבוהה לשוק הקריפטו ולמעבר מתקני אנרגיה לשימושי AI.",
            "news_title": "הסבת חוזי חשמל ומתקנים קיימים לתמיכה בחישובי ענן ובינה מלאכותית",
            "news_content": "הנהלת החברה מדווחת על עסקאות גיבוי ענן המייצרות מקור הכנסה אלטרנטיבי.",
            "news_impact": "תנודות שער חדות המספקות פוטנציאל רווח סווינג גבוה."
        },
        {
            "symbol": "CIFR", "name": "Cipher Mining", "target": "6.50",
            "sector_desc": "כריית ביטקוין ותשתיות דיגיטליות",
            "rationale": "מניה בעלת בטא גבוהה המושפעת ישירות מתנודות המחיר של שוק המטבעות הדיגיטליים.",
            "news_title": "תנועה במחירי הביטקוין ודיונים סביב שיתופי פעולה תשתיתיים",
            "news_content": "סוחרים אקטיביים מנצלים את מחזורי המסחר הערים לביצוע עסקאות מהירות.",
            "news_impact": "רגישות מוגברת לחדשות יומיות המכתיבות את כיוון המסחר."
        },
        {
            "symbol": "SIMO", "name": "Silicon Motion Technology", "target": "85.00",
            "sector_desc": "בקרי אחסון למוליכים למחצה",
            "rationale": "שחקנית נישה בסקטור השבבים הרגישה במיוחד לפערים בתמחור הטכני קצר הטווח.",
            "news_title": "עדכונים על קצבי אספקת בקרים ליצרניות כוננים איתנות",
            "news_content": "התאוששות הדרגתית בשוק המחשבים האישיים תומכת בפעילותה השוטפת.",
            "news_impact": "אפשרות לתיקון חד מעלה בעקבות זיהוי תבניות טכניות."
        },
        {
            "symbol": "WDC", "name": "Western Digital", "target": "75.00",
            "sector_desc": "פתרונות אחסון מידע וזיכרון",
            "rationale": "תהליכי רה-ארגון פנימיים ומחזור עסקים משתפר מייצרים עניין למסחר סווינג.",
            "news_title": "התקדמות לקראת השלמת המהלך המבני והפיצול התאגידי המתוכנן",
            "news_content": "אנליסטים בשוק מעריכים כי המהלך צפוי להציף ערך משמעותי למשקיעים.",
            "news_impact": "תנועות מחיר מושפעות מדיווחים תאגידיים נקודתיים."
        },
        {
            "symbol": "GTEC", "name": "Green Scientific Technologies", "target": "2.50",
            "sector_desc": "טכנולוגיות ירוקות וחקלאות חכמה",
            "rationale": "מניית מומנטום תנודתית המאפשרת עסקאות ספקולטיביות מהירות במחזורים נמוכים.",
            "news_title": "חתימה על הסכמי הפצה אזוריים חדשים בשווקים מתעוררים",
            "news_content": "פרסום הודעות על פרויקטים תפעוליים מביא לקפיצות פתאומיות במחזור.",
            "news_impact": "סיכון גבוה המותאם לסוחרים מנוסים בלבד."
        }
    ]

    default_portfolio_analysis = {
        sym: {
            "rationale": f"ניתוח עומק טכני ומאקרו מותאם אישית למניית {sym} בהתאם לתנאי השוק הנוכחיים.",
            "news_title": f"עדכון שוק וסקירה טכנית ייחודית עבור מניית {sym}",
            "news_content": f"ניתוח מחזורי המסחר וההתפתחויות העסקיות האחרונות המשפיעות ישירות על {sym}.",
            "news_impact": "השפעה ישירה וממוקדת על אופן ניהול הפוזיציה האישית."
        } for sym in portfolio_buys.keys()
    }

    return {
        "SP500_ANALYSIS": "מדד S&P 500 ממשיך להיסחר סביב רמות מפתח תוך בחינת נתוני המאקרו והאינפלציה.",
        "NASDAQ_ANALYSIS": "מדד הטכנולוגיה מוביל את הסנטימנט בשוק עם דגש על חברות הבינה המלאכותית.",
        "DOW_ANALYSIS": "מניות הערך במדד הדאו ג'ונס מספקות יציבות ועוגן לתיק המסחר.",
        "VIX_ANALYSIS": "מדד התנודתיות משקף רמת רגיעה מתונה בשווקים ללא לחצים חריגים.",
        "DXY_ANALYSIS": "מדד הדולר העולמי נסחר במגמה מעורבת אל מול המטבעות המרכזיים.",
        "long_term_stocks": long_term_list,
        "swing_stocks": swing_list,
        "portfolio_analysis": default_portfolio_analysis,
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

base_market_tickers = [
    "GC=F",
    "CL=F",
    "BTC-USD",
    "USDILS=X",
    "DX-Y.NYB",
    "^GSPC",
    "^NDX",
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

def generate_ai_insights(market_data, date_str, day_name, portfolio_tickers):
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
    portfolio_json = json.dumps(portfolio_tickers, ensure_ascii=False)
    
    prompt_raw = f"""אתה אנליסט בכיר בשוק ההון. נתח את נתוני המאקרו והשוק הבאים עבור התאריך הנוכחי {date_str} (יום {day_name}):
{market_json}

רשימת מניות התיק האישי של המשתמש שחייבות לקבל ניתוח עומק ייחודי ומלא:
{portfolio_json}

כללי חובה קשיחים ואבסולוטיים למניעת כל תוכן גנרי:
1. איסור מוחלט על טקסט גנרי או מחוזר: אסור להשתמש בניסוחים קבועים מראש, משפטים כלליים או תבניות חוזרות. כל מניה בכל קטגוריה (ארוך טווח, סווינג, ותיק אישי) חייבת לקבל ניתוח עומק, רציונל, כותרת חדשותית, תוכן חדשותי והשפעה שונים לחלוטין, מקוריים, מעודכנים וספציפיים אך ורק להיום.
2. ספק ניתוח אנליסטי מפורט ועדכני להיום תחת SP500_ANALYSIS, NASDAQ_ANALYSIS, DOW_ANALYSIS, VIX_ANALYSIS, DXY_ANALYSIS.
3. בחר והחזר בדיוק **10 מניות שונות לחלוטין** להשקעה ארוכת טווח תחת המפתח 'long_term_stocks' כמערך JSON שבו לכל מניה יש שדות ייחודיים: symbol, name, target, rationale, news_title, news_content, news_impact.
4. בחר והחזר בדיוק **10 מניות שונות לחלוטין** למסחר סווינג קצר טווח תחת המפתח 'swing_stocks' כמערך JSON שבו לכל מניה יש שדות ייחודיים: symbol, name, target, sector_desc, rationale, news_title, news_content, news_impact.
5. עבור **כל** אחד מהטיקרים שברשימת התיק האישי ({portfolio_json}), ספק אובייקט תחת המפתח 'portfolio_analysis' שבו המפתח הוא הטיקר, והערך הוא אובייקט הכולל שדות טקסט מקוריים לחלוטין: rationale, news_title, news_content, news_impact.
6. הוסף הסברים קצרים למצב השוק הנוכחי תחת המפתחות: USD_ILS_EXPLANATION, OIL_EXPLANATION, GOLD_EXPLANATION, BTC_EXPLANATION.
7. הוסף ניתוחי מאקרו וניהול סיכונים תחת המפתחות: US_MARKET_MACRO_NEWS, IL_MARKET_MACRO_NEWS, RISK_MANAGEMENT_TEXT, ACTION_RECOMMENDATIONS_TEXT.
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
    portfolio_tickers_list = list(portfolio_buys.keys())

    if run_ai:
        print("Running Gemini AI generation (Scheduled/Manual trigger)...")
        ai_insights = generate_ai_insights(base_market_data, date_str, day_name, portfolio_tickers_list)
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

    long_term_stocks = ai_insights.get("long_term_stocks", [])
    swing_stocks = ai_insights.get("swing_stocks", [])
    portfolio_analysis_map = ai_insights.get("portfolio_analysis", {})

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
            f'מחיר נוכחי: <span dir="ltr" style="unicode-bidi: isolate;"><strong>{price_str}</strong></span>&nbsp;<span dir="ltr" style="unicode-bidi: isolate;">({pct_str})</span><br>'
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
            f'מחיר נוכחי: <span dir="ltr" style="unicode-bidi: isolate;"><strong>{price_str}</strong></span>&nbsp;<span dir="ltr" style="unicode-bidi: isolate;">({pct_str})</span><br>'
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

    nvda_stock = next((s for s in long_term_stocks + swing_stocks if s.get("symbol") == "NVDA"), {})
    amd_stock = next((s for s in long_term_stocks + swing_stocks if s.get("symbol") == "AMD"), {})

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
        
        "SECTOR_CHIPS_DESC": "מוליכים למחצה ותשתיות עיבוד נתונים מתקדמות",
        "SECTOR_CLOUD_DESC": "שירותי ענן, תשתיות ארגוניות ובינה מלאכותית",
        "SECTOR_CRYPTO_DESC": "נכסים דיגיטליים, בלוקצ'יין וכרייה ירוקה",

        "CATALYST_EARNINGS": "דיווחים שוטפים על תוצאות רבעוניות והערכות אנליסטים",
        "CATALYST_MONETARY": "החלטות ריבית, נתוני אינפלציה וצעדי בנקים מרכזיים",
        "CATALYST_HARDWARE": "השקות מוצרי חומרה חדשים ועדכוני תוכנה לתשתיות AI",

        "COMMUNITY_SENTIMENT": "סנטימנט חיובי זהיר בקרב משקיעים פרטיים ומוסדיים",
        "ANALYST_POINT_1": "המשך דגש על חברות בעלות תזרים מזומנים חזק ויציב",
        "ANALYST_POINT_2": "מעקב צמוד אחר רמות התנגדות טכניות במדדים המוצגים",

        "NVDA_NEWS_LINK": "[https://finance.yahoo.com/quote/NVDA](https://finance.yahoo.com/quote/NVDA)",
        "NVDA_NEWS_TITLE": nvda_stock.get("news_title", "ביקושים גבוהים לשבבי הדור הבא מצד ענקיות הענן"),
        "NVDA_NEWS_CONTENT": nvda_stock.get("news_content", "החברה ממשיכה לדווח על צבר הזמנות חזק המעיד על המשך שליטה בשוק מעבדי ה-AI."),
        "NVDA_NEWS_IMPACT": nvda_stock.get("news_impact", "תמיכה חזקה במומנטום החיובי של המניה בטווח הקצר והארוך."),

        "AMD_NEWS_LINK": "[https://finance.yahoo.com/quote/AMD](https://finance.yahoo.com/quote/AMD)",
        "AMD_NEWS_TITLE": amd_stock.get("news_title", "הרחבת נתח השוק במעבדי בינה מלאכותית למרכזי נתונים"),
        "AMD_NEWS_CONTENT": amd_stock.get("news_content", "הכרזות על שיתופי פעולה אסטרטגיים עם לקוחות מובילים במגזר הטכנולוגי."),
        "AMD_NEWS_IMPACT": amd_stock.get("news_impact", "פוטנציאל לראלי מחירים ותנודתיות גבוהה במסחר סווינג."),

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

        p_item = portfolio_analysis_map.get(ticker, {})
        p_rationale = p_item.get("rationale", f"ניתוח טכני ומאקרו מתקדם עבור מניית {ticker}.")
        p_news_title = p_item.get("news_title", f"עדכון שוק ומגמות מסחר עבור {ticker}")
        p_news_content = p_item.get("news_content", f"סקירת פעילות המסחר והנתונים הפיננסיים העדכניים המאפיינים את {ticker}.")
        p_news_impact = p_item.get("news_impact", "השפעה ישירה וממוקדת על ניהול הפוזיציה.")

        full_note_html = (
            f"<strong>רציונל וניתוח:</strong> {p_rationale}<br>"
            f"<strong>כותרת חדשותית:</strong> {p_news_title}<br>"
            f"<strong>תוכן חדשותי:</strong> {p_news_content}<br>"
            f"<strong>השפעה על הפוזיציה:</strong> {p_news_impact}"
        )

        replacements[f"{ticker}_PORT_CURRENT"] = f"${format_num(curr_p)}"
        replacements[f"{ticker}_PORT_PRE"] = f"${format_num(pre_p)}"
        replacements[f"{ticker}_PORT_TARGET"] = f"${format_num(fetched_target)}"
        replacements[f"{ticker}_PORT_STATUS"] = f'רווח: <span style="color: {color}; font-weight: bold;">{sign}{ret:.2f}%</span>'
        replacements[f"{ticker}_PORT_NOTE"] = full_note_html

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
            f"Auto-update prices & dynamic unique AI analysis for {day_name} at {time_str}"
            if run_ai
            else f"Auto-update stock prices (yfinance) for {day_name} at {time_str}"
        )
        subprocess.run(["git", "commit", "-m", commit_msg], check=True)
        subprocess.run(["git", "pull", "origin", "main", "--rebase"], check=True)
        subprocess.run(["git", "push"], check=True)

except Exception as e:
    traceback.print_exc()
