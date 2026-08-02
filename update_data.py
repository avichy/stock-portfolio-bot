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

# נתוני קנייה ומחיר בסיס של התיק
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


def fetch_all_data():
  """מושך נתוני מחיר, שינוי יומי ויעד אנליסטים אמיתי מ-yfinance"""
  market_data = {}
  for ticker in tickers_to_fetch:
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
        time.sleep(12)
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
  """מייצר את כל הטקסטים הדינמיים בחלוקה לבאצ'ים כדי למנוע חריגת טוקנים"""
  api_keys = [
      os.environ.get("GEMINI_API_KEY_1") or os.environ.get("GEMINI_API_KEY"),
      os.environ.get("GEMINI_API_KEY_2"),
  ]
  valid_keys = [k for k in api_keys if k]

  if not valid_keys:
    print("No GEMINI_API_KEY found. Skipping AI generation.")
    return {}

  all_insights = {}

  # שלב 1: בקשה למאקרו וסקטורים כלליים
  print("Generating Macro & Sectors insights...")
  macro_prompt = (
      "אתה אנליסט בכיר בשוק ההון. נתח את נתוני המאקרו והשוק הבאים:\n"
      + json.dumps(market_data, ensure_ascii=False)
      + "\n\nכללי חובה:\n1. דיוק אנליטי גבוה.\n2. פורמט מספרים מעל 1,000 עם"
      " פסיק אלפים.\n\nהחזר אובייקט JSON תקף בלבד הכולל את המפתחות הבאים בעברית"
      " מקצועית:\n- US_MARKET_MACRO_NEWS\n- IL_MARKET_MACRO_NEWS\n-"
      " SECTOR_CHIPS_DESC\n- SECTOR_CLOUD_DESC\n- SECTOR_CRYPTO_DESC\n-"
      " CATALYST_EARNINGS\n- CATALYST_MONETARY\n- CATALYST_HARDWARE\n-"
      " COMMUNITY_SENTIMENT\n- ANALYST_POINT_1\n- ANALYST_POINT_2\n-"
      " RISK_MANAGEMENT_TEXT\n- ACTION_RECOMMENDATIONS_TEXT"
  )

  macro_res = call_gemini_with_rotation(macro_prompt, valid_keys)
  if isinstance(macro_res, dict):
    all_insights.update(macro_res)

  time.sleep(10)  # השהייה בין בקשות למניעת עומס

  # שלב 2: חלוקת המניות לקבוצות (באצ'ים של 5 מניות בכל פעם)
  batch_size = 5
  for i in range(0, len(all_strategy_tickers), batch_size):
    batch = all_strategy_tickers[i : i + batch_size]
    print(f"Generating insights for batch: {batch}")
    batch_market_data = {t: market_data.get(t, {}) for t in batch}

    batch_prompt = (
        "אתה אנליסט בכיר בשוק ההון. עבור קבוצת המניות הבאה, ספק ניתוח מדויק"
        " ומקצועי מבוסס על נתוני השוק:\n"
        + json.dumps(batch_market_data, ensure_ascii=False)
        + "\n\nכללי חובה:\n1. כל מספר מעל 1,000 עם פסיק אלפים.\n2. השתמש במחירי"
        " יעד אמיתיים.\n\nהחזר אובייקט JSON תקף בלבד הכולל את כל המפתחות הבאים"
        " עבור *כל אחד* מהסימולים בקבוצה ("
        + ", ".join(batch)
        + "):\n- [TICKER]_RATIONALE\n- [TICKER]_SWING_TEXT\n- [TICKER]_NEWS_TITLE\n-"
        " [TICKER]_NEWS_CONTENT\n- [TICKER]_NEWS_IMPACT\n- [TICKER]_NEWS_LINK\n-"
        " [TICKER]_PORT_NOTE"
    )

    batch_res = call_gemini_with_rotation(batch_prompt, valid_keys)
    if isinstance(batch_res, dict):
      all_insights.update(batch_res)

    time.sleep(10)  # השהייה בין באצ'ים

  return all_insights


# מעדכן תמיד בכל הרצה
should_update = True

