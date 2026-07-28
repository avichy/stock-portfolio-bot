from datetime import datetime
import json
import os
import subprocess
import pytz
import requests
import yfinance as yf


def format_num(val, decimals=2):
    """מפרמט מספר עם פסיקים לאלפים ומספר ספרות אחרי הנקודה"""
    try:
        num = float(val)
        if decimals == 0:
            return f"{num:,.0f}"
        return f"{num:,.{decimals}f}"
    except (ValueError, TypeError):
        return str(val)


# הגדרת אזור זמן של ישראל
israel_tz = pytz.timezone("Asia/Jerusalem")
now_il = datetime.now(israel_tz)

current_date = now_il.date()
current_hour = now_il.hour
current_minute = now_il.minute
current_total_minutes = current_hour * 60 + current_minute

trigger_event = (
    os.environ.get("GITHUB_EVENT_NAME")
    or os.environ.get("TRIGGER_EVENT")
    or "schedule"
)

days_map = {
    0: "שני",
    1: "שלישי",
    2: "רביעי",
    3: "חמישי",
    4: "שישי",
    5: "שבת",
    6: "ראשון",
}
day_name = days_map[now_il.weekday()]

print(
    f"Current Israel Time: {now_il.strftime('%Y-%m-%d %H:%M')} - Day:"
    f" {day_name} - Event: {trigger_event}"
)

# רשימת כל הסימולים במערכת
all_strategy_tickers = [
    "NVDA",
    "AMD",
    "MU",
    "GOOG",
    "AMZN",
    "META",
    "MA",
    "WMT",
    "TTWO",
    "WDC",
    "TQQQ",
    "INTC",
    "IREN",
    "CIFR",
    "IBIT",
    "SIMO",
    "SNDK",
    "NFLX",
    "GTEC",
]

tickers_to_fetch = all_strategy_tickers + [
    "GC=F",
    "CL=F",
    "BTC-USD",
    "USDILS=X",
    "^GSPC",
    "^IXIC",
    "^DJI",
    "^VIX",
]


def fetch_all_data():
    """מושך נתוני מחיר ושינוי יומי מ-yfinance"""
    market_data = {}
    for ticker in tickers_to_fetch:
        try:
            stock = yf.Ticker(ticker)
            hist = stock.history(period="2d")
            if not hist.empty:
                current_price = round(hist["Close"].iloc[-1], 2)
                prev_close = (
                    hist["Close"].iloc[-2] if len(hist) > 1 else current_price
                )
                change = round(
                    ((current_price - prev_close) / prev_close) * 100, 2
                )
                market_data[ticker] = {
                    "price": current_price,
                    "change": change,
                }
            else:
                market_data[ticker] = {"price": 0.0, "change": 0.0}
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            market_data[ticker] = {"price": 0.0, "change": 0.0}
    return market_data


# נתוני קנייה ומחיר יעד של התיק בסעיף 5
portfolio_buys = {
    "NVDA": {"shares": 3, "buy": 184.90, "target": 220.0},
    "AMD": {"shares": 20, "buy": 211.34, "target": 250.0},
    "MU": {"shares": 6, "buy": 316.32, "target": 350.0},
    "SNDK": {"shares": 4, "buy": 630.26, "target": 700.0},
    "WDC": {"shares": 6, "buy": 223.23, "target": 260.0},
    "INTC": {"shares": 20, "buy": 43.05, "target": 55.0},
    "SIMO": {"shares": 30, "buy": 131.32, "target": 160.0},
    "IREN": {"shares": 54, "buy": 52.75, "target": 70.0},
    "CIFR": {"shares": 28, "buy": 17.50, "target": 25.0},
    "META": {"shares": 2, "buy": 661.00, "target": 750.0},
    "AMZN": {"shares": 6, "buy": 229.29, "target": 270.0},
    "GOOG": {"shares": 4, "buy": 317.95, "target": 360.0},
    "TTWO": {"shares": 5, "buy": 235.50, "target": 280.0},
    "WMT": {"shares": 16, "buy": 119.45, "target": 140.0},
    "NFLX": {"shares": 14, "buy": 94.03, "target": 120.0},
    "MA": {"shares": 4, "buy": 503.99, "target": 580.0},
    "IBIT": {"shares": 14, "buy": 60.48, "target": 75.0},
    "GTEC": {"shares": 260, "buy": 1.27, "target": 2.0},
    "TQQQ": {"shares": 28, "buy": 56.53, "target": 75.0},
}


