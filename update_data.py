import base64
import json
import os
import re
import time
import traceback
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
import feedparser
from bs4 import BeautifulSoup
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


portfolio_buys = load_portfolio_buys()


def fetch_us_market_news():
  """שליפת חדשות שוק אמריקאי עבור שלב 1 מ-Google News RSS"""
  try:
    query = "Wall Street stock market S&P 500 Nasdaq economy breaking news"
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"

    feed = feedparser.parse(url)
    news_items = []

    for entry in feed.entries[:6]:
      title = entry.get("title", "")
      summary = entry.get("summary", "")
      news_items.append(f"- {title}\n  תיאור: {summary}")

    return (
        "\n".join(news_items)
        if news_items
        else "No recent US market news available."
    )
  except Exception as e:
    print(f"Error fetching US news: {e}")
    return "Failed to fetch US market news."


def fetch_investing_news():
  """שליפת חדשות פיננסיות מ-Investing.com עם סינון מוקדם (Pre-processing)"""
  try:
    url = "https://www.investing.com/rss/news.rss"
    feed = feedparser.parse(url)
    raw_headlines = []
    seen_titles = set()

    for entry in feed.entries[:12]:
      title = entry.get("title", "").strip()
      summary = entry.get("summary", "") or entry.get("description", "")
      link = entry.get("link", "https://www.investing.com/")
      if title and len(title) > 5 and title not in seen_titles:
        seen_titles.add(title)
        raw_headlines.append({"title": title, "link": link, "summary": summary})

    return raw_headlines
  except Exception as e:
    print(f"Error fetching Investing news: {e}")
    return []


def fetch_bizportal_news():
  url = "https://www.bizportal.co.il/"
  headers = {
      "User-Agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML,"
          " like Gecko) Chrome/124.0.0.0 Safari/537.36"
      ),
      "Accept": (
          "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
      ),
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
      text = a_tag.get_text(strip=True)
      href = a_tag["href"]
      if len(text) > 25 and text not in seen_titles:
        if not any(
            w in text
            for w in [
                "התחבר",
                "הירשם",
                "פרסם אצלנו",
                "תנאי שימוש",
                "צור קשר",
                "חיפוש",
                "מערכת",
                "שירות לקוחות",
                "תפריט",
            ]
        ):
          if href.startswith("/"):
            link = f"https://www.bizportal.co.il{href}"
          elif not href.startswith("http"):
            link = f"https://www.bizportal.co.il/{href}"
          else:
            link = href

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


def force_source_on_newline(text):
  if not isinstance(text, str):
    return str(text)

  text = re.sub(r"(^|<br>)\s*;\s*", r"\1", text)
  text = re.sub(r"(^|<br>)\s*,\s*", r"\1", text)
  text = re.sub(
      r"<br>\s*(\(מקור\s*:[^)]+\))", r" \1", text, flags=re.IGNORECASE
  )
  text = re.sub(
      r"(\(מקור\s*:[^)]+\))(?!\s*<br\s*/?>)",
      r"\1<br>",
      text,
      flags=re.IGNORECASE,
  )

  return text


