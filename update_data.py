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
      market_data[ticker] = {"price": 0.0, "change": 0.0, "target": 0.0}
  return market_data


current_key_index = 0


def generate_ai_insights(market_data):
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
    return {}

  market_json = json.dumps(market_data, ensure_ascii=False)
  prompt_raw = (
      "אתה אנליסט בכיר בשוק ההון. נתח את נתוני המאקרו והשוק הבאים:\n"
      f"{market_json}\n\n"
      "כללי חובה קשיחים:\n"
      "1. ספק ניתוח אנליסטי מפורט וגנרי תחת SP500_ANALYSIS, NASDAQ_ANALYSIS,"
      " DOW_ANALYSIS, VIX_ANALYSIS, DXY_ANALYSIS.\n"
      "2. בחר והחזר בדיוק **10 מניות** להשקעה ארוכת טווח (Long-Term Core)"
      " תחת המפתח 'long_term_stocks' כמערך JSON הכולל את השדות: symbol, name,"
      " target, rationale, news_title, news_content, news_impact.\n"
      "3. בחר והחזר בדיוק **10 מניות** למסחר סווינג קצר טווח (Swing Trading)"
      " תחת המפתח 'swing_stocks' כמערך JSON הכולל את השדות: symbol, name,"
      " target, sector_desc, rationale, news_title, news_content, news_impact.\n"
      "4. הוסף הסברים קצרים בשפה פשוטה ומעודכנית למצב השוק הנוכחי עבור ארבעת"
      " הנכסים הבאים תחת המפתחות:\n"
      "   - USD_ILS_EXPLANATION\n"
      "   - OIL_EXPLANATION\n"
      "   - GOLD_EXPLANATION\n"
      "   - BTC_EXPLANATION\n"
      "5. הוסף ניתוחי מאקרו כלליים תחת המפתחות: US_MARKET_MACRO_NEWS,"
      " IL_MARKET_MACRO_NEWS, RISK_MANAGEMENT_TEXT, ACTION_RECOMMENDATIONS_TEXT.\n"
      "6. החזר אובייקט JSON תקף בלבד, ללא שום טקסט נוסף מסביב.\n"
  )

  payload = {
      "contents": [{"parts": [{"text": prompt_raw}]}],
      "generationConfig": {"response_mime_type": "application/json"},
  }

  max_attempts = len(valid_keys) * 3
  attempts = 0
  while attempts < max_attempts:
    api_key = valid_keys[current_key_index % len(valid_keys)]
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    try:
      res = requests.post(url, json=payload, timeout=50)
      res_data = res.json()
      if "candidates" in res_data:
        text_response = (
            res_data["candidates"][0]["content"]["parts"][0]["text"].strip()
        )
        if text_response.startswith("```json"):
          text_response = text_response[7:]
        if text_response.startswith("```"):
          text_response = text_response[3:]
        if text_response.endswith("```"):
          text_response = text_response[:-3]
        parsed_res = json.loads(text_response.strip())
        if isinstance(parsed_res, dict) and len(parsed_res) > 0:
          return parsed_res
      if res_data.get("error", {}).get("code") == 429:
        current_key_index += 1
        time.sleep(20)
      else:
        current_key_index += 1
        time.sleep(5)
    except Exception:
      current_key_index += 1
      time.sleep(5)
    attempts += 1
  return {}


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

  long_term_stocks = ai_insights.get("long_term_stocks", [])
  swing_stocks = ai_insights.get("swing_stocks", [])

  dynamic_tickers = [
      s.get("symbol") for s in long_term_stocks if "symbol" in s
  ] + [s.get("symbol") for s in swing_stocks if "symbol" in s]
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
    long_term_html_blocks += f"""
        <p class="border-b border-gray-700 pb-3">
            🚀 <strong>{name}</strong> (סמל: <strong>{sym}</strong>)<br>
            מחיר נוכחי: <strong>{price_str}</strong> (<span class="text-cyan-300">{pct_str}</span>)<br>
            מחיר יעד אנליסטים ממוצע: <strong>{target_str}</strong><br>
            <strong>רציונל וניתוח AI:</strong> <span class="text-gray-200">{rationale}</span>
        </p>
        """

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
    news_html_blocks += f"""
        <div class="bg-gray-800 p-4 rounded-xl border border-gray-700 shadow space-y-2 text-sm text-gray-300">
            <h3 class="text-cyan-400 font-semibold">חדשות {name} (סמל: {sym})</h3>
            <p>🔗 <strong>קישור למקור:</strong> <a href="{news_link}" target="_blank" class="text-cyan-400 hover:underline">{news_link}</a></p>
            <p><strong>כותרת הכתבה המלאה:</strong> {news_title}</p>
            <p><strong>תוכן הכתבה המלא:</strong> {news_content}</p>
            <p>🚀 <strong>מה זה אומר בקשר למניה:</strong> {news_impact}</p>
        </div>
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
          "NASDAQ_ANALYSIS", 'ניתוח מדד נאסד"ק מתעדכן...'
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
      "NEWS_SECTION": news_html_blocks,
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
      "USD_ILS_EXPLANATION": ai_insights.get(
          "USD_ILS_EXPLANATION",
          "השפעה ישירה על עלות ייבוא, מוצרים דולריים ותיק ההשקעות.",
      ),
      "OIL_EXPLANATION": ai_insights.get(
          "OIL_EXPLANATION",
          "משפיע ישירות על עלויות האנרגיה, הדלק ושיעורי האינפלציה.",
      ),
      "GOLD_EXPLANATION": ai_insights.get(
          "GOLD_EXPLANATION",
          "משמש כנכס מקלט בטוח וגידור מפני אי-יציבות בשווקים ובאינפלציה.",
      ),
      "BTC_EXPLANATION": ai_insights.get(
          "BTC_EXPLANATION",
          "אינדיקטור מוביל לסנטימנט סיכון, נזילות ונכסים אלטרנטיביים.",
      ),
  }

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
    content = content.replace(f"{{{{{key}}}}}", str(val))

  with open("index.html", "w", encoding="utf-8") as f:
    f.write(content)

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
      ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
  )
  if "index.html" in status.stdout:
    subprocess.run(
        [
            "git",
            "commit",
            "-m",
            f"Auto-update dynamic AI report & news for {day_name} at"
            f" {time_str}",
        ],
        check=True,
    )
    subprocess.run(["git", "pull", "origin", "main", "--rebase"], check=True)
    subprocess.run(["git", "push"], check=True)

except Exception as e:
  traceback.print_exc()
