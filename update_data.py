from datetime import datetime
import json
import os
import subprocess
import pytz
import requests
import yfinance as yf

# הגדרת אזור זמן של ישראל
israel_tz = pytz.timezone('Asia/Jerusalem')
now_il = datetime.now(israel_tz)

current_date = now_il.date()
current_hour = now_il.hour
current_minute = now_il.minute
current_total_minutes = current_hour * 60 + current_minute

# זיהוי אירוע ההפעלה ב-GitHub Actions
trigger_event = os.environ.get('TRIGGER_EVENT', 'schedule')

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
        prev_close = (
            hist['Close'].iloc[-2] if len(hist) > 1 else current_price
        )
        change = round(((current_price - prev_close) / prev_close) * 100, 2)
        market_data[ticker] = {'price': current_price, 'change': change}
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
  """פונה ל-Gemini API להפקת ניתוח דינמי, חדשות ומניות מומלצות לשלב 4"""
  api_key = os.environ.get('GEMINI_API_KEY')
  if not api_key:
    print('No GEMINI_API_KEY found. Skipping AI generation.')
    return {}

  try:
    url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}'
    prompt = f"""
        אתה אנליסט בכיר בשוק ההון. ניתוח הנתונים העדכני של השוק:
        {json.dumps(market_data, ensure_ascii=False)}

        החזר JSON בלבד עם המפתחות הבאים בעברית מקצועית:
        - US_MARKET_MACRO_NEWS: תמצית חדשות מאקרו ארה"ב והפד (1-2 משפטים)
        - IL_MARKET_MACRO_NEWS: תמצית חדשות שוק ההון בישראל (1-2 משפטים)
        - EXECUTIVE_SUMMARY_1: דגש מרכזי 1 לניהול התיק
        - EXECUTIVE_SUMMARY_2: דגש מרכזי 2 לניהול סיכונים
        - EXECUTIVE_SUMMARY_3: הזדמנות טכנולוגית/סווינג
        - NEWS_CHIPS_CLOUD: עדכון קצר על מניות שבבים וענן (NVDA, AMD, MU, GOOGL וכו')
        - NEWS_ENERGY_CRYPTO: עדכון קצר על קריפטו, ביטקוין ונפט
        - FEAR_GREED_INDEX: מספר הערכה למדד הפחד והחמדנות (למשל 65)
        - FEAR_GREED_DESC: תיאור קצר של המדד (למשל: חמדנות מתונה)
        - INSTITUTIONAL_SENTIMENT: תיאור פעילות גופים מוסדיים
        - DYNAMIC_STOCKS: רשימה של 4 מניות סווינג/צמיחה מעניינות להיום בפורמט מערך:
          [
            {{"ticker": "NVDA", "name": "אנבידיה", "reason": "מובילת ה-AI בפריצה טכנית", "action": "סווינג / מעקב"}},
            {{"ticker": "AMD", "name": "אי-אמ-די", "reason": "גידול בנתח שוק המעבדים", "action": "קנייה במדרגות"}},
            {{"ticker": "PLTR", "name": "פלאנטיר", "reason": "מומנטום חיובי בחוזים ממשלתיים", "action": "מעקב צמוד"}},
            {{"ticker": "AVGO", "name": "ברודקום", "reason": "ביקוש חזק לשבבי תקשורת וענן", "action": "איסוף שקט"}}
          ]
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


# בדיקת שעות פעילות לעדכון (10:30 עד 23:30) או הפעלה ידנית
is_within_auto_hours = 630 <= current_total_minutes <= 1410
should_update = (trigger_event == 'workflow_dispatch') or is_within_auto_hours

if should_update:
  market_data = fetch_all_data()
  ai_insights = generate_ai_insights(market_data)

  try:
    date_str = now_il.strftime('%d.%m.%Y')
    time_str = now_il.strftime('%H:%M')

    # בניית כרטיסיות ה-HTML הדינמיות עבור שלב 4 (מניות AI)
    dynamic_stocks = ai_insights.get('DYNAMIC_STOCKS', [])
    dynamic_cards_html = ''

    for stock_info in dynamic_stocks:
      ticker = stock_info.get('ticker', '')
      company_name = stock_info.get('name', ticker)
      reason = stock_info.get('reason', '')
      action = stock_info.get('action', 'מעקב')

      # משיכת נתוני מחיר עדכניים עבור מניות ה-AI הדינמיות
      price = 0.0
      change = 0.0
      try:
        yf_stock = yf.Ticker(ticker)
        hist = yf_stock.history(period='2d')
        if not hist.empty:
          price = round(hist['Close'].iloc[-1], 2)
          prev_close = hist['Close'].iloc[-2] if len(hist) > 1 else price
          change = round(((price - prev_close) / prev_close) * 100, 2)
      except Exception as e:
        print(f'Error fetching dynamic stock {ticker}: {e}')

      change_color = '#00e676' if change >= 0 else '#ff5252'
      change_str = f'+{change}%' if change >= 0 else f'{change}%'

      dynamic_cards_html += f"""
            <div class="stock-card" style="background: #1a2238; border: 1px solid #2a365c; padding: 16px; border-radius: 12px; margin-bottom: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <span style="background: #2a3b63; color: #00d2ff; padding: 3px 8px; border-radius: 6px; font-size: 0.8em; font-weight: bold;">{action}</span>
                        <h3 style="margin: 8px 0 4px 0; color: #ffffff; font-size: 1.2em;">{company_name} <span style="color: #8a99ad;">({ticker})</span></h3>
                        <p style="margin: 0; font-size: 0.9em; color: #b0bec5;">{reason}</p>
                    </div>
                    <div style="text-align: left; min-width: 90px;">
                        <div style="font-size: 1.3em; font-weight: bold; color: #ffffff;">${price}</div>
                        <div style="color: {change_color}; font-weight: bold; font-size: 0.95em;">{change_str}</div>
                    </div>
                </div>
            </div>
            """

    # מילון החלפות התבניות של ה-HTML
    replacements = {
        'REPORT_TITLE': f'דו"ח סקייל שוק ההון המלא ליום {day_name} - מותאם אישית 📊',
        'LAST_UPDATED': (
            'עודכן לאחרונה:'
            f' <span dir="ltr">{date_str} | {time_str}</span>'
        ),
        'USD_ILS': str(market_data.get('USDILS=X', {}).get('price', 3.65)),
        'OIL_PRICE': str(market_data.get('CL=F', {}).get('price', 75.0)),
        'GOLD_PRICE': str(market_data.get('GC=F', {}).get('price', 2350.0)),
        'BTC_PRICE': f"{market_data.get('BTC-USD', {}).get('price', 65000.0):,}",
        'US_MARKET_MACRO_NEWS': ai_insights.get(
            'US_MARKET_MACRO_NEWS',
            'נתוני המאקרו ומדיניות הריבית ממשיכים להוות את מנוע הניווט הראשי'
            ' בוול סטריט.',
        ),
        'IL_MARKET_MACRO_NEWS': ai_insights.get(
            'IL_MARKET_MACRO_NEWS',
            'השוק המקומי מגיב להתפתחויות הביטחוניות ולנתונים הכלכליים המשקפיים.',
        ),
        'EXECUTIVE_SUMMARY_1': ai_insights.get(
            'EXECUTIVE_SUMMARY_1',
            'התמקדות בחברות ליבה בעלות יתרון תחרותי חזק וביקושים מוכחים.',
        ),
        'EXECUTIVE_SUMMARY_2': ai_insights.get(
            'EXECUTIVE_SUMMARY_2',
            'ניהול סיכונים קפדני ועבודה לפי רמות תמיכה והתנגדות.',
        ),
        'EXECUTIVE_SUMMARY_3': ai_insights.get(
            'EXECUTIVE_SUMMARY_3',
            'בחינת הזדמנויות סווינג בסקטורים המחזוריים והטכנולוגיים.',
        ),
        'NEWS_CHIPS_CLOUD': ai_insights.get(
            'NEWS_CHIPS_CLOUD',
            'ביקוש יציב לשבבי עיבוד ומרכזי נתונים תומך בהמשך המגמה החיובית.',
        ),
        'NEWS_ENERGY_CRYPTO': ai_insights.get(
            'NEWS_ENERGY_CRYPTO',
            'תנודתיות ערה בשוק הקריפטו והאנרגיה לצד מעבר לטכנולוגיות ירוקות.',
        ),
        'FEAR_GREED_INDEX': str(ai_insights.get('FEAR_GREED_INDEX', '65')),
        'FEAR_GREED_DESC': ai_insights.get(
            'FEAR_GREED_DESC', 'חמדנות מתונה - סנטימנט חיובי בזהירות'
        ),
        'INSTITUTIONAL_SENTIMENT': ai_insights.get(
            'INSTITUTIONAL_SENTIMENT',
            'הגופים המוסדיים שומרים על חשיפה גבוהה לטכנולוגיה ולשבבים.',
        ),
        'DYNAMIC_STOCKS_SECTION_4': dynamic_cards_html,
    }

    # עדכון נתוני התיק האישי בשלב 5
    for ticker, info in portfolio_buys.items():
      curr_p = market_data.get(ticker, {}).get('price', info['buy'])
      ret = round(((curr_p - info['buy']) / info['buy']) * 100, 2)
      ret_str = f'+{ret}%' if ret >= 0 else f'{ret}%'

      replacements[f'PORTFOLIO_{ticker}_SHARES'] = str(info['shares'])
      replacements[f'PORTFOLIO_{ticker}_BUY'] = str(info['buy'])
      replacements[f'PORTFOLIO_{ticker}_RETURN'] = ret_str
      replacements[f'PORTFOLIO_{ticker}_PRICE'] = str(curr_p)
      replacements[f'PORTFOLIO_{ticker}_TARGET'] = str(info['target'])
      replacements[f'PORTFOLIO_{ticker}_STATUS'] = (
          'רווח' if ret >= 0 else 'הפסד'
      )

    # טעינת index.html והחלפת התבניות
    with open('index.html', 'r', encoding='utf-8-sig') as f:
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
  print('Outside active automated hours. Skipping run.')