def format_text_with_conclusion(text, prefix_num=None):
  if isinstance(text, list):
    text = " ".join(str(item) for item in text)
  elif not isinstance(text, str):
    text = str(text)

  text = text.strip()
  text = text.replace("\\n", "<br>").replace("\n", "<br>")

  if text.startswith("[") and text.endswith("]"):
    try:
      parsed_list = json.loads(text)
      if isinstance(parsed_list, list):
        text = " ".join(str(item) for item in parsed_list)
    except Exception:
      pass

  source_match = re.search(r"(\(מקור\s*:[^)]+\))", text, re.IGNORECASE)
  source_str = source_match.group(1) if source_match else ""
  if source_str:
    text = text.replace(source_str, "").strip()

  cleaned = (
      text.replace("{", "")
      .replace("}", "")
      .replace("[", "")
      .replace("]", "")
      .replace('"', "")
      .replace("'", "")
  )

  cleaned = re.sub(
      r"^(?:ניהול\s*סיכונים|המלצות\s*פעולה|סיכונים|ניתוח\s+הסבר[^\n:]+|קָטָלִיסט[^\n:]*|השפעות[^\n:]*|סיכום הכתבה:?)\s*[:\-]?\s*",
      "",
      cleaned,
      flags=re.IGNORECASE,
  )
  cleaned = re.sub(
      r"מה\s*זה\s*אומר\s*[:\-]*", "", cleaned, flags=re.IGNORECASE
  ).strip()

  explanation = cleaned
  conclusion = ""

  if "לסיכום" in cleaned:
    parts = re.split(r"לסיכום\s*[:\-]*", cleaned, flags=re.IGNORECASE)
    explanation = parts[0].strip()
    if len(parts) > 1:
      conclusion = parts[1].strip()
      conclusion = re.sub(
          r"לסיכום\s*[:\-]*", "", conclusion, flags=re.IGNORECASE
      ).strip()

  explanation = re.sub(r"\s*<br>\s*", "<br>", explanation).strip()
  conclusion = re.sub(r"\s*<br>\s*", "<br>", conclusion).strip()

  explanation = re.sub(r"\s*\(?מקור:[^\)]+\)?", "", explanation)
  conclusion = re.sub(r"\s*\(?מקור:[^\)]+\)?", "", conclusion)

  sentences = [
      s.strip() for s in re.split(r"(?<=[.!?])\s+", explanation) if s.strip()
  ]

  if not conclusion:
    if len(sentences) > 2:
      conclusion = sentences[-1]
      explanation = " ".join(sentences[:-1])
    elif len(sentences) == 2:
      conclusion = sentences[1]
      explanation = sentences[0]
    else:
      conclusion = ""

  explanation = re.sub(
      r"לסיכום\s*[:\-]*", "", explanation, flags=re.IGNORECASE
  ).strip()
  conclusion = re.sub(
      r"^(|בנוסף|כמו כן|לפיכך|על כן|לכן)\s*[,:\-]*\s*", "", conclusion
  ).strip()

  conclusion = re.sub(r"\(מקור\s*:[^)]+\)", "", conclusion).strip()

  if prefix_num is not None:
    explanation = re.sub(r"^\d+[\.\)]\s*", "", explanation).strip()
    if not explanation:
      explanation = text.strip()
    explanation = f"{prefix_num}. {explanation}"

  if source_str:
    explanation = explanation.strip() + " " + source_str

  if conclusion:
    formatted_content = (
        f"{explanation}<br><br><strong>לסיכום:</strong><br>{conclusion}"
    )
  else:
    formatted_content = explanation

  formatted_content = format_numbers_in_text(formatted_content)
  formatted_content = force_source_on_newline(formatted_content)

  return (
      f'<span class="leading-relaxed text-sm text-gray-200 block'
      f' mt-1 mb-3" dir="rtl" style="text-align: right;">{formatted_content}</span>'
  )


def format_news_description(text):
  if isinstance(text, list):
    text = " ".join(str(item) for item in text)
  elif not isinstance(text, str):
    text = str(text)

  text = text.strip()
  text = text.replace("\\n", "<br>").replace("\n", "<br>")
  source_match = re.search(r"(\(מקור\s*:[^)]+\))", text, re.IGNORECASE)
  source_str = source_match.group(1) if source_match else ""
  if source_str:
    text = text.replace(source_str, "").strip()

  cleaned = (
      text.replace("{", "")
      .replace("}", "")
      .replace("[", "")
      .replace("]", "")
      .replace('"', "")
      .replace("'", "")
  )
  cleaned = re.sub(
      r"^(?:סיכום הכתבה:?|לסיכום:?)\s*[:\-]?\s*",
      "",
      cleaned,
      flags=re.IGNORECASE,
  ).strip()
  cleaned = re.sub(r"לסיכום.*$", "", cleaned, flags=re.IGNORECASE).strip()

  cleaned = format_numbers_in_text(cleaned)
  if source_str:
    cleaned = cleaned.strip() + " " + source_str

  return force_source_on_newline(cleaned)


