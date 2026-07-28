from datetime import datetime
import json
import os
import subprocess
import pytz
import requests
import yfinance as yf


def format_num(val, decimals=2):
  """מפרמט מספר עם פסיקים לאלפים ומספר ספרות אחרי הנקודה"""
  try:
    num = float(val)
    if decimals == 0:
      return f'{num:,.0f}'
    return f'{num:,.{decimals}f}'
  except (ValueError, TypeError):
    return str(val)


# הגדרת אזור זמן של ישראל
israel_tz = pytz.timezone('Asia/Jerusalem')
now_il = datetime.now(israel_tz)

current_date = now_il.date()
current_hour = now_il.hour
current_minute = now_il.minute
current_total_minutes = current_hour * 60 + current_minute

# זיהוי אירוע ההפעלה מול GitHub Actions (תומך גם ב-workflow_dispatch ידני וגם ב-schedule)
trigger_event = (
    os.environ.get('GITHUB_EVENT_NAME')
    or os.environ.get('TRIGGER_EVENT')
    or 'schedule'
)

# מיפוי שמות הימים בעברית
days_map = {
    0: 'שני',
    1: 'שלישי',
    2: 'רביעי',
    3: 'חמישי',
    4: 'שישי',
    5: 'שבת',
    6: 'ראשון',
}
day_name = days_map[now_il.weekday()]

print(
    f'Current Israel Time: {now_il.strftime("%Y-%m-%d %H:%M")} - Day:'
    f' {day_name} - Event: {trigger_event}'
)

# רשימת סימולים למשיכה קבועה (מדדים, סחורות ומניות תיק הליבה)
tickers_to_fetch = [
    'NVDA',
    'AMD',
    'MU',
    'GOOG',
    'AMZN',
    'META',
    'MA',
    'WMT',
    'TTWO',
    'WDC',
    'TQQQ',
    'INTC',
    'IREN',
    'CIFR',
    'IBIT',
    'SIMO',
    'SNDK',
    'NFLX',
    'GTEC',
    'GC=F',
    'CL=F',
    'BTC-USD',
    'USDILS=X',
    '^GSPC',
    '^IXIC',
    '^DJI',
    '^VIX',
]


def fetch_all_data():
  """מושך נתוני מחיר ושינוי יומי מ-yfinance"""
  market_data = {}
  for ticker in tickers_to_fetch:
    try:
      stock = yf.Ticker(ticker)
      hist = stock.history(period='2d')
      if not hist.empty:
        current_price = round(hist['Close'].iloc[-1], 2)
        prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else current_price
        change = round(((current_price - prev_close) / prev_close) * 100, 2)
        market_data[ticker] = {'price': current_price, 'change': change}
      else:
        market_data[ticker] = {'price': 0.0, 'change': 0.0}
    except Exception as e:
      print(f'Error fetching {ticker}: {e}')
      market_data[ticker] = {'price': 0.0, 'change': 0.0}
  return market_data


# נתוני קנייה ומחיר יעד של התיק בשלב 5
portfolio_buys = {
    'NVDA': {'shares': 3, 'buy': 184.90, 'target': 220.0},
    'AMD': {'shares': 20, 'buy': 211.34, 'target': 250.0},
    'MU': {'shares': 6, 'buy': 316.32, 'target': 350.0},
    'SNDK': {'shares': 4, 'buy': 630.26, 'target': 700.0},
    'WDC': {'shares': 6, 'buy': 223.23, 'target': 260.0},
    'INTC': {'shares': 20, 'buy': 43.05, 'target': 55.0},
    'SIMO': {'shares': 30, 'buy': 131.32, 'target': 160.0},
    'IREN': {'shares': 54, 'buy': 52.75, 'target': 70.0},
    'CIFR': {'shares': 28, 'buy': 17.50, 'target': 25.0},
    'META': {'shares': 2, 'buy': 661.00, 'target': 750.0},
    'AMZN': {'shares': 6, 'buy': 229.29, 'target': 270.0},
    'GOOG': {'shares': 4, 'buy': 317.95, 'target': 360.0},
    'TTWO': {'shares': 5, 'buy': 235.50, 'target': 280.0},
    'WMT': {'shares': 16, 'buy': 119.45, 'target': 140.0},
    'NFLX': {'shares': 14, 'buy': 94.03, 'target': 120.0},
    'MA': {'shares': 4, 'buy': 503.99, 'target': 580.0},
    'IBIT': {'shares': 14, 'buy': 60.48, 'target': 75.0},
    'GTEC': {'shares': 260, 'buy': 1.27, 'target': 2.0},
    'TQQQ': {'shares': 28, 'buy': 56.53, 'target': 75.0},
}


