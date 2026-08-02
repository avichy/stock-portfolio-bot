from datetime import datetime
import json
import os
import subprocess
import time
import traceback
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


def format_pct_colored(val):
  """מפרמט אחוזים עם צבע HTML: ירוק לחיובי, אדום לשלילי"""
  try:
    num = float(val)
    sign = "+" if num > 0 else ""
    color = "#2ecc71" if num >= 0 else "#e74c3c"
    return f'<span style="color: {color}; font-weight: bold;">{sign}{num:.2f}%</span>'
  except (ValueError, TypeError):
    return str(val)


# הגדרת אזור זמן של ישראל
israel_tz = pytz.timezone("Asia/Jerusalem")
now_il = datetime.now(israel_tz)

current_date = now_il.date()
current_hour = now_il.hour
current_minute = now_il.minute

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

# נתוני קנייה ומחיר בסיס של התיק האישי (לשמירת טבלת הפוזיציות הקיימת)
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

# סימולים כלליים למשיכת נתוני שוק בסיסיים (מדדים, סחורות, מט"ח ותיק)
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
  """מושך נתוני מחיר, שינוי יומי ויעד אנליסטים מ-yfinance עבור רשימת סימולים"""
  market_data = {}
  for ticker in tickers:
    try:
      stock = yf.Ticker(ticker)
      hist = stock.history(period="2d")
      info = stock.info
      target_mean = info.get("targetMeanPrice")

      if not hist.empty:
        current_price = round(hist["Close"].iloc[-1], 2)
        prev_close = hist["Close"].iloc[-2] if len(hist) > 1 else current_price
        change = round(((current_price - prev_close) / prev_close) * 100, 2)
        market_data[ticker] = {
            "price": current_price,
            "change": change,
            "target": target_mean if target_mean else 0.0,
        }
      else:
        market_data[ticker] = {"price": 0.0, "change": 0.0, "target": 0.0}
    except Exception as e:
      print(f"Error fetching {ticker}: {e}")
      market_data[ticker] = {"price": 0.0, "change": 0.0, "target": 0.0}
  return market_data


# ניהול מפתחות גלובלי למעבר בין מפתחות במקרה של שגיאה
current_key_index = 0


def call_gemini_with_rotation(prompt, valid_keys):
  """שולח בקשה ל-Gemini עם מנגנון סיבוב מפתחות והשהיות במקרה של עומס או שגיאת 429"""
  global current_key_index
  payload = {
      "contents": [{"parts": [{"text": prompt}]}],
      "generationConfig": {"response_mime_type": "application/json"},
  }

  max_attempts = len(valid_keys) * 2
  attempts = 0

  while attempts < max_attempts:
    api_key = valid_keys[current_key_index % len(valid_keys)]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    try:
      res = requests.post(url, json=payload, timeout=50)
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

        print(
            "Successfully generated AI chunk using Key Index"
            f" {current_key_index % len(valid_keys)}"
        )
        return json.loads(text_response.strip())

      error_code = res_data.get("error", {}).get("code")
      if error_code == 429:
        print(
            f"API Key index {current_key_index % len(valid_keys)} exceeded"
            " quota (429). Switching key & waiting..."
        )
        current_key_index += 1
        time.sleep(15)
      else:
        print(f"Gemini API Error Response: {res_data}")
        current_key_index += 1
        time.sleep(5)
    except Exception as e:
      print(f"Error calling Gemini API: {e}")
      current_key_index += 1
      time.sleep(5)

    attempts += 1
  return {}


