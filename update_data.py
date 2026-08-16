import base64
from datetime import datetime
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import pytz
import requests
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


def format_ai_text(text):
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

  text = re.sub(
      r"^(?:ניתוח\s+ה?-?[^\n:]+|קָטָלִיסט[^\n:]*|השפעות[^\n:]*|סיכום"
      r" הכתבה:?|המלצות:?|ניהול\s+סיכונים:?|המלצה:?)\s*[:\-]?\s*",
      "",
      text,
      flags=re.IGNORECASE,
  )
  text = re.sub(
      r"^(?:🇺🇸|🇮🇱|US|IL)\s*(?:השפעות על השוק[^:]*)?[:\-]?\s*",
      "",
      text,
      flags=re.IGNORECASE,
  )

  cleaned = (
      text.replace("{", "")
      .replace("}", "")
      .replace("[", "")
      .replace("]", "")
      .replace('"', "")
      .replace("'", "")
  )

  cleaned = format_numbers_in_text(cleaned)
  return f'<div class="leading-relaxed text-sm text-gray-300">{cleaned}</div>'


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
              {"title": title.text.strip(), "link": link.text.strip()}
          )
      return news_items[:15]
  except Exception as e:
    print(f"Warning: Error fetching Hebrew Investing RSS: {e}")
    return []


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
          "XLK": {"price": 220.0, "change": 0.0, "target": 0.0, "pre_market": 220.0},
          "XLF": {"price": 45.0, "change": 0.0, "target": 0.0, "pre_market": 45.0},
          "XLV": {"price": 140.0, "change": 0.0, "target": 0.0, "pre_market": 140.0},
          "XLY": {"price": 180.0, "change": 0.0, "target": 0.0, "pre_market": 180.0},
          "XLP": {"price": 80.0, "change": 0.0, "target": 0.0, "pre_market": 80.0},
          "XLE": {"price": 90.0, "change": 0.0, "target": 0.0, "pre_market": 90.0},
          "XLI": {"price": 130.0, "change": 0.0, "target": 0.0, "pre_market": 130.0},
          "XLB": {"price": 90.0, "change": 0.0, "target": 0.0, "pre_market": 90.0},
          "XLC": {"price": 95.0, "change": 0.0, "target": 0.0, "pre_market": 95.0},
          "XLU": {"price": 75.0, "change": 0.0, "target": 0.0, "pre_market": 75.0},
          "XLRE": {"price": 40.0, "change": 0.0, "target": 0.0, "pre_market": 40.0},
      }
      market_data[ticker] = defaults.get(
          ticker, {"price": 100.0, "change": 0.0, "target": 0.0, "pre_market": 100.0}
      )
  return market_data


