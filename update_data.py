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
        "long_term_stocks": [
            "<strong>NVIDIA (NVDA):</strong> מובילת השוק הבלתי מעורערת בשבבי AI ותשתיות מחשוב על.",
            "<strong>Microsoft (MSFT):</strong> עוגן טכנולוגי חזק עם שליטה בענן (Azure) ושילוב כלי AI ארגוניים.",
            "<strong>Apple (AAPL):</strong> יציבות פיננסית איתנה, בסיס משתמשים נאמן וצמיחה בשירותים.",
            "<strong>Alphabet / Google (GOOG):</strong> שליטה מוחלטת בחיפוש, פרסום דיגיטלי ופיתוח מודלי Gemini מתקדמים.",
            "<strong>Amazon (AMZN):</strong> מובילת ענן גלובלית (AWS) וענקית מסחר אלקטרוני עם יעילות תפעולית עולה.",
            "<strong>Broadcom (AVGO):</strong> שחקנית מפתח בשבבי תקשורת מתקדמים ומעבדי AI ייעודיים (ASIC).",
            "<strong>AMD (AMD):</strong> מתחרה מרכזית בשוק המעבדים והכרטיסים הגרפיים עם נתח שוק צומח בשרתים.",
            "<strong>Meta Platforms (META):</strong> שליטה ברשתות החברתיות המרכזיות והשקעות חכמות בקוד פתוח ו-AI.",
            "<strong>Taiwan Semiconductor (TSMC):</strong> בית היציקה המרכזי בעולם המייצר את השבבים המתקדמים ביותר.",
            "<strong>ASML Holding (ASML):</strong> מונופול עולמי ייחודי של מכונות ליטוגרפיה אב-טיפוס לתעשיית השבבים."
        ],
        "swing_stocks": [
            "<strong>Micron Technology (MU):</strong> מחזוריות חזקה בשוק הזיכרונות (DRAM/NAND) עם ביקוש שיא משרתי AI.",
            "<strong>Super Micro Computer (SMCI):</strong> פתרונות שרתים וקירור נוזלי מתקדמים למרכזי נתונים.",
            "<strong>Palantir Technologies (PLTR):</strong> ביקושים חזקים לפלטפורמות ניתוח נתונים ובינה מלאכותית צבאית ועסקית.",
            "<strong>Coinbase Global (COIN):</strong> חשיפה תנודתית גבוהה למחזורי המסחר בשוק הקריפטו והביטקוין.",
            "<strong>Iris Energy (IREN):</strong> תשתית מחשוב ענן ומרכזי נתונים עם דגש על אנרגיה ירוקה ויעילה.",
            "<strong>Cipher Mining (CIFR):</strong> כרייה ותשתיות מחשוב בהספקים גבוהים עם ניהול פיננסי הדוק.",
            "<strong>Arm Holdings (ARM):</strong> ארכיטקטורת מעבדים חסכונית שמתרחבת לעולמות ה-PC והשרתים.",
            "<strong>Marvell Technology (MRVL):</strong> פתרונות קישוריות מהירה למרכזי נתונים ושבבי מותג מותאמים אישית.",
            "<strong>Qualcomm (QCOM):</strong> מובילה בשבבי תקשורת סלולרית וכניסה אגרסיבית למעבדי מחשבי Copilot+ PC.",
            "<strong>ProShares UltraPro QQQ (TQQQ):</strong> תעודת סל ממונפת (x3) למסחר תנודתי קצר טווח במדד הנאסד\"ק."
        ],
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
] + list(sector_tickers_map.values()) + list(portfolio_buys.keys())

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
                time.sleep(2)
        if not success:
            market_data[ticker] = {"price": 0.0, "change": 0.0, "target": 0.0, "pre_market": 0.0}
    return market_data

if __name__ == "__main__":
    try:
        print("Fetching market data...")
        base_market_data = fetch_market_data(base_market_tickers)
        date_str = now_il.strftime("%d.%m.%Y")
        time_str = now_il.strftime("%H:%M")

        ai_insights = load_ai_cache()
        if not ai_insights or not ai_insights.get("long_term_stocks"):
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

        lt_stocks = ai_insights.get("long_term_stocks", [])
        lt_html = "".join([f"<p class=\"mb-2\">• {item}</p>" for item in lt_stocks]) if lt_stocks else "אין נתונים כרגע."

        sw_stocks = ai_insights.get("swing_stocks", [])
        sw_html = "".join([f"<p class=\"mb-2\">• {item}</p>" for item in sw_stocks]) if sw_stocks else "אין נתונים כרגע."

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

            p_item = portfolio_analysis_map.get(ticker, {})
            p_rationale = p_item.get("rationale", f"ניתוח טכני ומאקרו עבור {ticker}.")
            p_news_title = p_item.get("news_title", f"עדכון שוק עבור {ticker}")
            p_news_content = p_item.get("news_content", f"סקירת נתונים פיננסיים עבור {ticker}.")
            p_news_impact = p_item.get("news_impact", "השפעה מתונה על ניהול הפוזיציה.")

            full_note_html = (
                f"<strong>רציונל וניתוח:</strong> {p_rationale}<br>"
                f"<strong>כותרת חדשותית:</strong> {p_news_title}<br>"
                f"<strong>תוכן חדשותי:</strong> {p_news_content}<br>"
                f"<strong>השפעה על הפוזיציה:</strong> {p_news_impact}"
            )

            replacements[f"{ticker}_PORT_SHARES"] = format_num(shares_count, 0)
            replacements[f"{ticker}_PORT_CURRENT"] = f"${format_num(curr_p)}"
            replacements[f"{ticker}_PORT_PRE"] = f"${format_num(pre_p)}"
            replacements[f"{ticker}_PORT_TARGET"] = f"${format_num(fetched_target)}"
            replacements[f"{ticker}_PORT_STATUS"] = f'רווח: <span style=\'color: {color}; font-weight: bold;\'>{sign}{ret:.2f}%</span>'
            replacements[f"{ticker}_PORT_NOTE"] = full_note_html

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
            subprocess.run(["git", "commit", "-m", f"Add full 10 stocks for long term and swing strategies for {day_name}"], check=True)
            subprocess.run(["git", "pull", "origin", "main", "--rebase"], check=True)
            subprocess.run(["git", "push"], check=True)
            print("Successfully pushed changes to GitHub!")

    except:
        traceback.print_exc()
        raise
