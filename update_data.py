import base64
import json
import os
import requests

GITHUB_TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get(
    "GITHUB_REPO"
)  # לדוגמה: "username/stock-portfolio-bot"
PORTFOLIO_FILE = "portfolio.json"


def load_portfolio_buys():
  # ניסיון טעינה ישירות מ-GitHub API כדי לקבל תמיד את המידע המעודכן ביותר
  if GITHUB_TOKEN and GITHUB_REPO:
    try:
      url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{PORTFOLIO_FILE}"
      headers = {"Authorization": f"token {GITHUB_TOKEN}"}
      response = requests.get(url, headers=headers)
      if response.status_code == 200:
        file_data = response.json()
        content = base64.b64decode(file_data["content"]).decode("utf-8")
        return json.loads(content)
    except Exception as e:
      print(f"Error loading from GitHub API: {e}")

  # גיבוי מקומי למקרה הרצה מקומית
  if os.path.exists(PORTFOLIO_FILE):
    try:
      with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
    except Exception as e:
      print(f"Error loading local portfolio.json: {e}")
  return {}


def save_portfolio_buys(data):
  # שמירה מקומית
  try:
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
      json.dump(data, f, ensure_ascii=False, indent=2)
  except Exception as e:
    print(f"Error saving local portfolio.json: {e}")

  # עדכון אוטומטי ב-GitHub דרך API (מה שמעדכן את הריפוזיטורי ומפעיל את ה-Action)
  if GITHUB_TOKEN and GITHUB_REPO:
    try:
      url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{PORTFOLIO_FILE}"
      headers = {"Authorization": f"token {GITHUB_TOKEN}"}

      # שליפת ה-SHA הנוכחי של הקובץ (חובה בשביל לעדכן קובץ בגיטהאב)
      get_res = requests.get(url, headers=headers)
      sha = None
      if get_res.status_code == 200:
        sha = get_res.json().get("sha")

      # קידוד הנתונים ל-Base64
      json_str = json.dumps(data, ensure_ascii=False, indent=2)
      encoded_content = base64.b64encode(json_str.encode("utf-8")).decode(
          "utf-8"
      )

      # שליחת בקשת עדכון ל-GitHub
      payload = {
          "message": "Update portfolio.json via web app",
          "content": encoded_content,
          "sha": sha,
      }
      put_res = requests.put(url, json=payload, headers=headers)
      if put_res.status_code in [200, 201]:
        print("Successfully updated portfolio.json on GitHub!")
      else:
        print(f"Failed to update GitHub: {put_res.text}")
    except Exception as e:
      print(f"Error saving to GitHub API: {e}")