def format_phase1_text(text):
  return format_text_with_conclusion(text)


def format_analyst_text(text):
  if not text or not str(text).strip() or str(text).strip() in ["''", '""']:
    text = "אין נתונים עדכניים זמינים כרגע מסקירת האנליסטים. לסיכום: מומלץ להמתין לעדכונים נוספים בשווקים."
  if "לסיכום" not in str(text):
    text = (
        str(text).strip()
        + " לסיכום: מומלץ לעקוב אחר התפתחות המגמות בשווקים."
    )
  return format_text_with_conclusion(text, prefix_num=None)


def get_stock_logo_url(ticker):
  clean_ticker = str(ticker).strip().upper()
  parqet_ticker = clean_ticker.replace("-", ".")
  return f"https://assets.parqet.com/logos/symbol/{parqet_ticker}"


LT_STOCKS_META = [
    {
        "ticker": "MSFT",
        "name": "Microsoft Corporation",
        "desc": "ענן Azure, תוכנה, פתרונות AI וטכנולוגיה עסקית גלובלית.",
        "news": "התרחבות עקבית בשירותי ענן ובינה מלאכותית ארגונית, יציבות פיננסית גבוהה.",
        "why_invest": "מובילה גלובלית עם תזרים מזומנים אדיר וביקושים קשיחים לשירותי ענן ובינה מלאכותית.",
    },
    {
        "ticker": "JPM",
        "name": "JPMorgan Chase & Co.",
        "desc": 'בנקאות מסחרית והשקעות מובילה בארה"ב ובעולם (סקטור הפיננסים).',
        "news": "תוצאות חזקות וניהול סיכונים קפדני תחת סביבת ריבית משתנה, עוגן חזק בתיק.",
        "why_invest": "ניהול פיננסי מעולה ומאזן חסון המייצרים תשואות עקביות בכל מצב שוק.",
    },
    {
        "ticker": "JNJ",
        "name": "Johnson & Johnson",
        "desc": "פיתוח תרופות, ציוד רפואי ומוצרי בריאות הצרכן (סקטור הבריאות).",
        "news": "חסינות עסקית גבוהה מול מחזוריות השוק, חלוקת דיבידנדים יציבה ואמינה.",
        "why_invest": "חברה דפנסיבית מובהקת עם פורטפוליו רפואי רחב והיסטוריית דיבידנדים מרשימה.",
    },
    {
        "ticker": "XOM",
        "name": "Exxon Mobil Corporation",
        "desc": "חיפוש, הפקה ואנרגיה קונבנציונלית ומתקדמת (סקטור האנרגיה).",
        "news": "תזרים מזומנים חזק ויעילות תפעולית גבוהה התומכת בתשואות אטרקטיביות למשקיעים.",
        "why_invest": "יעילות תפעולית גבוהה ותגמול נדיב למשקיעים באמצעות דיבידנדים ורכישות עצמיות.",
    },
    {
        "ticker": "WMT",
        "name": "Walmart Inc.",
        "desc": "רשת הקמעונאות והמרכולים הגדולה בעולם (סקטור צרכנות בסיסית).",
        "news": "ביקושים יציבים בכל תנאי מאקרו וצמיחה מרשימה בפעילות המסחר האלקטרוני.",
        "why_invest": "חסינות אינפלציונית מוכחת ונוכחות אלקטרונית מתרחב המבטיחים צמיחה יציבה.",
    },
]

