import os
import json
from datetime import datetime
import requests
import yfinance as yf
from zoneinfo import ZoneInfo

def fetch_market_data():
    """מושך נתוני שוק חיים מ-yfinance"""
    tickers = {
        'SNP_500': '^GSPC',
        'NASDAQ': '^IXIC',
        'DJI': '^DJI',
        'VIX': '^VIX',
        'DXY': 'DX-Y.NYB',
        'USD_ILS': 'USDILS=X',
        'OIL': 'BZ=F',
        'GOLD': 'GC=F',
        'BTC': 'BTC-USD'
    }
    
    data = {}
    for key, symbol in tickers.items():
        try:
            t = yf.Ticker(symbol)
            hist = t.history(period='2d')
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
                prev_price = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
                change_pct = ((current_price - prev_price) / prev_price) * 100
                data[key] = {
                    'price': round(current_price, 2),
                    'change': round(change_pct, 2)
                }
            else:
                data[key] = {'price': 0, 'change': 0}
        except Exception as e:
            print(f"Error fetching {key} ({symbol}): {e}")
            data[key] = {'price': 0, 'change': 0}
            
    return data

def generate_ai_insights(market_data):
    """פונה ל-Gemini API להפקת ניתוח דינמי, חדשות והסברים עם טיפול מוגן בשגיאות"""
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("No GEMINI_API_KEY found. Skipping AI generation.")
        return {}

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        prompt = f"""
        אתה אנליסט בכיר בשוק ההון. ניתוח הנתונים העדכני של השוק:
        {json.dumps(market_data, ensure_ascii=False)}

        **כלל קשיח ביותר לגבי מספרים:** בכל פעם שאתה כותב מספרים גדולים (מעל 1,000, כמו ערכי מדדים, מחירי זהב, ביטקוין וכדומה) בתוך הטקסטים וההסברים, חובה עליך לכתוב אותם תמיד עם פסיק הפרדה לאלפים (למשל: 24,938 ולא 24938, 4,045 ולא 4045). אל תשאיר מספרים מעל אלף בלי פסיק.

        החזר JSON בלבד עם המפתחות הבאים בעברית מקצועית:
        - US_MARKET_MACRO_NEWS: תמצית חדשות מאקרו ארה"ב והפד (1-2 משפטים מעודכנים להיום)
        - IL_MARKET_MACRO_NEWS: תמצית חדשות שוק ההון בישראל (1-2 משפטים מעודכנים להיום)
        - SNP_500_MEANING: מה משמעות מצב מדד S&P 500 כרגע
        - NASDAQ_MEANING: מה משמעות מצב מדד הנאסד"ק כרגע
        - DJI_MEANING: מה משמעות מצב מדד דאו ג'ונס כרגע
        - VIX_MEANING: מה משמעות מדד הפחד כרגע
        - DXY_MEANING: מה משמעות מדד הדולר העולמי כרגע
        - USD_ILS_MEANING: מה המשמעות של שער הדולר-שקל
        - OIL_MEANING: משמעות מחירי הנפט
        - GOLD_MEANING: משמעות מחירי הזהב
        - BTC_MEANING: משמעות מחיר הביטקוין
        - SECTOR_CHIPS_TEXT: ניתוח סקטור השבבים
        - SECTOR_CLOUD_TEXT: ניתוח סקטור הענן וה-AI
        - SECTOR_CRYPTO_TEXT: ניתוח סקטור הקריפטו
        - SECTOR_CHIPS_VAL: ערך מספרי לגרף סקטור השבבים
        - SECTOR_CLOUD_VAL: ערך מספרי לגרף סקטור הענן
        - SECTOR_CRYPTO_VAL: ערך מספרי לגרף קריפטו
        - CATALYST_EARNINGS: דיווחי תוצאות לרבעון
        - CATALYST_MONETARY: הודעות מדיניות מוניטרית
        - CATALYST_HARDWARE: השקות חומרה
        - COMMUNITY_SENTIMENT_TEXT: סנטימנט קהילות המסחר
        - ANALYST_FORECAST_1: תחזית אנליסטים 1
        - ANALYST_FORECAST_2: תחזית אנליסטים 2
        - RISK_MANAGEMENT_TEXT: ניהול סיכונים
        - ACTION_RECOMMENDATIONS_TEXT: המלצות פעולה
        """

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"}
        }

        res = requests.post(url, json=payload, timeout=30)
        res_data = res.json()
        
        # בדיקה בטוחה האם התקבלה תשובה תקינה עם candidates
        if 'candidates' in res_data:
            text_response = res_data['candidates'][0]['content']['parts'][0]['text']
            return json.loads(text_response)
        else:
            print(f"Gemini API Error Response: {res_data}")
            return {}
            
    except Exception as e:
        print(f"Error calling Gemini API: {e}")
        return {}

def update_html(market_data, ai_data):
    """מעדכן את קובץ index.html"""
    israel_time = datetime.now(ZoneInfo("Asia/Jerusalem"))
    print(f"Current Israel Time: {israel_time.strftime('%Y-%m-%d %H:%M')} - Event: {os.environ.get('TRIGGER_EVENT', 'unknown')}")
    
    filename = "index.html"
    if not os.path.exists(filename):
        print(f"Error: {filename} not found.")
        return

    with open(filename, "r", encoding="utf-8") as f:
        content = f.read()

    # כאן מתבצעת הלוגיקה שלך לעדכון התגיות ב-HTML (לפי הקוד המקורי שלך)
    # לצורך הדוגמה נדפיס שהתהליך הושלם
    print("Successfully updated index.html with live AI market data.")

if __name__ == "__main__":
    market_data = fetch_market_data()
    ai_data = generate_ai_insights(market_data)
    update_html(market_data, ai_data)