def generate_ai_insights(market_data):
  """מייצר את ניתוחי המדדים ואת 10+10 המניות הדינמיות מה-AI"""
  api_keys = [
      os.environ.get("GEMINI_API_KEY_1") or os.environ.get("GEMINI_API_KEY"),
      os.environ.get("GEMINI_API_KEY_2"),
  ]
  valid_keys = [k for k in api_keys if k]

  if not valid_keys:
    print("No GEMINI_API_KEY found. Skipping AI generation.")
    return {}

  print(
      "Generating Macro analysis, Indices analysis, and Dynamic 10+10 stocks"
      " selection from AI..."
  )
  prompt = (
      "אתה אנליסט בכיר בשוק ההון. נתח את נתוני המאקרו והשוק הבאים:\n"
      + json.dumps(market_data, ensure_ascii=False)
      + "\n\nכללי חובה קשיחים:\n"
      "1. ספק ניתוח אנליסטי מפורט וגנרי תחת "
      "SP500_ANALYSIS, NASDAQ_ANALYSIS, DOW_ANALYSIS, VIX_ANALYSIS, DXY_ANALYSIS.\n"
      "2. בחר והחזר בדיוק **10 מניות** להשקעה ארוכת טווח (Long-Term Core) תחת"
      " המפתח 'long_term_stocks' כמערך JSON הכולל את השדות: symbol, name,"
      " target, rationale.\n"
      "3. בחר והחזר בדיוק **10 מניות** למסחר סווינג קצר טווח (Swing Trading)"
      " תחת המפתח 'swing_stocks' כמערך JSON הכולל את השדות: symbol, name,"
      " target, sector_desc, rationale.\n"
      "4. הוסף ניתוחי מאקרו כלליים תחת המפתחות:"
      " US_MARKET_MACRO_NEWS, IL_MARKET_MACRO_NEWS, RISK_MANAGEMENT_TEXT,"
      " ACTION_RECOMMENDATIONS_TEXT.\n"
      "5. החזר אובייקט JSON תקף בלבד, ללא שום טקסט נוסף מסביב.\n"
  )

  ai_res = {}
  for attempt in range(3):
    ai_res = call_gemini_with_rotation(prompt, valid_keys)
    if isinstance(ai_res, dict) and len(ai_res) > 0:
      break
    print(f"AI generation failed or empty, retrying attempt {attempt+1}...")
    time.sleep(10)

  return ai_res


# מעדכן תמיד בכל הרצה
should_update = True