SW_STOCKS_META = [
    {
        "ticker": "TSLA",
        "name": "Tesla, Inc.",
        "desc": "רכבים חשמליים, אנרגיה מתחדשת ופתרונות אוטונומיה (סקטור צרכנות מחזורית).",
        "news": "תנודתיות גבוהה המייצרת הזדמנויות מסחר יומי וסווינג עם מומנטום חזק.",
        "why_invest": "תנועות מחיר חדות המייצרות פוטנציאל רווח מהיר לסוחרים יומיים וסווינג.",
    },
    {
        "ticker": "AMD",
        "name": "Advanced Micro Devices",
        "desc": "פיתוח מעבדים, שבבים וכרטיסים גרפיים לשוק הטכנולוגיה.",
        "news": 'תנועות מחיר חדות סביב השקות מוצרים ודו"חות רבעוניים בסקטור השבבים.',
        "why_invest": "חשיפה ישירה לשוק השבבים וה-AI המייצרת מומנטום מסחר אטרקטיבי.",
    },
    {
        "ticker": "COIN",
        "name": "Coinbase Global, Inc.",
        "desc": "פלטפורמת מסחר מובילה בנכסים דיגיטליים וקריפטו (פיננסים/אלטרנטיבי).",
        "news": "קורלציה ישירה לתנודתיות בשוק הקריפטו, מעולה למסחר סווינג תנודתי קצר.",
        "why_invest": "תנודתיות גבוהה המונעת מנכסים דיגיטליים ומייצרת הזדמנויות רווח מהירות.",
    },
]


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

  return {
      "price": round(float(current_price or 100.0), 2),
      "change": round(float(change), 2),
      "target": 0.0,
      "pre_market": round(float(current_price or 100.0), 2),
  }


def fetch_market_data(tickers):
  market_data = {}
  for ticker in tickers:
    data = fetch_yahoo_direct(ticker)
    if data and data["price"] > 0:
      market_data[ticker] = data
  return market_data


def fetch_ai_insights_split(
    market_data,
    portfolio_stocks,
    date_str,
    day_name,
    us_market_news,
    investing_news_items,
    bizportal_headlines,
    now_il_str,
):
  api_keys = get_all_groq_keys()
  if not api_keys:
    print("❌ ERROR: No Groq API keys found! Using cached/defaults.")
    cached = load_ai_cache()
    return cached if cached else {}

  safe_bizportal_headlines = (
      bizportal_headlines[:8] if bizportal_headlines else []
  )
  market_summary = {
      t: f"Price: {d.get('price')}, Change: {d.get('change')}%"
      for t, d in market_data.items()
  }

  biz_formatted = (
      "\n".join(
          [
              f"- Title: {h['title']} | Source: {h.get('source', 'Bizportal')} | Link: {h['link']}"
              for h in safe_bizportal_headlines
          ]
      )
      if safe_bizportal_headlines
      else "No Israeli headlines."
  )

  combined_result = load_ai_cache()
  if not isinstance(combined_result, dict):
    combined_result = {}

  print(
      "🔄 Starting Groq AI Analysis with Data Isolation & Deterministic"
      " Settings..."
  )

  raw_headlines = [item["title"] for item in investing_news_items]

  for key_name, api_key in api_keys:
    try:
      client = Groq(
          api_key=api_key,
          base_url="https://groq-proxy.avichy65.workers.dev",
      )
      print(f"🤖 Connecting to Groq AI using {key_name} (openai/gpt-oss-120b)...")

      prompt = f"""
אתה אנליסט פיננסי דטרמיניסטי. נתח אך ורק את הכותרות הבאות.
חוקים נוקשים:
- אסור להמציא מספרים או נתונים שלא קיימים במקור.
- אם אינו בטוח בהקשר, התעלם מהידיעה לחלוטין.
- החזר אובייקט JSON חוקי בלבד המכיל את המפתחות הנדרשים: market_news, US_MARKET_NEWS, IL_MARKET_NEWS, long_term_stocks, swing_stocks, SP500_ANALYSIS, NASDAQ_ANALYSIS, DOW_ANALYSIS, VIX_ANALYSIS, DXY_ANALYSIS, USD_ILS_EXPLANATION, OIL_EXPLANATION, GOLD_EXPLANATION, BTC_EXPLANATION, COMMUNITY_SENTIMENT, ANALYST_POINT_1, ANALYST_POINT_2, CATALYST_EARNINGS, CATALYST_MONETARY, CATALYST_HARDWARE, RISK_MANAGEMENT_TEXT, ACTION_RECOMMENDATIONS_TEXT.

<us_headlines>
{json.dumps(raw_headlines, ensure_ascii=False)}
</us_headlines>

<bizportal_headlines>
{biz_formatted}
</bizportal_headlines>

Today is {day_name}, Date: {date_str}.
"""

      response = client.chat.completions.create(
          model="openai/gpt-oss-120b",
          messages=[{"role": "user", "content": prompt}],
          response_format={"type": "json_object"},
          temperature=0,
          max_tokens=4000,
      )

      raw_text = response.choices[0].message.content.strip()
      parsed = json.loads(raw_text)
      combined_result.update(parsed)
      print("Successfully parsed AI JSON response with temperature=0.")
      break
    except Exception as e:
      print(f"⚠️ AI attempt failed with {key_name}: {e}")
      if "429" in str(e) or "rate_limit_exceeded" in str(e):
        print("⏳ Rate limit hit. Waiting 60 seconds...")
        time.sleep(60)
      else:
        time.sleep(5)

  combined_result["ai_updated_at"] = now_il_str
  return combined_result