def fetch_ai_insights_from_groq(
    market_data, portfolio_stocks, date_str, day_name, time_str, investing_headlines
):
  api_keys = get_all_groq_keys()
  if not api_keys:
    print("❌ ERROR: No Groq API keys found! Using cached/defaults.")
    cached = load_ai_cache()
    return cached if cached else {}

  max_rounds = 2
  for attempt_round in range(1, max_rounds + 1):
    print(f"🔄 Starting Groq AI request round {attempt_round}/{max_rounds}...")
    for key_name, api_key in api_keys:
      try:
        client = Groq(
            api_key=api_key, base_url="https://groq-proxy.avichy65.workers.dev"
        )
        print(
            f"🤖 Connecting to Groq AI using {key_name} for {day_name},"
            f" {date_str}..."
        )

        market_summary = {
            t: f"Price: {d.get('price')}, Change: {d.get('change')}%"
            for t, d in market_data.items()
        }
        portfolio_tickers = list(portfolio_stocks.keys())

        headlines_formatted = (
            "\n".join([
                f"- Title: {h['title']} | Link: {h['link']}"
                for h in investing_headlines
            ])
            if investing_headlines
            else "No headlines available."
        )

        prompt = f"""
You are an elite Wall Street Chief Quantitative Strategist. Output a valid JSON object ONLY. 

CRITICAL SEPARATION MANDATE FOR US AND ISRAELI NEWS:
- US_MARKET_NEWS MUST focus strictly on US macroeconomic factors: Federal Reserve policy, US Treasury yields, Wall Street tech earnings, and US inflation data.
- IL_MARKET_NEWS MUST focus strictly on Israeli macroeconomic and geopolitical factors: Bank of Israel interest rate decisions, local security developments and geopolitical risk premiums affecting the market, USD/ILS exchange rate dynamics, and the Tel Aviv Stock Exchange.
- ABSOLUTELY NO sharing of sentences or phrases between US_MARKET_NEWS and IL_MARKET_NEWS. They must discuss completely different economic realities.

- Length: Each market analysis paragraph must be substantial, deep, quantitative, and written in fluent professional Hebrew.
- NO INTRODUCTORY LABELS: Never start any text with labels like "ניתוח ה-...", "השפעות על...", "המלצות:", "ניהול סיכונים:", או דומיהם. התחל מיד בכתיבת הניתוח המקצועי.
- IMPACT TAG MANDATE: In every news summary or macroeconomic analysis field, include a brief, concise indication of whether the impact is for the better or worse and why (e.g., "לרעה - בגלל חשש מעליית אינפלציה").

Today is {day_name}, Date: {date_str}.

Headlines from Investing.com:
{headlines_formatted}

Current Market Data:
{json.dumps(market_summary, ensure_ascii=False)}

User Portfolio Tickers: {portfolio_tickers}

Return a valid JSON object with exactly these keys:
1. SP500_ANALYSIS
2. NASDAQ_ANALYSIS
3. DOW_ANALYSIS
4. VIX_ANALYSIS
5. DXY_ANALYSIS
6. USD_ILS_EXPLANATION
7. OIL_EXPLANATION
8. GOLD_EXPLANATION
9. BTC_EXPLANATION
10. US_MARKET_NEWS
11. IL_MARKET_NEWS
12. MARKET_MOVERS_TABLE
13. CATALYST_EARNINGS
14. CATALYST_MONETARY
15. CATALYST_HARDWARE
16. COMMUNITY_SENTIMENT
17. ANALYST_POINT_1
18. ANALYST_POINT_2
19. RISK_MANAGEMENT_TEXT
20. ACTION_RECOMMENDATIONS_TEXT
21. long_term_stocks (array of EXACTLY 10 distinct individual corporate stocks with ticker, name, desc in Hebrew, news in Hebrew - STARTING DIRECTLY WITH THE TEXT WITHOUT "סיכום הכתבה:", why_invest in Hebrew - NO ETFS OR SECTORS)
22. swing_stocks (array of EXACTLY 10 distinct individual corporate stocks completely separate from long_term_stocks with ticker, name, desc in Hebrew, news in Hebrew - STARTING DIRECTLY WITH THE TEXT WITHOUT "סיכום הכתבה:", why_invest in Hebrew - NO ETFS OR SECTORS)
23. market_news (array of at least 10 items with news_link, news_title, news_desc in Hebrew starting with "סיכום הכתבה:")
"""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            max_tokens=8192,
        )

        raw_text = response.choices[0].message.content.strip()
        parsed_ai_data = json.loads(raw_text)
        parsed_ai_data["ai_updated_at"] = f"{date_str} | {time_str}"
        print("Successfully parsed AI response into JSON using key:", key_name)
        return parsed_ai_data

      except Exception as e:
        print(f"⚠️ Attempt failed with {key_name}: {e}")
        if (
            "429" in str(e)
            or "413" in str(e)
            or "RESOURCE_EXHAUSTED" in str(e)
            or "rate_limit_exceeded" in str(e)
        ):
          print(f"⏳ Rate limit or size limit hit on {key_name}. Waiting 65 seconds...")
          time.sleep(65)
        else:
          print("🔄 Connection error. Waiting 5 seconds...")
          time.sleep(5)

  print("⚠️ All AI retries exhausted. Falling back to cache.")
  cached = load_ai_cache()
  return cached if cached else {}