if should_update:
  try:
    base_market_data = fetch_market_data(base_market_tickers)
    ai_insights = generate_ai_insights(base_market_data)

    date_str = now_il.strftime("%d.%m.%Y")
    time_str = now_il.strftime("%H:%M")

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

    # שליפת 10 מניות ארוכות טווח ו-10 מניות סווינג שהוחזרו מה-AI
    long_term_stocks = ai_insights.get("long_term_stocks", [])
    swing_stocks = ai_insights.get("swing_stocks", [])

    # איסוף הסימולים שלהן כדי לשלוף עבורן מחירים חיים מעודכנים מ-yfinance
    dynamic_tickers = [
        s.get("symbol") for s in long_term_stocks if "symbol" in s
    ] + [s.get("symbol") for s in swing_stocks if "symbol" in s]

    dynamic_market_data = fetch_market_data(dynamic_tickers)

    # בניית ה-HTML עבור קבוצת מניות ארוכות טווח
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

      long_term_html_blocks += f"""
        <p class="border-b border-gray-700 pb-3">
            🚀 <strong>{name}</strong> (סמל: <strong>{sym}</strong>)<br>
            מחיר נוכחי: <strong>{price_str}</strong> (<span class="text-cyan-300">{pct_str}</span>)<br>
            מחיר יעד אנליסטים ממוצע: <strong>{target_str}</strong><br>
            <strong>רציונל וניתוח AI:</strong> <span class="text-gray-200">{rationale}</span>
        </p>
        """

    # בניית ה-HTML עבור קבוצת מניות סווינג
    swing_html_blocks = ""
    for stock in swing_stocks:
      sym = stock.get("symbol", "")
      name = stock.get("name", sym)
      sector_desc = stock.get("sector_desc", "")
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

      swing_html_blocks += f"""
        <p class="border-b border-gray-700 pb-3">
            ⚡ <strong>{name}</strong> (סמל: <strong>{sym}</strong>)<br>
            מחיר נוכחי: <strong>{price_str}</strong> (<span class="text-cyan-300">{pct_str}</span>)<br>
            יעד למסחר: <strong>{target_str}</strong><br>
            תחום עיסוק: {sector_desc}<br>
            <strong>רציונל וחדשות:</strong> <span class="text-gray-200">{rationale}</span>
        </p>
        """

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
        "SP500_ANALYSIS": ai_insights.get(
            "SP500_ANALYSIS", "ניתוח מדד S&P 500 מתעדכן..."
        ),
        "NASDAQ_ANALYSIS": ai_insights.get(
            "NASDAQ_ANALYSIS", "ניתוח מדד נאסד\"ק מתעדכן..."
        ),
        "DOW_ANALYSIS": ai_insights.get(
            "DOW_ANALYSIS", "ניתוח מדד דאו ג'ונס מתעדכן..."
        ),
        "VIX_ANALYSIS": ai_insights.get(
            "VIX_ANALYSIS", "ניתוח מדד הפחד VIX מתעדכן..."
        ),
        "DXY_ANALYSIS": ai_insights.get(
            "DXY_ANALYSIS", "ניתוח מדד הדולר מתעדכן..."
        ),
        "LONG_TERM_STOCKS_SECTION": long_term_html_blocks,
        "SWING_STOCKS_SECTION": swing_html_blocks,
        "US_MARKET_NEWS": ai_insights.get(
            "US_MARKET_MACRO_NEWS",
            "נתוני המאקרו ממשיכים להוות מנוע ניווט בשווקים.",
        ),
        "IL_MARKET_NEWS": ai_insights.get(
            "IL_MARKET_MACRO_NEWS", "השוק המקומי מגיב להתפתחויות הכלכליות."
        ),
        "RISK_MANAGEMENT_TEXT": ai_insights.get(
            "RISK_MANAGEMENT_TEXT",
            "ניהול סיכונים קפדני באמצעות פקודות סטופ-לוס וגודל פוזיציה מדוד.",
        ),
        "ACTION_RECOMMENDATIONS_TEXT": ai_insights.get(
            "ACTION_RECOMMENDATIONS_TEXT",
            "בחינה מדודה של פוזיציות קיימות והיערכות להזדמנויות בשוק.",
        ),
        "USD_ILS": usd_ils_price,
        "USD_ILS_CHANGE": usd_ils_change,
        "OIL_PRICE": oil_price,
        "OIL_CHANGE": oil_change,
        "GOLD_PRICE": gold_price,
        "GOLD_CHANGE": gold_change,
        "BTC_PRICE": btc_price,
        "BTC_CHANGE": btc_change,
    }

    # עדכון נתוני תיק ההשקעות האישי (Portfolio Buys) לשמירת תאימות טבלאות
    for ticker, info in portfolio_buys.items():
      curr_p = base_market_data.get(ticker, {}).get("price", info["buy"])
      ret = round(((curr_p - info["buy"]) / info["buy"]) * 100, 2)
      ret_str = format_pct_colored(ret)
      status_str = f"רווח {ret_str}" if ret >= 0 else f"הפסד {ret_str}"
      curr_p_str = f"${format_num(curr_p)}"
      fetched_target = base_market_data.get(ticker, {}).get("target", 0.0)
      if not fetched_target or fetched_target == 0.0:
        fetched_target = info["buy"] * 1.25
      target_p_str = f"${format_num(fetched_target)}"

      replacements[f"{ticker}_PORT_STATUS"] = status_str
      replacements[f"{ticker}_PORT_TARGET"] = target_p_str
      replacements[f"{ticker}_PORT_PRE"] = curr_p_str
      replacements[f"{ticker}_PORT_CURRENT"] = curr_p_str
      replacements[f"{ticker}_PORT_NOTE"] = (
          "מעקב פוזיציה שוטף מבוסס ביצועי שוק נוכחיים."
      )

    with open("index.template.html", "r", encoding="utf-8-sig") as f:
      content = f.read()

    for key, val in replacements.items():
      placeholder = f"{{{{{key}}}}}"
      content = content.replace(placeholder, str(val))

    with open("index.html", "w", encoding="utf-8") as f:
      f.write(content)

    print(
        "Successfully updated index.html with dynamic AI indices & 10+10 stock"
        " strategy."
    )

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
      commit_message = f"Auto-update dynamic AI 10+10 report for {day_name} at {time_str}"
      subprocess.run(["git", "commit", "-m", commit_message], check=True)
      subprocess.run(["git", "pull", "origin", "main", "--rebase"], check=True)
      subprocess.run(["git", "push"], check=True)
      print("Changes committed and pushed successfully.")
    else:
      print("No changes in index.html to commit.")

  except Exception as e:
    print(f"Error updating file: {e}")
    traceback.print_exc()
else:
  print("Outside active automated hours. Skipping scheduled run.")
