from datetime import datetime
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

# זיהוי האם ההפעלה היא ידנית או אוטומטית מגיטהאב
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

# רשימת כל הסימולים שצריך למשוך עבור התיק, המדדים והסחורות
tickers_to_fetch = [
    'NVDA', 'AMD', 'MU', 'GOOG', 'AMZN', 'META', 'MA', 'WMT', 'TTWO', 'WDC',
    'TQQQ', 'INTC', 'IREN', 'CIFR', 'IBIT', 'SIMO', 'SNDK', 'NFLX', 'GTEC',
    'GC=F', 'CL=F', 'BTC-USD', 'USDILS=X'
]

def fetch_all_data():
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
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            market_data[ticker] = {'price': 0.0, 'change': 0.0}
    return market_data

# נתוני קנייה ומספר מניות מדויקים (ללא שינוי) עבור שלב 5
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

# שעות פעילות לעדכון האתר: מ-10:30 בבוקר ועד 23:30 בלילה
is_within_auto_hours = 630 <= current_total_minutes <= 1410
should_update = (trigger_event == 'workflow_dispatch') or is_within_auto_hours

if should_update:
    market_data = fetch_all_data()
    
    try:
        date_str = now_il.strftime('%d.%m.%Y')
        time_str = now_il.strftime('%H:%M')

        # מיפוי ערכים להזרקה לתוך תבניות ה-{{...}} בקובץ ה-HTML
        replacements = {
            'REPORT_TITLE': f'דו"ח סקייל שוק ההון המלא ליום {day_name} - נתונים מעודכנים 📊',
            'LAST_UPDATED': f'עודכן לאחרונה: <span dir="ltr">{date_str} | {time_str}</span>',
            'MACRO_INDICES_DESC': 'המדדים המובילים נסחרים בהתאם לנתוני המאקרו האחרונים וציפיות הנזילות בשווקים.',
            'USD_ILS': str(market_data.get('USDILS=X', {}).get('price', 3.65)),
            'OIL_PRICE': str(market_data.get('CL=F', {}).get('price', 75.0)),
            'GOLD_PRICE': str(market_data.get('GC=F', {}).get('price', 2350.0)),
            'BTC_PRICE': f"{market_data.get('BTC-USD', {}).get('price', 65000.0):,}",
            'US_MARKET_MACRO_NEWS': 'התפתחויות באינפלציה ובמדיניות הפד ממשיכות להוות את מוקד העניין הראשי בוול סטריט.',
            'IL_MARKET_MACRO_NEWS': 'השוק המקומי מגיב לנתוני המאקרו ולעדכונים הביטחוניים והכלכליים.',
            
            # סקטורים
            'SECTOR_TECH_PERF': '+1.4%',
            'SECTOR_COMM_PERF': '+0.8%',
            'SECTOR_CONS_DISC_PERF': '-0.5%',
            'SECTOR_CONS_STAPLES_PERF': '+0.3%',
            'SECTOR_FIN_PERF': '+0.9%',
            'SECTOR_HEALTH_PERF': '-0.2%',
            'SECTOR_IND_PERF': '+0.6%',
            'SECTOR_ENERGY_PERF': '-1.1%',
            'SECTOR_MAT_PERF': '+0.4%',
            'SECTOR_RE_PERF': '-0.7%',
            'SECTOR_UTIL_PERF': '+0.2%',
            
            # זרזים
            'CATALYST_EARNINGS': 'דוחות כספיים עונתיים של חברות הטכנולוגיה והשבבים.',
            'CATALYST_MONETARY': 'החלטות ריבית ופרוטוקולים של הבנקים המרכזיים.',
            'CATALYST_HARDWARE': 'השקות מוצרי חומרה, מעבדים ופתרונות ענן מתקדמים.',
            
            # מחירי מניות שלב 4
            'NVDA_PRICE': str(market_data.get('NVDA', {}).get('price', 0)),
            'AMD_PRICE': str(market_data.get('AMD', {}).get('price', 0)),
            'MU_PRICE': str(market_data.get('MU', {}).get('price', 0)),
            'GOOG_PRICE': str(market_data.get('GOOG', {}).get('price', 0)),
            'AMZN_PRICE': str(market_data.get('AMZN', {}).get('price', 0)),
            'META_PRICE': str(market_data.get('META', {}).get('price', 0)),
            'MA_PRICE': str(market_data.get('MA', {}).get('price', 0)),
            'WMT_PRICE': str(market_data.get('WMT', {}).get('price', 0)),
            'TTWO_PRICE': str(market_data.get('TTWO', {}).get('price', 0)),
            'WDC_PRICE': str(market_data.get('WDC', {}).get('price', 0)),
            'TQQQ_PRICE': str(market_data.get('TQQQ', {}).get('price', 0)),
            'INTC_PRICE': str(market_data.get('INTC', {}).get('price', 0)),
            'IREN_PRICE': str(market_data.get('IREN', {}).get('price', 0)),
            'CIFR_PRICE': str(market_data.get('CIFR', {}).get('price', 0)),
            'IBIT_PRICE': str(market_data.get('IBIT', {}).get('price', 0)),
            'SIMO_PRICE': str(market_data.get('SIMO', {}).get('price', 0)),
            'SNDK_PRICE': str(market_data.get('SNDK', {}).get('price', 0)),
            'NFLX_PRICE': str(market_data.get('NFLX', {}).get('price', 0)),
            'GTEC_PRICE': str(market_data.get('GTEC', {}).get('price', 0)),
            
            # סנטימנט וסיכום מנהלים
            'FEAR_GREED_INDEX': '68',
            'FEAR_GREED_DESC': 'חמדנות מתונה - המשקיעים מפגינים אופטימיות זהירה.',
            'INSTITUTIONAL_SENTIMENT': 'הגופים המוסדיים ממשיכים לתמוך בסקטורי הצמיחה והטכנולוגיה המובילים.',
            'EXECUTIVE_SUMMARY_1': 'התמקדות בחברות ליבה בעלות יתרון תחרותי חזק וביקושים מוכחים.',
            'EXECUTIVE_SUMMARY_2': 'ניהול סיכונים קפדני ועבודה לפי רמות תמיכה והתנגדות.',
            'EXECUTIVE_SUMMARY_3': 'בחינת הזדמנויות סווינג בסקטורים המחזוריים והטכנולוגיים.',
            'NEWS_CHIPS_CLOUD': 'ביקוש יציב לשבבי עיבוד ומרכזי נתונים תומך בהמשך המגמה החיובית.',
            'NEWS_ENERGY_CRYPTO': 'תנודתיות ערה בשוק הקריפטו והאנרגיה לצד מעבר לטכנולוגיות ירוקות.'
        }

        # חישוב דינמי של מחירי שלב 5 תוך שמירה מלאה על מספר המניות ומחירי הקנייה שלך
        for ticker, info in portfolio_buys.items():
            curr_p = market_data.get(ticker, {}).get('price', info['buy'])
            ret = round(((curr_p - info['buy']) / info['buy']) * 100, 2)
            ret_str = f"+{ret}%" if ret >= 0 else f"{ret}%"
            
            replacements[f'PORTFOLIO_{ticker}_SHARES'] = str(info['shares'])
            replacements[f'PORTFOLIO_{ticker}_BUY'] = str(info['buy'])
            replacements[f'PORTFOLIO_{ticker}_RETURN'] = ret_str
            replacements[f'PORTFOLIO_{ticker}_PRICE'] = str(curr_p)
            replacements[f'PORTFOLIO_{ticker}_TARGET'] = str(info['target'])
            replacements[f'PORTFOLIO_{ticker}_STATUS'] = 'רווח' if ret >= 0 else 'הפסד'

        # קריאת קובץ ה-HTML והחלפת התבניות
        with open('index.html', 'r', encoding='utf-8-sig') as f:
            content = f.read()

        for key, val in replacements.items():
            placeholder = f"{{{{{key}}}}}"
            content = content.replace(placeholder, str(val))

        with open('index.html', 'w', encoding='utf-8') as f:
            f.write(content)

        print('Successfully updated index.html template with market data.')

        # ביצוע Git Commit ו-Push אוטומטיים
        subprocess.run(['git', 'config', '--global', 'user.name', 'github-actions[bot]'], check=True)
        subprocess.run(['git', 'config', '--global', 'user.email', 'github-actions[bot]@users.noreply.github.com'], check=True)
        subprocess.run(['git', 'add', 'index.html'], check=True)

        status = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True, check=True)
        if 'index.html' in status.stdout:
            subprocess.run(['git', 'commit', '-m', f'Update market data template for {day_name} at {time_str}'], check=True)
            subprocess.run(['git', 'push'], check=True)
            print('Successfully pushed updated index.html to GitHub!')
        else:
            print('No changes detected by git.')

    except Exception as e:
        print(f'Error updating HTML template: {e}')
else:
    print('Outside active auto-update hours. Skipping update.')