israel_tz = pytz.timezone("Asia/Jerusalem")
now_il = datetime.now(israel_tz)
date_str = now_il.strftime("%d.%m.%Y")
time_str = now_il.strftime("%H:%M")
now_il_str = f"{date_str} | {time_str}"

day_name = {
    0: "שני",
    1: "שלישי",
    2: "רביעי",
    3: "חמישי",
    4: "שישי",
    5: "שבת",
    6: "ראשון",
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
    "REAL_ESTATE": "XLRE",
}

forbidden_stock_tickers = set(sector_tickers_map.values()).union({
    "^GSPC",
    "^NDX",
    "^DJI",
    "^VIX",
    "DX-Y.NYB",
    "CL=F",
    "GC=F",
    "BTC-USD",
    "USDILS=X",
    "SPY",
    "QQQ",
})


def clean_stocks_list(stocks_list, default_meta):
  if not isinstance(stocks_list, list) or not stocks_list:
    return default_meta
  cleaned = []
  for s in stocks_list:
    if isinstance(s, dict):
      t = str(s.get("ticker") or s.get("symbol") or "").strip().upper()
      if t and t not in forbidden_stock_tickers:
        cleaned.append({
            "ticker": t,
            "name": s.get("name") or s.get("company") or t,
            "desc": s.get("desc") or f"חברה מובילה ({t}).",
            "news": s.get("news") or "מעקב שוטף.",
            "why_invest": s.get("why_invest") or "פוטנציאל תשואה חיובי.",
        })
  return cleaned if len(cleaned) >= 3 else default_meta


cached_ai_init = load_ai_cache()
init_lt = clean_stocks_list(
    cached_ai_init.get("long_term_stocks", LT_STOCKS_META), LT_STOCKS_META
)
init_sw = clean_stocks_list(
    cached_ai_init.get("swing_stocks", SW_STOCKS_META), SW_STOCKS_META
)

base_market_tickers = list(
    set(
        [
            "GC=F",
            "CL=F",
            "BTC-USD",
            "USDILS=X",
            "DX-Y.NYB",
            "^GSPC",
            "^NDX",
            "^DJI",
            "^VIX",
        ]
        + list(sector_tickers_map.values())
        + list(portfolio_buys.keys())
    )
)