if __name__ == "__main__":
  print("🚀 Starting portfolio update script...")
  
  israel_tz = pytz.timezone("Asia/Jerusalem")
  now_il = datetime.now(israel_tz)
  date_str = now_il.strftime("%d/%m/%Y")
  time_str = now_il.strftime("%H:%M")
  
  days_hebrew = {
      "Sunday": "ראשון",
      "Monday": "שני",
      "Tuesday": "שלישי",
      "Wednesday": "רביעי",
      "Thursday": "חמישי",
      "Friday": "שישי",
      "Saturday": "שבת",
  }
  day_name = days_hebrew.get(now_il.strftime("%A"), now_il.strftime("%A"))

  portfolio_stocks = load_portfolio_buys()
  if not portfolio_stocks:
    portfolio_stocks = {"AAPL": {"shares": 10, "avg_price": 150.0}}

  market_tickers = [
      "^GSPC", "^NDX", "^DJI", "^VIX", "DX-Y.NYB", "CL=F", "GC=F", "BTC-USD", "USDILS=X",
      "XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLB", "XLC", "XLU", "XLRE"
  ]
  all_tickers = list(set(list(portfolio_stocks.keys()) + market_tickers))

  print("📊 Fetching market data...")
  market_data = fetch_market_data(all_tickers)

  print("📰 Fetching Investing.com news...")
  investing_headlines = fetch_investing_news()

  print("🤖 Generating AI insights...")
  ai_data = fetch_ai_insights_from_groq(
      market_data, portfolio_stocks, date_str, day_name, time_str, investing_headlines
  )

  if not ai_data:
    print("❌ AI data is empty! Using cache.")
    ai_data = load_ai_cache()

  save_ai_cache(ai_data)

  print("📝 Building HTML file from template...")
  if os.path.exists(TEMPLATE_FILE):
    with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
      template_content = f.read()

    # 1. החלפת מפתחות ה-AI
    for key, value in ai_data.items():
      if isinstance(value, str):
        formatted_val = format_ai_text(value)
        template_content = template_content.replace(f"{{{{{key}}}}}", formatted_val)

    # 2. החלפת מפתחות תאריך וזמן
    template_content = template_content.replace("{{DAY_NAME}}", day_name)
    template_content = template_content.replace("{{LAST_UPDATED}}", f"{date_str} | {time_str}")
    template_content = template_content.replace("{{AI_LAST_UPDATED}}", ai_data.get("ai_updated_at", f"{date_str} | {time_str}"))

    # 3. החלפת מפתחות מחירי שוק ושינויים
    market_mapping = {
        "OIL": "CL=F",
        "USD_ILS": "USDILS=X",
        "SP500": "^GSPC",
        "NASDAQ": "^NDX",
        "DOW": "^DJI",
        "BTC": "BTC-USD",
        "GOLD": "GC=F",
        "VIX": "^VIX",
        "DXY": "DX-Y.NYB",
    }

    for prefix, ticker in market_mapping.items():
      if ticker in market_data:
        p_val = format_num(market_data[ticker].get("price", 0))
        c_val = format_pct_colored(market_data[ticker].get("change", 0))
        template_content = template_content.replace(f"{{{{{prefix}_PRICE}}}}", p_val)
        template_content = template_content.replace(f"{{{{{prefix}_CHANGE}}}}", c_val)
        template_content = template_content.replace(f"{{{{{prefix}_PCT}}}}", c_val)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
      f.write(template_content)
    print("✅ Successfully generated index.html!")
  else:
    print(f"❌ Template file {TEMPLATE_FILE} not found!")
