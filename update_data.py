import base64
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
        except Exception:
            pass
    return {}

def save_ai_cache(data):
    try:
        with open(AI_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving AI cache: {e}")

def load_portfolio_buys():
    if GITHUB_TOKEN and GITHUB_REPO:
        try:
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{PORTFOLIO_FILE}"
            headers = {"Authorization": f"token {GITHUB_TOKEN}"}
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                file_data = response.json()
                content = base64.b64decode(file_data["content"]).decode("utf-8")
                return json.loads(content)
        except Exception as e:
            print(f"Error loading from GitHub API: {e}")

    if os.path.exists(PORTFOLIO_FILE):
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading local portfolio.json: {e}")
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
        return f'<span style=\'color: {color}; font-weight: bold;\'>{sign}{num:.2f}%</span>'
    except (ValueError, TypeError):
        return str(val)

# מיפוי דומיינים מדויק לשליפת הלוגו האמיתי של כל חברה בצורה נקייה ויציבה
DOMAIN_MAP = {
    "NVDA": "nvidia.com",
    "MSFT": "microsoft.com",
    "AAPL": "apple.com",
    "GOOGL": "google.com",
    "GOOG": "google.com",
    "AMZN": "amazon.com",
    "AVGO": "broadcom.com",
    "AMD": "amd.com",
    "META": "meta.com",
    "TSM": "tsmc.com",
    "ASML": "asml.com",
    "MU": "micron.com",
    "SMCI": "supermicro.com",
    "PLTR": "palantir.com",
    "COIN": "coinbase.com",
    "IREN": "iren.com",
    "CIFR": "ciphermining.com",
    "ARM": "arm.com",
    "MRVL": "marvell.com",
    "QCOM": "qualcomm.com",
    "TQQQ": "proshares.com",
    "TSLA": "tesla.com",
    "NFLX": "netflix.com",
    "INTC": "intel.com",
    "BTC": "bitcoin.org",
    "ETH": "ethereum.org"
}

def get_logo_url(ticker):
    clean_ticker = ticker.split(".")[0].split("-")[0].replace("=", "").replace("^", "").upper()
    domain = DOMAIN_MAP.get(clean_ticker, f"{clean_ticker.lower()}.com")
    return f"https://www.google.com/s2/favicons?domain={domain}&sz=128"

LT_STOCKS_META = [
    {"ticker": "NVDA", "name": "NVIDIA Corporation", "desc": "מובילת השוק הבלתי מעורערת בשבבי AI ותשתיות מחשוב על.", "news": "ביקושים שיא לשבבי Blackwell. כדאי להחזיק ארוך טווח בשל מובילות שוק טכנולוגית חסרת מתחרים."},
    {"ticker": "MSFT", "name": "Microsoft Corporation", "desc": "ענן Azure, מערכות הפעלה ושילוב כלי AI ארגוניים.", "news": "צמיחה חזקה בשירותי הענן והשקעות ענק בבינה מלאכותית, השקעה בטוחה ויציבה לטווח ארוך."},
    {"ticker": "AAPL", "name": "Apple Inc.", "desc": "פיתוח מכשירי iPhone, שירותים דיגיטליים ואקוסיסטם מוביל.", "news": "השקות מוצרים חדשים ושילוב Apple Intelligence, יציבות פיננסית איתנה לשמירה על ערך."},
    {"ticker": "GOOGL", "name": "Alphabet / Google", "desc": "מנוע חיפוש גלובלי, ענן ופיתוח מודלי הבינה המלאכותית Gemini.", "news": "התקדמות משמעותית במוניטין ה-AI והכנסות פרסום חזקות, מניה ראויה ומשתלמת להחזקה."},
    {"ticker": "AMZN", "name": "Amazon.com, Inc.", "desc": "מובילת ענן גלובלית (AWS) וענקית מסחר אלקטרוני.", "news": "שיפור ניכר ברווחיות התפעולית של AWS וצמיחה בלוגיסטיקה, מנוע צמיחה מרכזי בתיק."},
    {"ticker": "AVGO", "name": "Broadcom Inc.", "desc": "שבבי תקשורת מתקדמים ומעבדי AI ייעודיים (ASIC).", "news": "חוזים חדשים עם ענקיות טכנולוגיה, מציגה נתוני צמיחה מרשימים להשקעה ארוכת טווח."},
    {"ticker": "AMD", "name": "Advanced Micro Devices", "desc": "פיתוח מעבדים וכרטיסים גרפיים לשווקי ה-PC והשרתים.", "news": "נתח שוק גדל בסדרת מעבדי EPYC וכרטיסי MI300, פוטנציאל רווח גבוה לטווח הרחוק."},
    {"ticker": "META", "name": "Meta Platforms, Inc.", "desc": "הפעלת רשתות חברתיות מובילות ופיתוח מודלי קוד פתוח.", "news": "ייעול מבני דרסטי ושיפור מהיר בהכנסות מפרסום ממוקד AI, כדאי לשמור בתיק."},
    {"ticker": "TSM", "name": "Taiwan Semiconductor", "desc": "בית היציקה הגדול בעולם המייצר את השבבים המתקדמים ביותר.", "news": "ביקוש אדיר לייצור שבבים עבור כל ענקיות הטכנולוגיה, עמוד תווך יציב והכרחי בתעשייה."},
    {"ticker": "ASML", "name": "ASML Holding N.V.", "desc": "יצרנית בלעדית של מכונות ליטוגרפיה EUV לתעשיית השבבים.", "news": "מונופול עולמי ייחודי וקריטי לייצור שבבים מתקדמים, השקעה איכותית לטווח הארוך."}
]

SW_STOCKS_META = [
    {"ticker": "MU", "name": "Micron Technology", "desc": "ייצור רכיבי זיכרון מתקדמים מסוג DRAM ו-NAND.", "news": "מחזור ביקוש חזק לזיכרונות HBM למרכזי נתונים, מתאים מאוד לסווינג קצר טווח."},
    {"ticker": "SMCI", "name": "Super Micro Computer", "desc": "תשתיות שרתים מתקדמות ופתרונות קירור נוזלי למרכזי נתונים.", "news": "תנודתיות גבוהה במחיר בעקבות דוחות וביקושים, דורש מעקב צמוד למסחר סווינג."},
    {"ticker": "PLTR", "name": "Palantir Technologies", "desc": "פלטפורמות אנליטיקה ובינה מלאכותית עסקית וביטחונית.", "news": "חוזים ממשלתיים חדשים וצמיחה מהירה במגזר המסחרי (AIP), מניה חזקה למסחר תנודתי."},
    {"ticker": "COIN", "name": "Coinbase Global, Inc.", "desc": "פלטפורמת מסחר מובילה בנכסים דיגיטליים וקריפטו.", "news": "קורלציה גבוהה לתנודות הביטקוין ושוק הקריפטו, מצוינת לסווינג מהיר בתקופות מומנטום."},
    {"ticker": "IREN", "name": "Iris Energy Limited", "desc": "תשתיות מחשוב ענן ומרכזי נתונים עם דגש על אנרגיה ירוקה.", "news": "הרחבת פעילות ה-AI והתשתיות, תנודתיות גבוהה המייצרת הזדמנויות מסחר יומי וסווינג."},
    {"ticker": "CIFR", "name": "Cipher Mining Inc.", "desc": "כרייה ותשתיות מחשוב בהספקים גבוהים.", "news": "התייעלות תפעולית והתרחבות פוטנציאלית לתשתיות AI, מתאימה למעקב סווינג סלקטיבי."},
    {"ticker": "ARM", "name": "Arm Holdings plc", "desc": "תכנון ארכיטקטורת מעבדים חסכונית באנרגיה.", "news": "חדירה מואצת לשוק המחשבים הניידים והשרתים, פוטנציאל מומנטום טוב לסווינג."},
    {"ticker": "MRVL", "name": "Marvell Technology", "desc": "פתרונות קישוריות מהירה ושבבים מותאמים אישית.", "news": "ביקושים גבוהים למתגים וקישוריות במרכזי נתונים מבוססי AI, מעקב סווינג כדאי."},
    {"ticker": "QCOM", "name": "Qualcomm Incorporated", "desc": "שבבים סלולריים ומעבדים למחשבים אישיים מתקדמים.", "news": "כניסה אגרסיבית לשוק מחשבי ה-Copilot+ PC, מציגה תנועות מחיר מעניינות לסווינג."},
    {"ticker": "TQQQ", "name": "ProShares UltraPro QQQ", "desc": "תעודת סל ממונפת פי 3 על מדד הנאסד\"ק 100.", "news": "מתאימה אך ורק למסחר יומי או סווינג קצרצר עקב שחיקת מינוף לאורך זמן."}
]

def get_default_ai_insights():
    return {
        "SP500_ANALYSIS": "מדד S&P 500 ממשיך להיסחר סביב רמות מפתח תוך בחינת נתוני המאקרו והאינפלציה.",
        "NASDAQ_ANALYSIS": "מדד הטכנולוגיה מוביל את הסנטימנט בשוק עם דגש על חברות הבינה המלאכותית.",
        "DOW_ANALYSIS": "מניות הערך במדד הדאו ג'ונס מספקות יציבות ועוגן לתיק המסחר.",
        "VIX_ANALYSIS": "מדד התנודתיות משקף רמת רגיעה מתונה בשווקים ללא לחצים חריגים.",
        "DXY_ANALYSIS": "מדד הדולר העולמי נסחר במגמה מעורבת אל מול המטבעות המרכזיים.",
        "USD_ILS_EXPLANATION": "השפעה ישירה על עלות ייבוא, מוצרים דולריים ותיק ההשקעות המקומי.",
        "OIL_EXPLANATION": "משפיע ישירות על עלויות האנרגיה, התחבורה ושיעורי האינפלציה הגלובליים.",
        "GOLD_EXPLANATION": "משמש כנכס מקלט בטוח וגידור מרכזי מפני אי-יציבות גיאו-פוליטית.",
        "BTC_EXPLANATION": "אינדיקטור מוביל לסנטימנט סיכון ונזילות בנכסים אלטרנטיביים.",
        "US_MARKET_NEWS": "נתוני המאקרו בארה\"ב ממשיכים להוות מנוע ניווט מרכזי עבור הבנק המרכזי והמשקיעים.",
        "IL_MARKET_NEWS": "השוק המקומי מגיב להתפתחויות הביטחוניות והכלכליות באזור.",
        "CATALYST_EARNINGS": "דיווחים רבעוניים של חברות הטכנולוגיה והשבבים מובילים את נפחי המסחר.",
        "CATALYST_MONETARY": "הודעות ריבית ומדיניות מוניטרית צפויות להשפיע על תשואות האג\"ח.",
        "CATALYST_HARDWARE": "השקות מוצרי חומרה חדשים, שבבי AI ועדכוני תוכנה מתקדמים.",
        "COMMUNITY_SENTIMENT": "סנטימנט חיובי זהיר סביב חברות השבבים, הענן והטכנולוגיה המובילות.",
        "ANALYST_POINT_1": "האנליסטים צופים המשך צמיחה בהשקעות בתשתיות בינה מלאכותית (AI).",
        "ANALYST_POINT_2": "דגש על ניהול סיכונים קפדני ובחינה בררנית של דוחות כספיים רבעוניים.",
        "RISK_MANAGEMENT_TEXT": "ניהול סיכונים קפדני באמצעות פיזור השקעות ופקודות הגנה לפוזיציות.",
        "ACTION_RECOMMENDATIONS_TEXT": "בחינה מדודה של פוזיציות קיימות והיערכות להזדמנויות סלקטיביות.",
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

base_market_tickers = [
    "GC=F", "CL=F", "BTC-USD", "USDILS=X", "DX-Y.NYB", "^GSPC", "^NDX", "^DJI", "^VIX",
] + list(sector_tickers_map.values()) + list(portfolio_buys.keys()) + [s["ticker"] for s in LT_STOCKS_META] + [s["ticker"] for s in SW_STOCKS_META]

def fetch_market_data(tickers):
    market_data = {}
    for ticker in tickers:
        success = False
        for attempt in range(3):
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
                    success = True
                    break
            except Exception:
                time.sleep(1)
        if not success:
            market_data[ticker] = {"price": 0.0, "change": 0.0, "target": 0.0, "pre_market": 0.0}
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

        sign = "+" if change_val > 0 else ""
        color = "#2ecc71" if change_val >= 0 else "#e74c3c"
        change_str = f"<span style='color: {color}; font-weight: bold;'>{sign}{change_val:.2f}%</span>"
        
        logo_url = get_logo_url(ticker)

        card_html = f"""
        <div class="bg-gray-800/80 border border-gray-700/60 rounded-xl p-4 mb-4 shadow-md text-right" dir="rtl">
            <div class="flex items-center gap-3 mb-3">
                <img src="{logo_url}" width="28" height="28" class="rounded-full bg-white p-0.5 object-contain" alt="{ticker}" onerror="this.style.display='none'">
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
        if not ai_insights:
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

        portfolio_analysis_map = ai_insights.get("portfolio_analysis", {})

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
            replacements[f"SECTOR_{s_key}_CLASS"] = f'style=\'color: {color};\''
            replacements[f"SECTOR_{s_key}_PERF"] = s_change

        for ticker, info in portfolio_buys.items():
            if not isinstance(info, dict):
                continue
            
            upper_ticker = ticker.upper().strip()
            buy_p = info.get("buy") or info.get("buyPrice") or 0.0

            fetched_price_data = base_market_data.get(ticker, {})
            curr_p = fetched_price_data.get("price")
            if not curr_p or curr_p == 0.0:
                curr_p = buy_p
            
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
            company_name = info.get("name", upper_ticker)

            p_item = portfolio_analysis_map.get(ticker, {})
            p_rationale = p_item.get("rationale", f"ניתוח טכני ומאקרו עבור {upper_ticker}.")
            p_news_title = p_item.get("news_title", f"עדכון שוק עבור {upper_ticker}")
            p_news_content = p_item.get("news_content", f"סקירת נתונים פיננסיים עבור {upper_ticker}.")
            p_news_impact = p_item.get("news_impact", "השפעה מתונה על ניהול הפוזיציה.")

            full_note_html = (
                f"<strong>רציונל וניתוח:</strong> {p_rationale}<br>"
                f"<strong>כותרת חדשותית:</strong> {p_news_title}<br>"
                f"<strong>תוכן חדשותي:</strong> {p_news_content}<br>"
                f"<strong>השפעה על הפוזיציה:</strong> {p_news_impact}"
            )

            logo_url = get_logo_url(upper_ticker)
            
            # תיקון כיווניות (Bidi) לסוגריים ולשמות באנגלית כדי שלא יתפכו בתוך אזור RTL
            title_with_logo = f"""<span style="display: inline-flex; align-items: center; gap: 8px;" dir="ltr"><span style="font-weight: bold;">{company_name}</span> (<span dir="rtl">טיקר:</span> <span style="font-weight: bold;">{upper_ticker}</span>)</span><img src="{logo_url}" width="24" height="24" style="border-radius: 50%; background: white; padding: 1px; object-fit: contain; margin-right: 8px;" alt="{upper_ticker}" onerror="this.style.display='none'">"""

            replacements[f"{upper_ticker}_PORT_TITLE"] = title_with_logo
            replacements[f"{upper_ticker}_PORT_SHARES"] = format_num(shares_count, 0)
            replacements[f"{upper_ticker}_PORT_CURRENT"] = f"${format_num(curr_p)}"
            replacements[f"{upper_ticker}_PORT_PRE"] = f"${format_num(pre_p)}"
            replacements[f"{upper_ticker}_PORT_TARGET"] = f"${format_num(fetched_target)}"
            replacements[f"{upper_ticker}_PORT_STATUS"] = f'רווח: <span style=\'color: {color}; font-weight: bold;\'>{sign}{ret:.2f}%</span>'
            replacements[f"{upper_ticker}_PORT_NOTE"] = full_note_html

        for key, val in replacements.items():
            content = content.replace(f"{{{{{key}}}}}", str(val))

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(content)
        print("Successfully generated index.html!")

        # Git operations
        subprocess.run(["git", "config", "--global", "user.name", "github-actions[bot]"], check=True)
        subprocess.run(["git", "config", "--global", "user.email", "github-actions[bot]@users.noreply.github.com"], check=True)
        subprocess.run(["git", "add", OUTPUT_FILE], check=True)

        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, check=True)
        if OUTPUT_FILE in status.stdout:
            subprocess.run(["git", "commit", -m, f"Fix portfolio title bidi direction and logo layout on {day_name}"], check=True)
            subprocess.run(["git", "pull", "origin", "main", "--rebase"], check=True)
            subprocess.run(["git", "push"], check=True)
            print("Successfully pushed changes to GitHub!")

    except:
        traceback.print_exc()
        raise