def build_structured_stocks_html(stocks_meta, market_data, section_title):
  html_parts = [
      f'<div class="text-lg font-bold text-cyan-400 mb-4 mt-2 text-right"'
      f' dir="rtl" style="text-align: right;">{section_title}</div>'
  ]
  if not isinstance(stocks_meta, list):
    stocks_meta = LT_STOCKS_META

  for s in stocks_meta:
    if not isinstance(s, dict):
      continue
    ticker = str(s.get("ticker") or "").strip().upper()
    if not ticker or ticker in forbidden_stock_tickers:
      continue
    name = s.get("name") or ticker
    desc = s.get("desc") or ""
    news = s.get("news") or ""
    why_invest = s.get("why_invest") or ""

    data = market_data.get(ticker, {})
    price = format_num(data.get("price", 0))
    change_val = data.get("change", 0.0)
    change_str = format_pct_colored(change_val)
    logo_url = get_stock_logo_url(ticker)

    card_html = f"""
        <div class="bg-gray-800/80 border border-gray-700/60 rounded-xl p-4 mb-4 shadow-md text-right overflow-hidden" dir="rtl" style="text-align: right;">
            <div class="flex items-center gap-3 mb-3" style="text-align: right;">
                <img src="{logo_url}" width="28" height="28" class="rounded-full bg-white p-0.5 object-contain" alt="{ticker}">
                <span class="text-base font-bold text-white" style="text-align: right;">{name} (טיקר: {ticker}):</span>
            </div>
            <div class="text-sm text-gray-300 space-y-1 break-words" style="text-align: right;">
                <div style="text-align: right;"><strong>מחיר נוכחי:</strong> ${price}</div>
                <div style="text-align: right;"><strong>שינוי יומי:</strong> {change_str}</div>
                <div style="text-align: right;"><strong>עיסוק החברה:</strong> {desc}</div>
                <div style="text-align: right;"><strong>חדשות ורציונל יומי:</strong> {news}</div>
                <div style="text-align: right;"><strong>למה כדאי להשקיע:</strong> {why_invest}</div>
            </div>
        </div>
        """
    html_parts.append(card_html)
  return "".join(html_parts)


def build_market_news_html(market_news_list):
  if not isinstance(market_news_list, list) or not market_news_list:
    return (
        '<div class="text-gray-400 text-right" dir="rtl"'
        ' style="text-align: right;">אין חדשות שוק זמינות כרגע.</div>'
    )

  html_parts = []
  for item in market_news_list:
    if not isinstance(item, dict):
      continue
    p_link = item.get("news_link") or item.get("link") or "#"
    p_title = item.get("news_title") or item.get("title") or "עדכון שוק"
    p_desc = item.get("news_desc") or item.get("description") or ""

    card_html = f"""
        <div class="bg-gray-800 p-4 rounded-xl border border-gray-700 shadow space-y-2 text-sm text-gray-300 text-right overflow-hidden" dir="rtl" style="text-align: right;">
            <h3 class="text-cyan-400 font-semibold text-base break-words" style="text-align: right;">{p_title}</h3>
            <p class="mt-1 break-words" style="text-align: right;">קישור 🔗: <a href="{p_link}" target="_blank" class="text-cyan-400 hover:underline">{p_link}</a></p>
            <p class="mt-2 break-words" style="text-align: right;"><strong>סיכום:</strong><br>{format_news_description(p_desc)}</p>
        </div>
        """
    html_parts.append(card_html)
  return "".join(html_parts)


