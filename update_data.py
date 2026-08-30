from datetime import datetime
import json
import os
import re
import time
import traceback
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import base64
from bs4 import BeautifulSoup
import feedparser
from groq import Groq
import pytz
import requests

try:
  import yfinance as yf
except ImportError:
  os.system("pip install yfinance")
  import yfinance as yf

AI_CACHE_FILE = "ai_cache.json"
PORTFOLIO_FILE = "portfolio.json"
TEMPLATE_FILE = "index.template.html"
OUTPUT_FILE = "index.html"

# הגדרת ברירת מחדל למניות למניעת שגיאות NameError
LT_STOCKS_META = [
    {
        "ticker": "AAPL",
        "name": "Apple",
        "desc": "חברת טכנולוגיה מובילה.",
        "news": "מעקב שוטף אחרי מוצרי החברה.",
        "why_invest": "יציבות עסקית ותזרים מזומנים חזק."
    },
    {
        "ticker": "MSFT",
        "name": "Microsoft",
        "desc": "מובילת ענן ותוכנה עולמית.",
        "news": "התרחבות בתחומי ענן ובינה מלאכותית.",
        "why_invest": "מובילות טכנולוגית לטווח ארוך."
    }
]

SW_STOCKS_META = [
    {
        "ticker": "NVDA",
        "name": "NVIDIA",
        "desc": "יצרנית שבבים מובילה.",
        "news": "ביקוש גבוה לפתרונות AI.",
        "why_invest": "מומנטום חזק בשוק הסמיקונדקטורס."
    }
]

if not os.path.exists(TEMPLATE_FILE):
  with open(TEMPLATE_FILE, "w", encoding="utf-8") as f:
    f.write("""<!DOCTYPE html>
<html lang="he" dir="rtl">
<head><meta charset="UTF-8"><title>לוח בקרה פיננסי</title></head>
<body class="bg-gray-900 text-white p-6">
    <div class="max-w-7xl mx-auto">
        <h1 class="text-3xl font-bold text-cyan-400 mb-4">לוח בקרה פיננסי</h1>
        <div>עודכן לאחרונה: {{LAST_UPDATED}}</div>
        <div>{{SP500_PRICE}} | {{SP500_PCT}}</div>
        <div>{{LONG_TERM_STOCKS_SECTION}}</div>
        <div>{{SWING_STOCKS_SECTION}}</div>
        <div>{{PORTFOLIO_NEWS_SECTION}}</div>
    </div>
</body>
</html>""")

if not os.path.exists(PORTFOLIO_FILE):
  with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
    json.dump({"AAPL": {"shares": 10, "buy": 180.0}}, f, ensure_ascii=False, indent=4)

GITHUB_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")
if GITHUB_REPO:
  GITHUB_REPO = GITHUB_REPO.replace("https://github.com/", "").replace("http://github.com/", "").strip("/")
  if GITHUB_REPO.endswith(".git"):
    GITHUB_REPO = GITHUB_REPO[:-4]


def clean_text(text):
  if not text:
    return ""
  if not isinstance(text, str):
    text = str(text)
  return text


def parse_json_safely(raw_text):
  if not raw_text:
    return {}
  text = raw_text.strip()
  if text.startswith("```"):
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
  try:
    return json.loads(text)
  except Exception:
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
      try:
        return json.loads(match.group(0))
      except Exception:
        pass
    return {}


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
        data = json.load(f)
        if isinstance(data, dict):
          return {k: (clean_text(v) if isinstance(v, str) else v) for k, v in data.items()}
        return data
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
      url = f"[https://api.github.com/repos/](https://api.github.com/repos/){GITHUB_REPO}/contents/{PORTFOLIO_FILE}"
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


portfolio_buys = load_portfolio_buys()


def fetch_us_market_news():
  try:
    query = "Wall Street stock market S&P 500 Nasdaq economy breaking news Fed geopolitical"
    encoded_query = urllib.parse.quote_plus(query)
    url = f"[https://news.google.com/rss/search?q=](https://news.google.com/rss/search?q=){encoded_query}&hl=en-US&gl=US&ceid=US:en"

    feed = feedparser.parse(url)
    news_items = []

    for entry in feed.entries[:10]:
      title = clean_text(entry.get("title", ""))
      summary = clean_text(entry.get("summary", ""))
      link = entry.get("link", "[https://news.google.com](https://news.google.com)")
      if title:
        news_items.append({
            "title": title,
            "summary": summary,
            "link": link,
            "source": "Google News RSS",
        })

    return news_items
  except Exception as e:
    print(f"Error fetching US news: {e}")
    return []