def generate_ai_insights(market_data):
    """פונה ל-Gemini API עם מנגנון גיבוי ומייצר את כל הטקסטים הדינמיים למערכת"""
    api_keys = [
        os.environ.get("GEMINI_API_KEY_1") or os.environ.get("GEMINI_API_KEY"),
        os.environ.get("GEMINI_API_KEY_2"),
    ]
    valid_keys = [k for k in api_keys if k]

    if not valid_keys:
        print("No GEMINI_API_KEY found. Skipping AI generation.")
        return {}

    prompt = (
        "אתה אנליסט בכיר בשוק ההון. ניתוח נתוני השוק החיים כרגע:\n"
        + json.dumps(market_data, ensure_ascii=False)
        + "\n\n"
        "**כללים קשיחים לחובה:**\n"
        "1. דרישת דיוק אנליטי ומספרי של לפחות 95%: עליך להקפיד על דיוק מקצועי גבוה ביותר, להסתמך אך ורק על נתוני הבסיס המסופקים מבלי להמציא או לשערך עובדות, ולוודא תאימות מוחלטת לנתוני השוק.\n"
        "2. פורמט מספרים: כל מספר מעל 1,000 חייב להיכתב תמיד עם פסיק מפריד אלפים (לדוגמה: 7,413.18 ולא 7413.18).\n\n"
        "החזר אובייקט JSON תקף בלבד (ללא טקסט עוטף או Markdown נוסף מעבר ל-JSON) הכולל את כל המפתחות הבאים בעברית מקצועית המותאמת למצב הנוכחי:\n"
        "- US_MARKET_MACRO_NEWS\n"
        "- IL_MARKET_MACRO_NEWS\n"
        "- SECTOR_CHIPS_DESC\n"
        "- SECTOR_CLOUD_DESC\n"
        "- SECTOR_CRYPTO_DESC\n"
        "- CATALYST_EARNINGS\n"
        "- CATALYST_MONETARY\n"
        "- CATALYST_HARDWARE\n"
        "- COMMUNITY_SENTIMENT\n"
        "- ANALYST_POINT_1\n"
        "- ANALYST_POINT_2\n"
        "- RISK_MANAGEMENT_TEXT\n"
        "- ACTION_RECOMMENDATIONS_TEXT\n\n"
        + f"וכמו כן, עבור כל אחד מהסימולים הבאים ({', '.join(all_strategy_tickers)}), הוסף מפתחות ניתוח וחדשות:\n"
        "1. [TICKER]_RATIONALE\n"
        "2. [TICKER]_SWING_TEXT\n"
        "3. [TICKER]_NEWS_TITLE\n"
        "4. [TICKER]_NEWS_CONTENT\n"
        "5. [TICKER]_NEWS_IMPACT\n"
        "6. [TICKER]_NEWS_LINK\n"
        "7. [TICKER]_PORT_NOTE"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"response_mime_type": "application/json"},
    }

    for i, api_key in enumerate(valid_keys, 1):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
            res = requests.post(url, json=payload, timeout=40)
            res_data = res.json()

            if "candidates" in res_data:
                text_response = (
                    res_data["candidates"][0]["content"]["parts"][0]["text"]
                )

                text_response = text_response.strip()
                if text_response.startswith("```json"):
                    text_response = text_response[7:]
                if text_response.startswith("```"):
                    text_response = text_response[3:]
                if text_response.endswith("```"):
                    text_response = text_response[:-3]
                text_response = text_response.strip()

                print(
                    f"Successfully generated full dynamic AI insights using API Key #{i}"
                )
                return json.loads(text_response)

            error_code = res_data.get("error", {}).get("code")
            if error_code == 429:
                print(
                    f"API Key #{i} exceeded quota (429). Switching to next"
                    " key..."
                )
                continue
            else:
                print(f"API Key #{i} Error Response: {res_data}")
                continue

        except Exception as e:
            print(f"Error calling Gemini API with key #{i}: {e}")
            continue

    print("All API keys failed or exceeded quota.")
    return {}


is_within_auto_hours = 630 <= current_total_minutes <= 1410
should_update = (trigger_event == "workflow_dispatch") or is_within_auto_hours