if __name__ == "__main__":
  try:
    print("Fetching initial market data...")
    base_market_data = fetch_market_data(base_market_tickers)

    us_market_news = fetch_us_market_news()
    investing_news_items = fetch_investing_news()
    bizportal_headlines = fetch_bizportal_news()

    try:
      ai_insights = fetch_ai_insights_split(
          base_market_data,
          portfolio_buys,
          date_str,
          day_name,
          us_market_news,
          investing_news_items,
          bizportal_headlines,
          now_il_str,
      )
      if ai_insights and isinstance(ai_insights, dict) and len(ai_insights) > 3:
        save_ai_cache(ai_insights)
    except Exception as e:
      print(f"Error handling AI insights: {e}")
      ai_insights = load_ai_cache()

    us_news_text = ai_insights.get("US_MARKET_NEWS", "")
    if isinstance(us_news_text, list):
      us_news_text = " ".join(str(item) for item in us_news_text)

    if "(מקור:" not in str(us_news_text):
      us_news_text = str(us_news_text).strip() + " (מקור: Google News RSS)"
    ai_insights["US_MARKET_NEWS"] = us_news_text

    il_news_text = ai_insights.get("IL_MARKET_NEWS", "")
    if isinstance(il_news_text, list):
      il_news_text = " ".join(str(item) for item in il_news_text)

    if "(מקור:" not in str(il_news_text):
      il_news_text = str(il_news_text).strip() + " (מקור: Bizportal)"
    ai_insights["IL_MARKET_NEWS"] = il_news_text

    # --- יצירת קובץ ה-HTML מתוך ה-Template ---
    if os.path.exists(TEMPLATE_FILE):
      with open(TEMPLATE_FILE, "r", encoding="utf-8") as tf:
        template_content = tf.read()

      # 1. החלפת משתני תאריך וימים
      template_content = template_content.replace("{{DAY_NAME}}", day_name)
      template_content = template_content.replace(
          "{{AI_LAST_UPDATED}}", ai_insights.get("ai_updated_at", now_il_str)
      )
      template_content = template_content.replace(
          "{{LAST_UPDATED}}", now_il_str
      )

      # 2. החלפת מחירי השוק והשינויים האחוזים
      market_mappings = {
          "GC=F": ("GOLD_PRICE", "GOLD_CHANGE"),
          "CL=F": ("OIL_PRICE", "OIL_CHANGE"),
          "BTC-USD": ("BTC_PRICE", "BTC_CHANGE"),
          "USDILS=X": ("USD_ILS", "USD_ILS_CHANGE"),
          "^GSPC": ("SP500_PRICE", "SP500_PCT"),
          "^NDX": ("NASDAQ_PRICE", "NASDAQ_PCT"),
          "^DJI": ("DOW_PRICE", "DOW_PCT"),
          "^VIX": ("VIX_PRICE", "VIX_PCT"),
          "DX-Y.NYB": ("DXY_PRICE", "DXY_PCT"),
      }

      for ticker, (price_key, change_key) in market_mappings.items():
        d = base_market_data.get(ticker, {})
        p_str = format_num(d.get("price", 0))
        c_str = format_pct_colored(d.get("change", 0))
        template_content = template_content.replace(
            f"{{{{{price_key}}}}}", p_str
        )
        template_content = template_content.replace(
            f"{{{{{change_key}}}}}", c_str
        )
        # תמיכה בשמות חלופיים תואמים לטמפלייט
        template_content = template_content.replace(
            f"{{{{{price_key.replace('_PRICE', '_CHANGE')}}}}}", c_str
        )
        template_content = template_content.replace(
            f"{{{{{price_key.replace('_PRICE', '_PCT')}}}}}", c_str
        )

      # 3. החלפת מניות מבניות וחדשות שוק
      lt_stocks = clean_stocks_list(
          ai_insights.get("long_term_stocks", LT_STOCKS_META),
          LT_STOCKS_META,
      )
      sw_stocks = clean_stocks_list(
          ai_insights.get("swing_stocks", SW_STOCKS_META), SW_STOCKS_META
      )

      lt_html = build_structured_stocks_html(
          lt_stocks, base_market_data, "מניות לטווח ארוך"
      )
      sw_html = build_structured_stocks_html(
          sw_stocks, base_market_data, "מניות לסווינג"
      )
      market_news_html = build_market_news_html(
          ai_insights.get("market_news", [])
      )

      template_content = template_content.replace(
          "{{US_MARKET_NEWS}}", format_phase1_text(us_news_text)
      )
      template_content = template_content.replace(
          "{{IL_MARKET_NEWS}}", format_phase1_text(il_news_text)
      )
      template_content = template_content.replace(
          "{{LONG_TERM_STOCKS}}", lt_html
      )
      template_content = template_content.replace(
          "{{SWING_STOCKS}}", sw_html
      )
      template_content = template_content.replace(
          "{{MARKET_NEWS}}", market_news_html
      )

      # 4. החלפת שאר תגי ה-AI הדינמיים
      for k, v in ai_insights.items():
        if isinstance(v, str):
          template_content = template_content.replace(
              f"{{{{{k}}}}}", format_phase1_text(v)
          )

      with open(OUTPUT_FILE, "w", encoding="utf-8") as of:
        of.write(template_content)
      print("Successfully generated index.html from template with prices!")
    else:
      print("Warning: index.template.html not found, skipped HTML generation.")

    print("Dashboard generation completed successfully.")

  except Exception as e:
    print(f"❌ Critical Error: {e}")
    traceback.print_exc()
    exit(1)