def get_filtered_us_news(headlines):
  us_market_drivers = [
      "Fed", "הפד", "Powell", "פאוול", "inflation", "אינפלציה", "CPI",
      "interest rate", "ריבית", "employment", "תעסוקה", "GDP", "oil", "נפט",
      "geopolitical", "מתיחות", "tariff", "מכסים", "trade war", "סנקציות",
      "S&P 500", "Nasdaq", "נאסדק", "Dow", "דאו", "Wall Street", "וול סטריט", "earnings", "דוחות"
  ]
  filtered = []
  for h in headlines:
    title = h.get("title", "")
    if any(driver.lower() in title.lower() for driver in us_market_drivers):
      filtered.append(h)
  return filtered[:3] if filtered else headlines[:3]


def get_filtered_israel_news(headlines):
  local_mandatory = [
      "ישראל", "תל אביב", 'ת"א', "הבורסה", "בנק ישראל", "שקל", "נגיד",
      "אמיר ירון", "רשות ניירות ערך", "דיסקונט", "פועלים", "לאומי",
      "מזרחי", "אלביט", "טבע", "נייס", "קמטק", "אינפלציה בישראל"
  ]
  filtered = []
  for h in headlines:
    title = h.get("title", "")
    if any(f in title for f in ["וול סטריט", "הפד", "פאוול", "נאסדק", "S&P"]) and not any(l in title for l in ["ישראל", "תל אביב", 'ת"א', "הבורסה"]):
      continue
    if any(l in title for l in local_mandatory):
      filtered.append(h)
  return filtered[:3] if filtered else [h for h in headlines if not any(x in h.get("title", "") for x in ["וול סטריט", "הפד", "וולסטריט"])][:3]


def fetch_investing_news():
  try:
    rss_urls = [
        "[https://il.investing.com/rss/news.rss](https://il.investing.com/rss/news.rss)",
        "[https://www.investing.com/rss/news.rss](https://www.investing.com/rss/news.rss)",
        "[https://www.investing.com/rss/stock_market.rss](https://www.investing.com/rss/stock_market.rss)",
    ]
    news_items = []
    seen_titles = set()

    for url in rss_urls:
      feed = feedparser.parse(url)
      for entry in feed.entries[:10]:
        title = clean_text(entry.get("title", ""))
        summary = clean_text(entry.get("summary", "") or entry.get("description", ""))
        link = entry.get("link", "[https://il.investing.com/](https://il.investing.com/)")
        if title and title not in seen_titles:
          seen_titles.add(title)
          news_items.append(f"- כותרת: {title}\n  קישור: {link}\n  תיאור: {summary}")

    return "\n".join(news_items[:12]) if news_items else "No recent Investing.com news available."
  except Exception as e:
    print(f"Error fetching Investing news: {e}")
    return "Failed to fetch Investing news."


def fetch_bizportal_news():
  url = "[https://www.bizportal.co.il/](https://www.bizportal.co.il/)"
  headers = {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
      "Accept-Language": "he-IL,he;q=0.9,en-US;q=0.8,en;q=0.7",
  }
  try:
    response = requests.get(url, headers=headers, timeout=10)
    if response.status_code != 200:
      return []

    soup = BeautifulSoup(response.text, "html.parser")
    news_items = []
    seen_titles = set()

    for a_tag in soup.find_all("a", href=True):
      text = clean_text(a_tag.get_text(strip=True))
      href = a_tag["href"]
      if len(text) > 25 and text not in seen_titles:
        if not any(w in text for w in ["התחבר", "הירשם", "פרסם אצלנו", "תנאי שימוש", "צור קשר", "חיפוש", "מערכת", "שירות לקוחות", "תפריט"]):
          if href.startswith("http"):
            link = href
          elif href.startswith("/"):
            link = f"[https://www.bizportal.co.il](https://www.bizportal.co.il){href}"
          else:
            link = f"[https://www.bizportal.co.il/](https://www.bizportal.co.il/){href}"

          seen_titles.add(text)
          news_items.append({"title": text, "link": link, "source": "Bizportal"})
    return news_items[:15]
  except Exception as e:
    print(f"Warning: Error fetching Bizportal: {e}")
    return []


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
    return f'<span dir="ltr" style="color: {color}; font-weight: bold; display: inline-block;">{sign}{num:.2f}%</span>'
  except (ValueError, TypeError):
    return str(val)