if should_update:
  try:
    market_data = fetch_all_data()
    ai_insights = generate_ai_insights(market_data)

    date_str = now_il.strftime("%d.%m.%Y")
    time_str = now_il.strftime("%H:%M")

    sp500 = market_data.get("^GSPC", {})
    nasdaq = market_data.get("^IXIC", {})
    dji = market_data.get("^DJI", {})
    vix = market_data.get("^VIX", {})
    dxy = market_data.get("USDILS=X", {})

    sp500_p = sp500.get("price", 0)
    sp500_c = sp500.get("change", 0)
    sp500_price = format_num(sp500_p)
    sp500_change = format_pct_colored(sp500_c)

    nasdaq_p = nasdaq.get("price", 0)
    nasdaq_c = nasdaq.get("change", 0)
    nasdaq_price = format_num(nasdaq_p)
    nasdaq_change = format_pct_colored(nasdaq_c)

    dji_p = dji.get("price", 0)
    dji_c = dji.get("change", 0)
    dji_price = format_num(dji_p)
    dji_change = format_pct_colored(dji_c)

    vix_p = vix.get("price", 0)
    vix_c = vix.get("change", 0)
    vix_price = format_num(vix_p)
    vix_change = format_pct_colored(vix_c)

    dxy_p = dxy.get("price", 0)
    dxy_c = dxy.get("change", 0)
    dxy_price = format_num(dxy_p)
    dxy_change = format_pct_colored(dxy_c)

    usd_ils_data = market_data.get("USDILS=X", {})
    usd_ils_p = usd_ils_data.get("price", 3.65)
    usd_ils_c = usd_ils_data.get("change", 0)
    usd_ils_price = f"{format_num(usd_ils_p)}₪"
    usd_ils_change = format_pct_colored(usd_ils_c)

    oil_data = market_data.get("CL=F", {})
    oil_p = oil_data.get("price", 75.0)
    oil_c = oil_data.get("change", 0)
    oil_price = f"${format_num(oil_p)}"
    oil_change = format_pct_colored(oil_c)

    gold_data = market_data.get("GC=F", {})
    gold_p = gold_data.get("price", 2350.0)
    gold_c = gold_data.get("change", 0)
    gold_price = f"${format_num(gold_p)}"
    gold_change = format_pct_colored(gold_c)

    btc_data = market_data.get("BTC-USD", {})
    btc_p = btc_data.get("price", 65000.0)
    btc_c = btc_data.get("change", 0)
    btc_price = f"${format_num(btc_p)}"
    btc_change = format_pct_colored(btc_c)

    replacements = {
        "LAST_UPDATED": f"{date_str} | {time_str}",
        "DAY_NAME": day_name,
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
      price_val = f"${format_num(p_data.get('price', 0.0))}"
      pct_val = format_pct_colored(p_data.get("change", 0.0))

      fetched_target = p_data.get("target", 0.0)
      if not fetched_target or fetched_target == 0.0:
        fetched_target = portfolio_buys.get(ticker, {}).get("buy", 0.0) * 1.25
      target_val = f"${format_num(fetched_target)}"

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
      ret_str = format_pct_colored(ret)
      status_str = f"רווח {ret_str}" if ret >= 0 else f"הפסד {ret_str}"

      curr_p_str = f"${format_num(curr_p)}"

      fetched_target = market_data.get(ticker, {}).get("target", 0.0)
      if not fetched_target or fetched_target == 0.0:
        fetched_target = info["buy"] * 1.25
      target_p_str = f"${format_num(fetched_target)}"

      replacements[f"{ticker}_PORT_STATUS"] = status_str
      replacements[f"{ticker}_PORT_TARGET"] = target_p_str
      replacements[f"{ticker}_PORT_PRE"] = curr_p_str
      replacements[f"{ticker}_PORT_CURRENT"] = curr_p_str
      replacements[f"{ticker}_PORT_NOTE"] = ai_insights.get(
          f"{ticker}_PORT_NOTE",
          "מעקב פוזיציה שוטף מבוסס ביצועי שוק נוכחיים.",
      )

      replacements[f"PORTFOLIO_{ticker}_PRICE"] = curr_p_str
      replacements[f"PORTFOLIO_{ticker}_STATUS"] = status_str
      replacements[f"PORTFOLIO_{ticker}_TARGET"] = target_p_str
      replacements[f"PORTFOLIO_{ticker}_PRE"] = curr_p_str

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

    for key, val in replacements.items():
      placeholder = f"{{{{{key}}}}}"
      content = content.replace(placeholder, str(val))

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
      commit_message = f"Auto-update full dynamic AI injection report for {day_name} at {time_str}"
      subprocess.run(
          ["git", "commit", "-m", commit_message],
          check=True,
      )
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