def generate_ai_insights(market_data):
  """פונה ל-Gemini API להפקת ניתוח דינמי, חדשות והסברים לשלב 1-8"""
  api_key = os.environ.get('GEMINI_API_KEY')
  if not api_key:
    print('No GEMINI_API_KEY found. Skipping AI generation.')
    return {}

  try:
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}'
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
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'response_mime_type': 'application/json'},
    }

    res = requests.post(url, json=payload, timeout=30)
    res_data = res.json()
    text_response = res_data['candidates'][0]['content']['parts'][0]['text']
    return json.loads(text_response)
  except Exception as e:
    print(f'Error calling Gemini API: {e}')
    return {}


# תנאי עדכון: אם ההפעלה ידנית (workflow_dispatch) – תתבצע תמיד מיד. אם אוטומטית (schedule) – רק בשעות הפעילות (10:30 עד 23:30)
is_within_auto_hours = 630 <= current_total_minutes <= 1410
should_update = (trigger_event == 'workflow_dispatch') or is_within_auto_hours

if should_update:
  market_data = fetch_all_data()
  ai_insights = generate_ai_insights(market_data)

  try:
    date_str = now_il.strftime('%d.%m.%Y')
    time_str = now_il.strftime('%H:%M')

    # שליפת נתוני מדדים
    sp500 = market_data.get('^GSPC', {})
    nasdaq = market_data.get('^IXIC', {})
    dji = market_data.get('^DJI', {})
    vix = market_data.get('^VIX', {})
    dxy = market_data.get('USDILS=X', {})

    # מילון החלפות התבניות המלא עבור ה-HTML
    replacements = {
        'LAST_UPDATED': f'{date_str} | {time_str}',
        # מדדים מובילים
        'SNP_500_LEVEL': format_num(sp500.get('price', 0)),
        'SNP_500_CHANGE': f"{sp500.get('change', 0)}%",
        'SNP_500_MEANING': ai_insights.get(
            'SNP_500_MEANING', 'המדד משקף את מצב השוק הרחב.'
        ),
        'NASDAQ_LEVEL': format_num(nasdaq.get('price', 0)),
        'NASDAQ_CHANGE': f"{nasdaq.get('change', 0)}%",
        'NASDAQ_MEANING': ai_insights.get(
            'NASDAQ_MEANING', 'משקף את סקטור הטכנולוגיה והצמיחה.'
        ),
        'DJI_LEVEL': format_num(dji.get('price', 0)),
        'DJI_CHANGE': f"{dji.get('change', 0)}%",
        'DJI_MEANING': ai_insights.get(
            'DJI_MEANING', 'משקף את החברות התעשייתיות המסורתיות.'
        ),
        'VIX_LEVEL': format_num(vix.get('price', 0)),
        'VIX_CHANGE': f"{vix.get('change', 0)}%",
        'VIX_MEANING': ai_insights.get(
            'VIX_MEANING', 'רמת התנודתיות והחשש בשוק.'
        ),
        'DXY_LEVEL': format_num(dxy.get('price', 0)),
        'DXY_CHANGE': f"{dxy.get('change', 0)}%",
        'DXY_MEANING': ai_insights.get(
            'DXY_MEANING', 'חוזק הדולר מול סל המטבעות.'
        ),
        # סחורות ומטבעות
        'USD_ILS': format_num(
            market_data.get('USDILS=X', {}).get('price', 3.65)
        ),
        'USD_ILS_MEANING': ai_insights.get(
            'USD_ILS_MEANING', 'השפעה על תיק השקעות דולרי מול שקל.'
        ),
        'OIL_PRICE': format_num(
            market_data.get('CL=F', {}).get('price', 75.0)
        ),
        'OIL_MEANING': ai_insights.get(
            'OIL_MEANING', 'השפעה על עלויות אנרגיה ואינפלציה.'
        ),
        'GOLD_PRICE': format_num(
            market_data.get('GC=F', {}).get('price', 2350.0)
        ),
        'GOLD_MEANING': ai_insights.get(
            'GOLD_MEANING', 'גידור מפני אי-יציבות כלכלית.'
        ),
        'BTC_PRICE': format_num(
            market_data.get('BTC-USD', {}).get('price', 65000.0)
        ),
        'BTC_MEANING': ai_insights.get(
            'BTC_MEANING', 'אינדיקטור לסנטימנט סיכון ונכסים דיגיטליים.'
        ),
        # חדשות מאקרו מעודכנות מה-AI עם דגלים אוטומטיים
        'US_MARKET_MACRO_NEWS': f"🇺🇸 השפעות על השוק האמריקאי: {ai_insights.get('US_MARKET_MACRO_NEWS', 'נתוני המאקרו ממשיכים להוות מנוע ניווט ראשי בוול סטריט.')}",
        'IL_MARKET_MACRO_NEWS': f"🇮🇱 השפעות על השוק הישראלי: {ai_insights.get('IL_MARKET_MACRO_NEWS', 'השוק המקומי מגיב להתפתחויות הביטחוניות והכלכליות.')}",
        # סקטורים וגרפים
        'SECTOR_CHIPS_TEXT': ai_insights.get(
            'SECTOR_CHIPS_TEXT', 'ביקושים חזקים לשבבי AI.'
        ),
        'SECTOR_CLOUD_TEXT': ai_insights.get(
            'SECTOR_CLOUD_TEXT', 'צמיחה במרכזי נתונים.'
        ),
        'SECTOR_CRYPTO_TEXT': ai_insights.get(
            'SECTOR_CRYPTO_TEXT', 'תנודתיות ערה בנכסים דיגיטליים.'
        ),
        'SECTOR_CHIPS_VAL': format_num(
            ai_insights.get('SECTOR_CHIPS_VAL', 2.0)
        ),
        'SECTOR_CLOUD_VAL': format_num(
            ai_insights.get('SECTOR_CLOUD_VAL', 1.5)
        ),
        'SECTOR_CRYPTO_VAL': format_num(
            ai_insights.get('SECTOR_CRYPTO_VAL', 0.5)
        ),
        # קטליזטורים
        'CATALYST_EARNINGS': ai_insights.get(
            'CATALYST_EARNINGS', 'מעקב אחר דוחות כספיים רבעוניים.'
        ),
        'CATALYST_MONETARY': ai_insights.get(
            'CATALYST_MONETARY', 'החלטות ריבית והצהרות הבנקים המרכזיים.'
        ),
        'CATALYST_HARDWARE': ai_insights.get(
            'CATALYST_HARDWARE', 'השקות מעבדים וכרטיסי מסך חדשים.'
        ),
        # סנטימנט וניהול סיכונים
        'COMMUNITY_SENTIMENT_TEXT': ai_insights.get(
            'COMMUNITY_SENTIMENT_TEXT', 'אופטימיות זהירה בקרב סוחרים.'
        ),
        'ANALYST_FORECAST_1': ai_insights.get(
            'ANALYST_FORECAST_1', 'המשך תנודתיות בסקטור ירוק/אדום.'
        ),
        'ANALYST_FORECAST_2': ai_insights.get(
            'ANALYST_FORECAST_2', 'התמקדות בחברות בעלות תזרים מזומנים חזק.'
        ),
        'RISK_MANAGEMENT_TEXT': ai_insights.get(
            'RISK_MANAGEMENT_TEXT', 'עבודה עם פקודות סטופ-לוס וגיוון תיק.'
        ),
        'ACTION_RECOMMENDATIONS_TEXT': ai_insights.get(
            'ACTION_RECOMMENDATIONS_TEXT', 'התנהלות מדודה ואיסוף מניות ליבה.'
        ),
    }

    # מילוי דינמי למניות הליבה והסווינג באסטרטגיה
    all_strategy_tickers = [
        'NVDA',
        'AMD',
        'MU',
        'GOOG',
        'AMZN',
        'META',
        'MA',
        'WMT',
        'TTWO',
        'WDC',
        'TQQQ',
        'INTC',
        'IREN',
        'CIFR',
        'IBIT',
        'SIMO',
        'SNDK',
        'NFLX',
        'GTEC',
    ]
    for ticker in all_strategy_tickers:
      p_data = market_data.get(ticker, {})
      replacements[f'{ticker}_PRICE'] = format_num(p_data.get('price', 0.0))
      replacements[f'{ticker}_PRE'] = format_num(p_data.get('price', 0.0))
      replacements[f'{ticker}_PCT'] = f"{p_data.get('change', 0.0)}%"
      replacements[f'{ticker}_TARGET'] = format_num(
          portfolio_buys.get(ticker, {}).get('target', 0.0)
      )
      replacements[f'{ticker}_RATIONALE'] = ai_insights.get(
          f'{ticker}_RATIONALE', 'הובלה טכנולוגית וביקושים יציבים.'
      )
      replacements[f'{ticker}_SWING_TEXT'] = ai_insights.get(
          f'{ticker}_SWING_TEXT', 'פוטנציאל למומנטום קצר טווח.'
      )

    # מילוי נתוני התיק האישי
    for ticker, info in portfolio_buys.items():
      curr_p = market_data.get(ticker, {}).get('price', info['buy'])
      ret = round(((curr_p - info['buy']) / info['buy']) * 100, 2)
      ret_str = f'+{ret}%' if ret >= 0 else f'{ret}%'

      replacements[f'PORTFOLIO_{ticker}_PRICE'] = format_num(curr_p)
      replacements[f'PORTFOLIO_{ticker}_PRE'] = format_num(curr_p)
      replacements[f'PORTFOLIO_{ticker}_TARGET'] = format_num(info['target'])
      replacements[f'PORTFOLIO_{ticker}_STATUS'] = (
          f'רווח {ret_str}' if ret >= 0 else f'הפסד {ret_str}'
      )
      replacements[f'PORTFOLIO_{ticker}_NEWS'] = ai_insights.get(
          f'PORTFOLIO_{ticker}_NEWS', 'ביצועים בהתאם לציפיות השוק.'
      )

    # טעינת התבנית והחלפת התבניות (קורא מ-index.template.html ושומר ל-index.html)
    with open('index.template.html', 'r', encoding='utf-8-sig') as f:
      content = f.read()

    for key, val in replacements.items():
      placeholder = f'{{{{{key}}}}}'
      content = content.replace(placeholder, str(val))

    with open('index.html', 'w', encoding='utf-8') as f:
      f.write(content)

    print('Successfully updated index.html with live AI market data.')

    # ביצוע Git Commit ו-Push
    subprocess.run(
        ['git', 'config', '--global', 'user.name', 'github-actions[bot]'],
        check=True,
    )
    subprocess.run(
        [
            'git',
            'config',
            '--global',
            'user.email',
            'github-actions[bot]@users.noreply.github.com',
        ],
        check=True,
    )
    subprocess.run(['git', 'add', 'index.html'], check=True)

    status = subprocess.run(
        ['git', 'status', '--porcelain'],
        capture_output=True,
        text=True,
        check=True,
    )
    if 'index.html' in status.stdout:
      subprocess.run(
          [
              'git',
              'commit',
              '-m',
              f'Auto-update AI stock report for {day_name} at {time_str}',
          ],
          check=True,
      )
      subprocess.run(['git', 'push'], check=True)
      print('Changes committed and pushed successfully.')
    else:
      print('No changes in index.html to commit.')

  except Exception as e:
    print(f'Error updating file: {e}')
else:
  print('Outside active automated hours. Skipping scheduled run.')