def fetch_yahoo_direct(ticker):
  clean_ticker = str(ticker).strip().upper()
  try:
    t = yf.Ticker(clean_ticker)
    current_price = None
    prev_close = None
    try:
      current_price = t.fast_info.get('lastPrice')
    except Exception:
      pass
    try:
      prev_close = t.fast_info.get('previousClose')
    except Exception:
      pass

    info = {}
    try:
      info = t.info
    except Exception:
      pass

    if not current_price:
      current_price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose", 0.0)
    if not prev_close:
      prev_close = info.get("previousClose") or current_price

    if current_price and prev_close and prev_close > 0:
      change = ((current_price - prev_close) / prev_close) * 100
    else:
      change = 0.0

    target_mean = info.get("targetMeanPrice", 0.0) or 0.0

    if current_price and current_price > 0:
      return {
          "price": round(float(current_price), 2),
          "change": round(float(change), 2),
          "target": float(target_mean) if target_mean else 0.0,
      }
  except Exception as e:
    print(f"yfinance fetch error for {clean_ticker}: {e}")
  return None


def fetch_market_data(tickers):
  market_data = {}
  for ticker in tickers:
    data = fetch_yahoo_direct(ticker)
    if data and data["price"] > 0:
      market_data[ticker] = data
    else:
      market_data[ticker] = {"price": 100.0, "change": 0.0, "target": 0.0}
  return market_data


def fetch_ai_insights_split(market_data, portfolio_stocks, date_str, day_name, us_market_news_text, investing_news, bizportal_headlines_text, now_il_str):
  api_keys = get_all_groq_keys()
  if not api_keys:
    print("⚠️ No Groq API keys found! Using cached/defaults.")
    return load_ai_cache()

  market_summary = {
      t: f"Price: {d.get('price')}, Change: {d.get('change')}%, Analyst Target: {d.get('target', 0)}"
      for t, d in market_data.items()
  }

  combined_result = load_ai_cache()
  if not isinstance(combined_result, dict):
    combined_result = {}

  SYSTEM_PROMPT = "אתה אנליסט פיננסי בכיר. כתוב בעברית מקצועית בלבד והחזר אך ורק מבנה JSON תקין."

  for key_name, api_key in api_keys:
    try:
      client = Groq(api_key=api_key, base_url="[https://groq-proxy.avichy65.workers.dev](https://groq-proxy.avichy65.workers.dev)")
      prompt = f"""
{SYSTEM_PROMPT}
Today is {day_name}, Date: {date_str}.
Market Data: {json.dumps(market_summary, ensure_ascii=False)}

Return a valid JSON object with keys:
SP500_ANALYSIS, NASDAQ_ANALYSIS, DOW_ANALYSIS, VIX_ANALYSIS, DXY_ANALYSIS, USD_ILS_EXPLANATION, OIL_EXPLANATION, GOLD_EXPLANATION, BTC_EXPLANATION, US_MARKET_NEWS, IL_MARKET_NEWS, COMMUNITY_SENTIMENT, ANALYST_POINT_1, ANALYST_POINT_2, long_term_stocks, swing_stocks, market_news, CATALYST_EARNINGS, CATALYST_MONETARY, CATALYST_HARDWARE, RISK_MANAGEMENT_TEXT, ACTION_RECOMMENDATIONS_TEXT.
"""
      response = client.chat.completions.create(
          model="openai/gpt-oss-120b",
          messages=[{"role": "user", "content": prompt}],
          response_format={"type": "json_object"},
          temperature=0.3,
          max_tokens=4000,
      )
      parsed = parse_json_safely(response.choices[0].message.content.strip())
      if parsed:
        combined_result.update(parsed)
        break
    except Exception as e:
      print(f"⚠️ Groq attempt failed with {key_name}: {e}")
      time.sleep(2)

  combined_result["ai_updated_at"] = now_il_str
  return combined_result


israel_tz = pytz.timezone("Asia/Jerusalem")
now_il = datetime.now(israel_tz)
date_str = now_il.strftime("%d.%m.%Y")
time_str = now_il.strftime("%H:%M")
now_il_str = f"{date_str} | {time_str}"

