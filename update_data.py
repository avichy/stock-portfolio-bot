import base64
from datetime import datetime
import json
import os
import re
import time
import traceback
import urllib.parse
import urllib.request
from bs4 import BeautifulSoup
import feedparser
from groq import Groq
import pytz
import requests

# וידוא שספריית yfinance קיימת
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

HEBREW_DAYS = {
    "Monday": "שני",
    "Tuesday": "שלישי",
    "Wednesday": "רביעי",
    "Thursday": "חמישי",
    "Friday": "שישי",
    "Saturday": "שבת",
    "Sunday": "ראשון",
}


def clean_json_response(text):
  """ניקוי תגיות Markdown לקבלת JSON תקין"""
  if not text:
    return "{}"
  text = text.strip()
  text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
  text = re.sub(r"\s*
