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
  """מייצר את ניתוחי המדדים, 10+10 המניות והחדשות הדינמיות מה-AI"""
  api_keys = [
      os.environ.get("GEMINI_API_KEY_1") or os.environ.get("GEMINI_API_KEY"),
      os.environ.get("GEMINI_API_KEY_2"),
      os.environ.get("GEMINI_API_KEY_3"),
  ]
  valid_keys = [k for k in api_keys if k]

  if not valid_keys:
    print("No GEMINI_API_KEY found. Skipping AI generation.")
    return {}

  print(
      "Generating Macro analysis, Indices analysis, Dynamic 10+10 stocks &"
      " News from AI..."
  )

  market_json = json.dumps(market_data, ensure_ascii=False)

  # שימוש בשרשור מחרוזות רגיל למניעת שגיאות תחביר של Python עם טקסט עברי
  prompt = (
      "אתה אנליסט בכיר בשוק ההון. נתח את נתוני המאקרו והשוק הבאים:\n"
      + market_json
      + "\n\nכללי חובה קשיחים:\n"
      "1. ספק ניתוח אנליסטי מפורט וגנרי תחת SP500_ANALYSIS, NASDAQ_ANALYSIS,"
      " DOW_ANALYSIS, VIX_ANALYSIS, DXY_ANALYSIS.\n"
      "2. בחר והחזר בדיוק **10 מניות** להשקעה ארוכת טווח (Long-Term Core)"
      " תחת המפתח 'long_term_stocks' כמערך JSON הכולל את השדות: symbol, name,"
      " target, rationale, news_title, news_content, news_impact.\n"
      "3. בחר והחזר בדיוק **10 מניות** למסחר סווינג קצר טווח (Swing Trading)"
      " תחת המפתח 'swing_stocks' כמערך JSON הכולל את השדות: symbol, name,"
      " target, sector_desc, rationale, news_title, news_content, news_impact.\n"
      "4. הוסף הסברים קצרים בשפה פשוטה ומעודכנית למצב השוק הנוכחי עבור ארבעת