day_name = {0: "שני", 1: "שלישי", 2: "רביעי", 3: "חמישי", 4: "שישי", 5: "שבת", 6: "ראשון"}[now_il.weekday()]

sector_tickers_map = {
    "INFO_TECH": "XLK", "FINANCIALS": "XLF", "HEALTH": "XLV",
    "CONS_DISC": "XLY", "CONS_STAPLES": "XLP", "ENERGY": "XLE",
    "INDUSTRIALS": "XLI", "MATERIALS": "XLB", "COMM": "XLC",
    "UTILITIES": "XLU", "REAL_ESTATE": "XLRE"
}

forbidden_stock_tickers = set(sector_tickers_map.values()).union({
    "^GSPC", "^NDX", "^DJI", "^VIX", "DX-Y.NYB", "CL=F", "GC=F", "BTC-USD", "USDILS=X", "SPY", "QQQ"
})

def clean_stocks_list(stocks_list, default_meta):
  if not isinstance(stocks_list, list) or not stocks_list:
    return default_meta
  cleaned = []
  for s in stocks_list:
    if isinstance(s, dict):
      t = clean_text(str(s.get("ticker") or s.get("symbol") or "")).strip().upper()
      if t and t not in forbidden_stock_tickers:
        cleaned.append({
            "ticker": t,
            "name": clean_text(s.get("name") or s.get("company") or t),
            "desc": clean_text(s.get("desc") or f"חברה מובילה ({t})."),
            "news": clean_text(s.get("news") or "מעקב שוטף."),
            "why_invest": clean_text(s.get("why_invest") or "פוטנציאל תשואה חיובי."),
        })
  return cleaned if cleaned else default_meta


if __name__ == "__main__":
  try:
    print("Fetching initial market data...")
    base_market_tickers = list(set(["GC=F", "CL=F", "BTC-USD", "USDILS=X", "DX-Y.NYB", "^GSPC", "^NDX", "^DJI", "^VIX"] + list(sector_tickers_map.values()) + list(portfolio_buys.keys())))
    base_market_data = fetch_market_data(base_market_tickers)

    us_news_raw = fetch_us_market_news()
    safe_us_headlines = get_filtered_us_news(us_news_raw)
    us_market_news_text = "\n".join([f"- {h['title']}" for h in safe_us_headlines]) if safe_us_headlines else ""

    investing_news = fetch_investing_news()
    bizportal_raw = fetch_bizportal_news()
    safe_il_headlines = get_filtered_israel_news(bizportal_raw)
    bizportal_headlines_text = "\n".join([f"- {h['title']}" for h in safe_il_headlines]) if safe_il_headlines else ""

    ai_insights = fetch_ai_insights_split(
        base_market_data, portfolio_buys, date_str, day_name,
        us_market_news_text, investing_news, bizportal_headlines_text, now_il_str
    )
    if ai_insights and isinstance(ai_insights, dict):
      save_ai_cache(ai_insights)

    new_lt = clean_stocks_list(ai_insights.get("long_term_stocks", LT_STOCKS_META), LT_STOCKS_META)
    new_sw = clean_stocks_list(ai_insights.get("swing_stocks", SW_STOCKS_META), SW_STOCKS_META)

    with open(TEMPLATE_FILE, "r", encoding="utf-8-sig") as f:
      content = f.read()

    replacements = {
        "LAST_UPDATED": now_il_str,
        "SP500_PRICE": format_num(base_market_data.get("^GSPC", {}).get("price", 0)),
        "SP500_PCT": format_pct_colored(base_market_data.get("^GSPC", {}).get("change", 0)),
        "LONG_TERM_STOCKS_SECTION": "<div>קבוצת מניות ארוכות טווח מעודכנות</div>",
        "SWING_STOCKS_SECTION": "<div>קבוצת מניות סווינג מעודכנות</div>",
        "PORTFOLIO_NEWS_SECTION": "<div>חדשות שוק מעודכנות</div>",
    }

    for k, v in replacements.items():
      content = content.replace("{{" + k + "}}", str(v))

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
      f.write(content)

    print(f"Successfully generated {OUTPUT_FILE}!")

  except Exception as e:
    print(f"❌ Critical Error in main execution: {e}")
    traceback.print_exc()
    exit(1)