if should_update:
    market_data = fetch_all_data()
    ai_insights = generate_ai_insights(market_data)

    try:
        date_str = now_il.strftime("%d.%m.%Y")
        time_str = now_il.strftime("%H:%M")

        sp500 = market_data.get("^GSPC", {})
        nasdaq = market_data.get("^IXIC", {})
        dji = market_data.get("^DJI", {})
        vix = market_data.get("^VIX", {})
        dxy = market_data.get("USDILS=X", {})

        sp500_price = format_num(sp500.get("price", 0))
        sp500_change = f"{sp500.get('change', 0)}%"

        nasdaq_price = format_num(nasdaq.get("price", 0))
        nasdaq_change = f"{nasdaq.get('change', 0)}%"

        dji_price = format_num(dji.get("price", 0))
        dji_change = f"{dji.get('change', 0)}%"

        vix_price = format_num(vix.get("price", 0))
        vix_change = f"{vix.get('change', 0)}%"

        dxy_price = format_num(dxy.get("price", 0))
        dxy_change = f"{dxy.get('change', 0)}%"

        # שימוש במשתנים בטוחים כדי למנוע חיתוך תווים בדפדפן
        oil_ticker = "CL=F"
        gold_ticker = "GC=F"
        btc_ticker = "BTC-USD"
        fx_ticker = "USDILS=X"

        oil_data = market_data.get(oil_ticker, {})
        oil_price = format_num(oil_data.get("price", 75.0))
        oil_change = f"{oil_data.get('change', 0)}%"

        gold_data = market_data.get(gold_ticker, {})
        gold_price = format_num(gold_data.get("price", 2350.0))
        gold_change = f"{gold_data.get('change', 0)}%"

        btc_data = market_data.get(btc_ticker, {})
        btc_price = format_num(btc_data.get("price", 65000.0))
        btc_change = f"{btc_data.get('change', 0)}%"

        fx_data = market_data.get(fx_ticker, {})
        usd_ils_price = format_num(fx_data.get("price", 3.65))
        usd_ils_change = f"{fx_data.get('change', 0)}%"

        replacements = {
            "LAST_UPDATED": f"{date_str} | {time_str}",
            "SNP_500_LEVEL": sp500_price,
            "SP500_PRICE": sp500_price,
            "SP500_LEVEL": sp500_price,
            "SNP_500_CHANGE": sp500_change,
            "SP500_CHANGE": sp500_change,
            "SP500_PCT": sp500_change,
            "NASDAQ_LEVEL": nasdaq_price,
            "NASDAQ_PRICE": nasdaq_price,
            "NASDAQ_CHANGE": nasdaq_change,
            "NASDAQ_PCT": nasdaq_change,
            "DJI_LEVEL": dji_price,
            "DJI_PRICE": dji_price,
            "DJI_CHANGE": dji_change,
            "DJI_PCT": dji_change,
            "DOW_PRICE": dji_price,
            "DOW_PCT": dji_change,
            "VIX_LEVEL": vix_price,
            "VIX_PRICE": vix_price,
            "VIX_CHANGE": vix_change,
            "VIX_PCT": vix_change,
            "DXY_LEVEL": dxy_price,
            "DXY_PRICE": dxy_price,
            "DXY_CHANGE": dxy_change,
            "DXY_PCT": dxy_change,
            "USD_ILS": usd_ils_price,
            "USD_ILS_PRICE": usd_ils_price,
            "USD_ILS_RATE": usd_ils_price,
            "USD_ILS_CHANGE": usd_ils_change,
            "OIL_PRICE": oil_price,
            "OIL_CHANGE": oil_change,
            "GOLD_PRICE": gold_price,
            "GOLD_CHANGE": gold_change,
            "BTC_PRICE": btc_price,
            "BTC_CHANGE": btc_change,
            "US_MARKET_NEWS": ai_insights.get(
                "US_MARKET_MACRO_NEWS",
                "נתוני המאקרו ממשיכים להוות מנוע ניווט בשווקים.",
            ),
            "IL_MARKET_NEWS": ai_insights.get(
                "IL_MARKET_MACRO_NEWS", "השוק המקומי מגיב להתפתחויות הכלכליות."
            ),
            "SECTOR_CHIPS_DESC": ai_insights.get(
                "SECTOR_CHIPS_DESC",
                "ביקושים חזקים לשבבי בינה מלאכותית וחומרה מתקדמת.",
            ),
            "SECTOR_CLOUD_DESC": ai_insights.get(
                "SECTOR_CLOUD_DESC",
                "צמיחה מתמשכת בתשתיות ענן ושירותי מחשוב מבוסס ענן.",
            ),
            "SECTOR_CRYPTO_DESC": ai_insights.get(
                "SECTOR_CRYPTO_DESC",
                "תנודתיות ערה ופעילות ענפה בנכסים דיגיטליים ובלוקצ'יין.",
            ),
            "CATALYST_EARNINGS": ai_insights.get(
                "CATALYST_EARNINGS", "מעקב אחר דוחות רבעוניים וציפיות אנליסטים."
            ),
            "CATALYST_MONETARY": ai_insights.get(
                "CATALYST_MONETARY",
                "החלטות מדיניות מוניטרית, ריבית ובנקים מרכזיים.",
            ),
            "CATALYST_HARDWARE": ai_insights.get(
                "CATALYST_HARDWARE", "השקות מוצרים טכנולוגיים ועדכוני תוכנה."
            ),
            "COMMUNITY_SENTIMENT": ai_insights.get(
                "COMMUNITY_SENTIMENT", "אופטימיות זהירה המלווה בסלקטיביות."
            ),
            "ANALYST_POINT_1": ai_insights.get(
                "ANALYST_POINT_1",
                "התמקדות בחברות בעלות צמיחה חזקה ותזרים מזומנים יציב.",
            ),
            "ANALYST_POINT_2": ai_insights.get(
                "ANALYST_POINT_2",
                "מעקב הדוק אחר מדיניות הבנקים המרכזיים ונתוני האינפלציה.",
            ),
            "RISK_MANAGEMENT_TEXT": ai_insights.get(
                "RISK_MANAGEMENT_TEXT",
                "ניהול סיכונים קפדני באמצעות פקודות סטופ-לוס וגודל פוזיציה מדוד.",
            ),
            "ACTION_RECOMMENDATIONS_TEXT": ai_insights.get(
                "ACTION_RECOMMENDATIONS_TEXT",
                "בחינה מדודה של פוזיציות קיימות והיערכות להזדמנויות בשוק.",
            ),
        }

        for ticker in all_strategy_tickers:
            p_data = market_data.get(ticker, {})
            price_val = format_num(p_data.get("price", 0.0))
            pct_val = f"{p_data.get('change', 0.0)}%"
            target_val = format_num(
                portfolio_buys.get(ticker, {}).get("target", 0.0)
            )
            rationale_val = ai_insights.get(
                f"{ticker}_RATIONALE", "ניתוח מניה עדכני מתבצע..."
            )
            swing_val = ai_insights.get(
                f"{ticker}_SWING_TEXT", "מומנטום קצר טווח נבחן בשוק..."
            )

            for prefix in [
                f"{ticker}_LONG",
                f"{ticker}_SWING",
                ticker,
            ]:
                replacements[f"{prefix}_PRICE"] = price_val
                replacements[f"{prefix}_PRE"] = price_val
                replacements[f"{prefix}_PCT"] = pct_val
                replacements[f"{prefix}_TARGET"] = target_val
                replacements[f"{prefix}_RATIONALE"] = rationale_val
                replacements[f"{prefix}_TEXT"] = swing_val

            replacements[f"{ticker}_SWING_TEXT_2"] = (
                f"עדכון מומנטום נוסף עבור {ticker}."
            )

        for ticker, info in portfolio_buys.items():
            curr_p = market_data.get(ticker, {}).get("price", info["buy"])
            ret = round(((curr_p - info["buy"]) / info["buy"]) * 100, 2)
            ret_str = f"+{ret}%" if ret >= 0 else f"{ret}%"
            status_str = f"רווח {ret_str}" if ret >= 0 else f"הפסד {ret_str}"

            replacements[f"{ticker}_PORT_STATUS"] = status_str
            replacements[f"{ticker}_PORT_TARGET"] = format_num(info["target"])
            replacements[f"{ticker}_PORT_PRE"] = format_num(curr_p)
            replacements[f"{ticker}_PORT_CURRENT"] = format_num(curr_p)
            replacements[f"{ticker}_PORT_NOTE"] = ai_insights.get(
                f"{ticker}_PORT_NOTE",
                "מעקב פוזיציה שוטף מבוסס ביצועי שוק נוכחיים.",
            )

            replacements[f"PORTFOLIO_{ticker}_PRICE"] = format_num(curr_p)
            replacements[f"PORTFOLIO_{ticker}_STATUS"] = status_str
            replacements[f"PORTFOLIO_{ticker}_TARGET"] = format_num(
                info["target"]
            )
            replacements[f"PORTFOLIO_{ticker}_PRE"] = format_num(curr_p)

        for ticker in all_strategy_tickers:
            replacements[f"{ticker}_NEWS_LINK"] = (
                f"[https://finance.yahoo.com/quote/](https://finance.yahoo.com/quote/){ticker}"
            )
            replacements[f"{ticker}_NEWS_TITLE"] = ai_insights.get(
                f"{ticker}_NEWS_TITLE", f"עדכון שוק מרכזי עבור מניית {ticker}"
            )
            replacements[f"{ticker}_NEWS_CONTENT"] = ai_insights.get(
                f"{ticker}_NEWS_CONTENT",
                f"ניתוח פעילות מסחר ונתונים פיננסיים עדכניים עבור {ticker}.",
            )
            replacements[f"{ticker}_NEWS_IMPACT"] = ai_insights.get(
                f"{ticker}_NEWS_IMPACT",
                "השפעה חיובית ומתונה על תיק ההשקעות והמגמה הראשית.",
            )

        with open("index.template.html", "r", encoding="utf-8-sig") as f:
            content = f.read()

        # החלפת תגיות ה-US וה-IL בדגלים לבקשתך
        content = content.replace("US השפעות", "🇺🇸 השפעות")
        content = content.replace("IL השפעות", "🇮🇱 השפעות")
        content = content.replace("US:", "🇺🇸")
        content = content.replace("IL:", "🇮🇱")

        for ticker in all_strategy_tickers:
            bad_link_pattern = (
                f"קישור למקור: {ticker}/{{{{{ticker}}_NEWS_LINK}}}"
            )
            good_link_html = f'קישור למקור: <a href="{{{{{ticker}}_NEWS_LINK}}}}" target="_blank" style="color: #38bdf8; text-decoration: underline; font-weight: bold;">מעבר לאתר החדשות של {ticker}</a>'
            content = content.replace(bad_link_pattern, good_link_html)

            double_bad_pattern = f"{ticker}/{{{{{ticker}}_NEWS_LINK}}}/{{{{{ticker}}_NEWS_LINK}}}"
            content = content.replace(
                double_bad_pattern,
                f'<a href="{{{{{ticker}}_NEWS_LINK}}}}" target="_blank" style="color: #38bdf8; text-decoration: underline;">{ticker}</a>',
            )

        for key, val in replacements.items():
            placeholder = f"{{{{{key}}}}}"
            content = content.replace(placeholder, str(val))

        # עיצוב מחדש של קבוצה א', קבוצה ב' וסעיף 5 לתצוגת בלוקים (שורה מתחת לשורה) לנוחות קריאה
        for class_name in [
            "long-item",
            "swing-item",
            "port-item",
            "portfolio-item",
        ]:
            content = content.replace(
                f"class='{class_name}'",
                f"class='{class_name}' style='display: block; margin-bottom: 14px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 12px; line-height: 1.6;'",
            )
            content = content.replace(
                f'class="{class_name}"',
                f'class="{class_name}" style="display: block; margin-bottom: 14px; border-bottom: 1px solid rgba(255,255,255,0.06); padding-bottom: 12px; line-height: 1.6;"',
            )

        with open("index.html", "w", encoding="utf-8") as f:
            f.write(content)

        print("Successfully updated index.html with live AI injection data.")

        subprocess.run(
            ["git", "config", "--global", "user.name", "github-actions[bot]"],
            check=True,
        )
        subprocess.run(
            [
                "git",
                "config",
                "--global",
                "user.email",
                "github-actions[bot]@users.noreply.github.com",
            ],
            check=True,
        )
        subprocess.run(["git", "add", "index.html"], check=True)

        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        )
        if "index.html" in status.stdout:
            subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    (
                        "Auto-update full dynamic AI injection report for"
                        f" {day_name} at {time_str}"
                    ),
                ],
                check=True,
            )
            subprocess.run(["git", "push"], check=True)
            print("Changes committed and pushed successfully.")
        else:
            print("No changes in index.html to commit.")

    except Exception as e:
        print(f"Error updating file: {e}")
else:
    print("Outside active automated hours. Skipping scheduled run.")
