import base64
from datetime import datetime
import json
import os
import re
import time
import traceback
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import feedparser
from groq import Groq
import pytz
import requests

# וידוא שספריית yfinance קיימת (מותקנת אוטומטית במידת הצורך ב-GitHub Actions)
try:
  import yfinance as yf
except ImportError:
  os.system("pip install yfinance")
  import yfinance as yf

AI_CACHE_FILE = "ai_cache.json"
PORTFOLIO_FILE = "portfolio.json"
TEMPLATE_FILE = "index.template.html"
OUTPUT_FILE = "index.html"

GITHUB_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")


def clean_json_response(text):
  """ניקוי תגיות Markdown מתגובת AI לקבלת מחרוזת JSON תקינה"""
  if not text:
    return "{}"
  text = text.strip()
  text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
  text = re.sub(r"\s*```$", "", text)
  return text.strip()


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
      response = requests.get(url, headers=headers, timeout=10)
      if response.status_code == 200:
        file_data = response.json()
        raw_content = file_data.get("content", "").replace("\n", "").strip()
        missing_padding = len(raw_content) % 4
        if missing_padding:
          raw_content += "=" * (4 - missing_padding)
        content = base64.b64decode(raw_content.encode("utf-8")).decode("utf-8")
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
  """שליפת חדשות שוק אמריקאי מ-Google News RSS עם קישורים ומבנה מסודר"""
  try:
    query = (
        "Wall Street stock market S&P 500 Nasdaq economy breaking news Fed"
    )
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-US&gl=US&ceid=US:en"

    feed = feedparser.parse(url)
    news_items = []

    for entry in feed.entries[:10]:
      title = entry.get("title", "")
      summary = entry.get("summary", "")
      link = entry.get("link", "https://news.google.com")
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
  """סינון חכם לחדשות ארה\"ב - מתן עדיפות למאקרו, פד, גיאופוליטיקה ואירועי שוק"""
  us_market
